"""执行日志总线（运行在 worker 进程内）。

职责：
- 接收执行编排层的日志行（``append``，同步入口、按行分配递增 seq）
- 每行经 Redis pub/sub 实时分发给 API 进程的 WS 订阅者
- 周期性把增量日志落到 MySQL ``executions.logs``（崩溃不丢全量日志）
- 结束时发布 EOF 控制消息（在终态落库之后），WS 侧据此收尾

seq 不变式：行号在 append() 内同步递增（单事件循环内天然有序）；
EOF 必须在最后一次 flush 与终态 commit 之后发布。

Redis 消息格式（内部协议，不透传前端）：
- 行：``{"seq": 12, "line": "...\\n"}``
- 结束：``{"eof": true, "seq": 12}``

对前端的 WS 消息保持纯文本日志行，与既有契约逐字节一致。
"""

import asyncio
import json
from collections import deque
from typing import Awaitable, Callable

from sqlalchemy import update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.execution import Execution

# 落库连续失败的容忍次数，超过后停止落库（实时流不受影响）
_PERSIST_MAX_CONSECUTIVE_FAILURES = 3


def logs_channel(execution_id: int) -> str:
    return f"exec:logs:{execution_id}"


def encode_line(seq: int, line: str) -> str:
    return json.dumps({"seq": seq, "line": line}, ensure_ascii=False)


def encode_eof(seq: int) -> str:
    return json.dumps({"eof": True, "seq": seq})


def split_db_lines(logs: str | None) -> list[str]:
    """把 MySQL logs 列内容按 LogBus.append 的语义拆回行列表（每行以 \\n 结尾）"""
    pieces = (logs or "").split("\n")
    if pieces and pieces[-1] == "":
        pieces = pieces[:-1]
    return [p + "\n" for p in pieces]


_redis_client = None


async def _get_redis():
    """懒初始化共享 Redis 连接（worker/API 进程各自一份）"""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(settings.redis_url)
    return _redis_client


class ExecutionLogBus:
    """单次执行的日志缓冲与分发器。

    publish/persist 均可注入（默认 Redis PUBLISH / MySQL 增量 UPDATE），
    便于单元测试脱离 Redis 与 MySQL。
    """

    def __init__(
        self,
        execution_id: int,
        *,
        publish: Callable[[str], Awaitable[None]] | None = None,
        persist: Callable[[str], Awaitable[None]] | None = None,
        flush_interval: float = 1.0,
        live_buffer_max: int = 5000,
    ):
        self.execution_id = execution_id
        self._publish = publish
        self._persist = persist
        self._flush_interval = flush_interval
        self._seq = 0
        self._pending: list[str] = []  # 待落库的行（按序）
        self._live: deque[tuple[int, str]] = deque(maxlen=live_buffer_max)  # 待发布的 (seq, line)
        self._publisher_task: asyncio.Task | None = None
        self._flusher_task: asyncio.Task | None = None
        self._closed = False
        self._persist_failures = 0

    @property
    def last_seq(self) -> int:
        return self._seq

    def append(self, line: str) -> None:
        """同步入口（可直接当 log_callback 用）：按 \\n 拆行，保证 1 seq = 1 行"""
        if self._closed:
            return
        pieces = line.split("\n")
        for i, piece in enumerate(pieces):
            if i == len(pieces) - 1 and piece == "":
                break  # 尾部换行不产生空行
            part = piece + "\n"
            self._seq += 1
            self._pending.append(part)
            self._live.append((self._seq, part))

    async def start(self) -> None:
        self._publisher_task = asyncio.create_task(self._publisher())
        self._flusher_task = asyncio.create_task(self._flusher())

    async def _publisher(self) -> None:
        publish = self._publish if self._publish is not None else self._default_publish
        while True:
            if self._live:
                seq, line = self._live[0]
                try:
                    await publish(encode_line(seq, line))
                    self._live.popleft()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Redis 瞬断：保留队首稍后重试（WS 侧有 DB 轮询兜底）
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.05)

    async def _flusher(self) -> None:
        while True:
            await asyncio.sleep(self._flush_interval)
            await self.flush()

    async def flush(self) -> None:
        """把 pending 增量落库（服务端 CONCAT 追加，只传增量）；失败保留待下轮重试"""
        if self._persist_failures >= _PERSIST_MAX_CONSECUTIVE_FAILURES:
            return  # 已停用落库（如 logs 超长），避免无谓重试
        count = len(self._pending)
        if count == 0:
            return
        delta = "".join(self._pending[:count])
        persist = self._persist if self._persist is not None else self._default_persist
        try:
            await persist(delta)
            del self._pending[:count]
            self._persist_failures = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            self._persist_failures += 1
            if self._persist_failures >= _PERSIST_MAX_CONSECUTIVE_FAILURES:
                self._pending.clear()

    async def finalize(self) -> None:
        """停止周期 flush 并把剩余增量全部落库（须在终态 commit 之前调用）"""
        if self._flusher_task is not None:
            self._flusher_task.cancel()
            await asyncio.gather(self._flusher_task, return_exceptions=True)
            self._flusher_task = None
        await self.flush()

    async def close(self, *, publish_eof: bool = True) -> None:
        """收尾：等 live 队列发布完 → 发 EOF → 退出后台任务。须在终态 commit 之后调用"""
        if self._closed:
            return
        deadline = asyncio.get_running_loop().time() + 5.0
        while self._live and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)
        self._closed = True
        if publish_eof:
            try:
                publish = self._publish if self._publish is not None else self._default_publish
                await publish(encode_eof(self._seq))
            except Exception:
                pass  # EOF 丢失时 WS 侧按终态轮询兜底
        for task in (self._publisher_task, self._flusher_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(t for t in (self._publisher_task, self._flusher_task) if t is not None),
            return_exceptions=True,
        )
        self._publisher_task = None
        self._flusher_task = None

    async def _default_publish(self, message: str) -> None:
        redis = await _get_redis()
        await redis.publish(logs_channel(self.execution_id), message)

    async def _default_persist(self, delta: str) -> None:
        async with AsyncSessionLocal() as session:
            # logs = logs + delta 编译为 MySQL 的 CONCAT(logs, :delta)，只传增量
            await session.execute(
                update(Execution)
                .where(Execution.id == self.execution_id)
                .values(logs=Execution.logs + delta)
            )
            await session.commit()
