"""ExecutionLogBus：seq 递增、增量落库、EOF 时序、落库失败重试"""

import asyncio
import json

from app.services.log_bus import (
    ExecutionLogBus,
    encode_eof,
    logs_channel,
    split_db_lines,
)


def _sync_sink(sink: list) -> list:
    """把 list.append 包装成 async callable"""

    async def _publish(message: str) -> None:
        sink.append(message)

    return _publish


async def test_seq_increments_and_publish_order():
    published: list[str] = []
    bus = ExecutionLogBus(1, publish=_sync_sink(published))
    await bus.start()
    bus.append("line one\n")
    bus.append("a\nb\n")  # 多行拆分
    bus.append("no trailing newline")
    await bus.close(publish_eof=False)

    assert bus.last_seq == 4
    seqs = [json.loads(m)["seq"] for m in published]
    assert seqs == [1, 2, 3, 4]
    lines = [json.loads(m)["line"] for m in published]
    assert lines[0] == "line one\n"
    assert lines[3] == "no trailing newline\n"  # 自动补换行，保证 1 seq = 1 行


async def test_flush_sends_only_delta():
    deltas: list[str] = []

    async def persist(delta: str):
        deltas.append(delta)

    bus = ExecutionLogBus(1, persist=persist, flush_interval=0.01)
    await bus.start()
    bus.append("a\n")
    await asyncio.sleep(0.05)
    bus.append("b\nc\n")
    await bus.finalize()

    assert deltas == ["a\n", "b\nc\n"]  # 每轮只传新增量


async def test_finalize_flushes_remaining():
    deltas: list[str] = []

    async def persist(delta: str):
        deltas.append(delta)

    bus = ExecutionLogBus(1, persist=persist, flush_interval=3600)
    await bus.start()
    bus.append("x\n")
    bus.append("y\n")
    await bus.finalize()

    assert deltas == ["x\ny\n"]


async def test_persist_failure_requeues_delta():
    calls = 0

    async def failing_persist(delta: str):
        nonlocal calls
        calls += 1
        raise RuntimeError("db down")

    bus = ExecutionLogBus(1, persist=failing_persist, flush_interval=0.01)
    await bus.start()
    bus.append("keep\n")
    await bus.finalize()

    assert calls >= 1
    # 落库失败后增量保留，未丢失（可被下一轮重试）
    assert bus._pending == ["keep\n"]


async def test_eof_published_after_final_flush():
    published: list[str] = []
    flushed: list[str] = []

    async def persist(delta: str):
        flushed.append(delta)

    bus = ExecutionLogBus(
        1, publish=_sync_sink(published), persist=persist, flush_interval=3600
    )
    await bus.start()
    bus.append("last line\n")
    await bus.finalize()
    await bus.close(publish_eof=True)

    eofs = [json.loads(m) for m in published if json.loads(m).get("eof")]
    assert len(eofs) == 1
    assert eofs[0]["seq"] == bus.last_seq == 1


async def test_close_stops_appends():
    published: list[str] = []
    bus = ExecutionLogBus(1, publish=_sync_sink(published))
    await bus.start()
    await bus.close(publish_eof=False)
    bus.append("after close\n")
    assert bus.last_seq == 0


def test_split_db_lines_roundtrip():
    text = "a\nb\n"
    assert split_db_lines(text) == ["a\n", "b\n"]
    assert split_db_lines("") == []
    assert split_db_lines(None) == []


def test_logs_channel_naming():
    assert logs_channel(42) == "exec:logs:42"
    assert json.loads(encode_eof(9)) == {"eof": True, "seq": 9}
