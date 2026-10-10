"""WS 日志流：seq 对齐去重、断层补洞、EOF 收尾、DB 轮询降级"""

import asyncio
import json

import app.services.log_stream_service as lss
from app.services.log_bus import encode_eof, encode_line, split_db_lines


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self) -> None:
        self.closed = True


class FakePubSub:
    """预置消息队列的假 pubsub：get_message 逐条吐出"""

    def __init__(self, messages: list[dict]) -> None:
        self._messages = list(messages)
        self.closed = False

    async def get_message(self, ignore_subscribe_messages=True, timeout=None):
        await asyncio.sleep(0)
        if self._messages:
            return {"type": "message", "data": self._messages.pop(0)}
        return None

    async def aclose(self) -> None:
        self.closed = True


def _db_state(lines: list[str], status: str = "running"):
    state = {"logs": "".join(lines), "status": status}

    async def fake_replay(execution_id: int):
        return split_db_lines(state["logs"]), state["status"]

    return state, fake_replay


async def test_replay_drops_duplicate_live_lines(monkeypatch):
    """重放 2 行后，live 的 seq 1-2 应被丢弃，seq 3 起正常转发"""
    state, fake_replay = _db_state(["a\n", "b\n"])
    monkeypatch.setattr(lss, "_replay_history", fake_replay)

    messages = [
        encode_line(1, "a\n"),  # 重放已覆盖 → 丢弃
        encode_line(2, "b\n"),  # 丢弃
        encode_line(3, "c\n"),  # 发送
        encode_eof(3),
    ]
    ws = FakeWebSocket()
    await lss._stream_by_pubsub(ws, 1, FakePubSub(messages), expected=3)

    assert ws.sent == ["c\n"]


async def test_gap_fill_orders_out_of_window_lines(monkeypatch):
    """seq 5 先到（断层缓冲），seq 4 后到 → 按 4、5 顺序发出"""
    state, fake_replay = _db_state(["a\n"])
    monkeypatch.setattr(lss, "_replay_history", fake_replay)

    messages = [
        encode_line(2, "b\n"),
        encode_line(4, "d\n"),  # 断层（3 未落库也未收到）→ 缓冲
        encode_line(3, "c\n"),  # 补上后 4 随之发出
        encode_eof(4),
    ]
    ws = FakeWebSocket()
    await lss._stream_by_pubsub(ws, 1, FakePubSub(messages), expected=2)

    assert ws.sent == ["b\n", "c\n", "d\n"]


async def test_gap_filled_from_db_flush(monkeypatch):
    """seq 3/4 已缓冲，DB 落库补齐后按序发出并清缓冲"""
    state, fake_replay = _db_state(["a\n"])
    monkeypatch.setattr(lss, "_replay_history", fake_replay)

    async def delayed_replay(execution_id: int):
        # 首次回查时 DB 已有更多行（模拟 flush 完成）
        return split_db_lines(state["logs"]), state["status"]

    messages = [
        encode_line(3, "c\n"),
        encode_line(4, "d\n"),
        encode_eof(4),
    ]
    state["logs"] = "a\nb\nc\nd\n"  # 回查 DB 时全部已落库

    ws = FakeWebSocket()
    await lss._stream_by_pubsub(ws, 1, FakePubSub(messages), expected=2)

    assert ws.sent == ["b\n", "c\n", "d\n"]


async def test_eof_triggers_final_replay_and_close(monkeypatch):
    """EOF 到达后最后补齐 DB 增量（worker 在终态 commit 后发 EOF）"""
    state, fake_replay = _db_state(["a\n"])
    monkeypatch.setattr(lss, "_replay_history", fake_replay)

    messages = [encode_line(2, "b\n"), encode_eof(3)]
    state["logs"] = "a\nb\nfinal\n"  # EOF 后 DB 还有最后未实时收到的行
    state["status"] = "success"

    ws = FakeWebSocket()
    await lss._stream_by_pubsub(ws, 1, FakePubSub(messages), expected=2)

    assert ws.sent == ["b\n", "final\n"]


async def test_idle_drain_by_timeout_closes_on_terminal(monkeypatch):
    """无缓冲、无 EOF 的空闲路径：周期回查 DB，终态后收尾（不触发 NameError 等异常）"""
    state, fake_replay = _db_state(["a\n", "b\n"], status="success")
    monkeypatch.setattr(lss, "_replay_history", fake_replay)
    monkeypatch.setattr(lss, "_IDLE_STATUS_CHECK", 0.05)

    ws = FakeWebSocket()
    # expected=3：DB 已全部覆盖；pubsub 无任何消息 → 走 idle drain
    # 函数应正常返回（终态收尾），不抛异常、不发送重复行（关闭由外层负责）
    await asyncio.wait_for(
        lss._stream_by_pubsub(ws, 1, FakePubSub([]), expected=3), timeout=2
    )

    assert ws.sent == []  # 无增量可发


async def test_db_poll_fallback_without_redis(monkeypatch):
    """Redis 不可用：轮询 DB 增量直到终态"""
    state, _ = _db_state(["a\n"])
    rounds = {"n": 0}

    async def fake_replay(execution_id: int):
        rounds["n"] += 1
        if rounds["n"] >= 2:
            state["status"] = "success"
            state["logs"] = "a\nb\nc\n"
        return split_db_lines(state["logs"]), state["status"]

    monkeypatch.setattr(lss, "_replay_history", fake_replay)

    ws = FakeWebSocket()
    await lss._stream_by_db_polling(ws, 1, expected=2)

    assert ws.sent == ["b\n", "c\n"]


def test_split_db_lines_matches_bus_semantics():
    assert split_db_lines("x\ny\n") == ["x\n", "y\n"]
    assert split_db_lines("x\ny") == ["x\n", "y\n"]  # 无尾换行也按行拆
