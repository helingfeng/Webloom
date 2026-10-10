"""WS 执行日志流：先订阅 Redis 再重放 MySQL 历史，seq 对齐去重补洞。

对前端的 WS 消息保持纯文本日志行（与旧版 ConnectionManager 契约一致），
EOF/seq 等控制信息均不透传。Redis 不可用时退化为 DB 轮询，功能不中断。

seq 对齐算法：
1. 先订阅 Redis channel（缩小漏行窗口）；
2. 从 MySQL ``executions.logs`` 重放已落库的历史行，``expected = 行数 + 1``；
3. 消费实时消息：seq < expected 丢弃（重放已覆盖）；seq == expected 转发；
   seq > expected（订阅前产生、恰好未落库的行）进缓冲，周期回查 DB 补洞；
4. 收到 EOF（worker 在终态落库后发布）→ 最后补齐一次 DB 增量 → 结束；
5. 执行已是终态时不进入实时阶段，直接结束。
"""

import asyncio
import json

from fastapi import WebSocket

from app.database import AsyncSessionLocal
from app.models.execution import Execution
from app.services.log_bus import logs_channel, split_db_lines
from app.task_queue import get_pool

_SUBSCRIBE_TIMEOUT = 3.0
_POLL_INTERVAL = 0.5  # DB 轮询降级间隔
_GAP_DRAIN_INTERVAL = 0.2  # 断层补洞时回查 DB 的间隔
_IDLE_STATUS_CHECK = 5.0  # 无消息多久后回查一次终态（EOF 丢失兜底）


async def _load_execution(execution_id: int) -> Execution | None:
    async with AsyncSessionLocal() as session:
        return await session.get(Execution, execution_id)


async def _replay_history(execution_id: int) -> tuple[list[str], str]:
    """重放已落库的历史日志行，返回 (行列表, 状态)"""
    execution = await _load_execution(execution_id)
    if execution is None:
        return [], "missing"
    return split_db_lines(execution.logs), execution.status


async def stream_execution_logs(websocket: WebSocket, execution_id: int) -> None:
    await websocket.accept()

    history, status = await _replay_history(execution_id)
    if status == "missing":
        await websocket.close()
        return

    expected = len(history) + 1
    for line in history:
        await websocket.send_text(line)
    if status in ("success", "failed"):
        await websocket.close()
        return

    try:
        pubsub = None
        try:
            pool = await asyncio.wait_for(get_pool(), timeout=_SUBSCRIBE_TIMEOUT)
            pubsub = pool.pubsub()
            await pubsub.subscribe(logs_channel(execution_id))
        except Exception:
            pubsub = None

        if pubsub is None:
            await _stream_by_db_polling(websocket, execution_id, expected)
        else:
            try:
                await _stream_by_pubsub(websocket, execution_id, pubsub, expected)
            finally:
                await pubsub.aclose()
    except Exception as exc:
        # WS 流中断本身由前端轮询兜底，但异常不能静默：打印便于排障
        import sys

        print(f"[ws] log stream for execution {execution_id} interrupted: {exc!r}", file=sys.stderr)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


async def _send_lines(websocket: WebSocket, lines: list[str], start: int) -> int:
    """从第 start 行（1-based）开始发送，返回新的 expected"""
    for line in lines[start - 1 :]:
        await websocket.send_text(line)
    return len(lines) + 1


async def _stream_by_pubsub(
    websocket: WebSocket, execution_id: int, pubsub, expected: int
) -> None:
    """订阅模式：seq 对齐转发 + 断层 DB 补洞 + EOF 收尾"""
    buffered: dict[int, str] = {}  # 断层期间收到的超前行
    got_eof = False
    last_drain = asyncio.get_running_loop().time()

    while True:
        message = await pubsub.get_message(
            ignore_subscribe_messages=True, timeout=_POLL_INTERVAL
        )
        now = asyncio.get_running_loop().time()

        if message and message.get("type") == "message":
            try:
                data = json.loads(message["data"])
            except (TypeError, ValueError):
                data = None
            if isinstance(data, dict):
                if data.get("eof"):
                    got_eof = True
                else:
                    seq = data.get("seq")
                    line = data.get("line")
                    if isinstance(seq, int) and isinstance(line, str):
                        if seq == expected:
                            await websocket.send_text(line)
                            expected += 1
                            # 顺带 flush 已连续的缓冲行
                            while expected in buffered:
                                await websocket.send_text(buffered.pop(expected))
                                expected += 1
                        elif seq > expected:
                            buffered[seq] = line
                        # seq < expected：重放已覆盖，丢弃

        # 存在断层 / 收到 EOF / 周期兜底（EOF 丢失时靠回查终态收尾）时回查 DB
        if buffered or got_eof or now - last_drain >= _IDLE_STATUS_CHECK:
            last_drain = now
            history, status = await _replay_history(execution_id)
            if expected <= len(history):
                expected = await _send_lines(websocket, history, expected)
                while expected in buffered:
                    await websocket.send_text(buffered.pop(expected))
                    expected += 1
            for seq in [s for s in buffered if s < expected]:
                buffered.pop(seq)
            if got_eof or status in ("success", "failed"):
                return


async def _stream_by_db_polling(
    websocket: WebSocket, execution_id: int, expected: int
) -> None:
    """降级模式：Redis 不可用时轮询 DB 增量直到终态"""
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        history, status = await _replay_history(execution_id)
        if expected <= len(history):
            expected = await _send_lines(websocket, history, expected)
        if status in ("success", "failed", "missing"):
            return
