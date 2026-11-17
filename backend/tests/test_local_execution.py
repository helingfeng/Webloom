import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models.execution import Execution
from app.services.local_execution_service import LocalExecutor


@pytest_asyncio.fixture
async def local_db(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", connect_args={"timeout": 30}
    )
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def add_jobs(maker, count=1, status="pending", target_type="script"):
    async with maker() as db:
        rows = [
            Execution(
                target_type=target_type,
                target_id=1,
                mode="manual",
                status=status,
                logs="",
                inputs={},
                outputs={},
            )
            for _ in range(count)
        ]
        db.add_all(rows)
        await db.commit()
        return [r.id for r in rows]


async def eventually(check):
    async with asyncio.timeout(5):
        while not await check():
            await asyncio.sleep(0.01)


async def test_durable_pending_jobs_obey_concurrency_and_run_once(local_db, tmp_path):
    ids = await add_jobs(local_db, 5)
    seen, active, maximum = [], 0, 0

    async def job(eid):
        nonlocal active, maximum
        seen.append(eid)
        active += 1
        maximum = max(maximum, active)
        async with local_db() as db:
            await db.execute(
                update(Execution).where(Execution.id == eid).values(status="running")
            )
            await db.commit()
        await asyncio.sleep(0.03)
        async with local_db() as db:
            await db.execute(
                update(Execution).where(Execution.id == eid).values(status="success")
            )
            await db.commit()
        active -= 1

    executor = LocalExecutor(
        session_factory=local_db,
        run_job=job,
        max_jobs=2,
        lock_path=tmp_path / "executor.lock",
        poll_interval=0.01,
    )
    await executor.start()
    try:
        for _ in range(10):
            executor.notify()

        async def done():
            async with local_db() as db:
                return all(
                    r.status == "success"
                    for r in (await db.scalars(select(Execution))).all()
                )

        await eventually(done)
        assert sorted(seen) == ids and maximum == 2
        assert (await executor.stats())["depth"] == 0
    finally:
        await executor.stop()


async def test_recovery_and_shutdown_preserve_pending_but_fail_interrupted(
    local_db, tmp_path
):
    old = (await add_jobs(local_db, status="running"))[0]
    retired = (await add_jobs(local_db, target_type="flow"))[0]
    first, second = await add_jobs(local_db, 2)
    entered = asyncio.Event()

    async def long_job(eid):
        async with local_db() as db:
            await db.execute(
                update(Execution).where(Execution.id == eid).values(status="running")
            )
            await db.commit()
        entered.set()
        await asyncio.Event().wait()

    executor = LocalExecutor(
        session_factory=local_db,
        run_job=long_job,
        max_jobs=1,
        lock_path=tmp_path / "executor.lock",
    )
    await executor.start()
    await asyncio.wait_for(entered.wait(), 5)
    await executor.stop()
    async with local_db() as db:
        rows = {r.id: r for r in (await db.scalars(select(Execution))).all()}
        assert (
            rows[old].status == rows[retired].status == rows[first].status == "failed"
        )
        assert rows[second].status == "pending"
        assert rows[first].finished_at and "停止" in rows[first].logs

    recovered = []

    async def complete(eid):
        recovered.append(eid)
        async with local_db() as db:
            await db.execute(
                update(Execution).where(Execution.id == eid).values(status="success")
            )
            await db.commit()

    executor.run_job = complete
    await executor.start()
    try:

        async def done():
            async with local_db() as db:
                return (await db.get(Execution, second)).status == "success"

        await eventually(done)
        assert recovered == [second]
    finally:
        await executor.stop()


async def test_second_local_service_is_rejected_before_recovery(local_db, tmp_path):
    options = {"session_factory": local_db, "lock_path": tmp_path / "executor.lock"}
    first, second = LocalExecutor(**options), LocalExecutor(**options)
    await first.start()
    try:
        with pytest.raises(RuntimeError, match="仅允许一个服务进程"):
            await second.start()
        assert first.running
    finally:
        await first.stop()
    await second.start()
    await second.stop()


async def test_local_queue_never_creates_redis_connections(
    local_db, tmp_path, monkeypatch
):
    from app import task_queue
    from app.services import local_execution_service as local

    executor = LocalExecutor(
        session_factory=local_db, lock_path=tmp_path / "executor.lock"
    )
    monkeypatch.setattr(local, "local_executor", executor)
    monkeypatch.setattr(task_queue.settings, "execution_backend", "local")
    connect = AsyncMock(side_effect=AssertionError("Redis must not be used"))
    monkeypatch.setattr(task_queue, "create_pool", connect)
    with pytest.raises(task_queue.QueueUnavailableError, match="未启动"):
        await task_queue.enqueue_script_run(1)
    await task_queue.start_execution_backend()
    try:
        await task_queue.enqueue_script_run(1)
        stats = await task_queue.queue_stats()
        assert stats["available"] and stats["backend"] == "local"
        with pytest.raises(task_queue.QueueUnavailableError, match="不使用 Redis"):
            await task_queue.get_pool()
    finally:
        await task_queue.stop_execution_backend()
    connect.assert_not_awaited()


async def test_local_logs_are_persisted_and_streamed_without_redis(
    local_db, monkeypatch
):
    from app.services import log_bus, log_stream_service as stream

    eid = (await add_jobs(local_db, status="running"))[0]
    monkeypatch.setattr(log_bus.settings, "execution_backend", "local")
    monkeypatch.setattr(log_bus, "AsyncSessionLocal", local_db)
    monkeypatch.setattr(stream, "AsyncSessionLocal", local_db)
    monkeypatch.setattr(stream, "_POLL_INTERVAL", 0.01)
    redis = AsyncMock(side_effect=AssertionError("Redis must not be used"))
    monkeypatch.setattr(log_bus, "_get_redis", redis)
    monkeypatch.setattr(stream, "get_pool", redis)

    class Socket:
        def __init__(self):
            self.lines = []
            self.closed = False

        async def accept(self):
            pass

        async def send_text(self, line):
            self.lines.append(line)

        async def close(self):
            self.closed = True

    socket = Socket()
    bus = log_bus.ExecutionLogBus(eid, flush_interval=0.02)
    await bus.start()
    ws = asyncio.create_task(stream.stream_execution_logs(socket, eid))
    try:
        bus.append("first\n")

        async def received():
            return socket.lines == ["first\n"]

        await eventually(received)
        bus.append("second\n")
        await bus.finalize()
        async with local_db() as db:
            await db.execute(
                update(Execution).where(Execution.id == eid).values(status="success")
            )
            await db.commit()
        await bus.close()
        await asyncio.wait_for(ws, 5)
        assert socket.lines == ["first\n", "second\n"] and socket.closed
        redis.assert_not_awaited()
    finally:
        ws.cancel()
        await asyncio.gather(ws, return_exceptions=True)
        await bus.close()
