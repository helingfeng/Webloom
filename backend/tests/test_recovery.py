"""worker 启动恢复：running → failed（中断）；pending 超龄兜底重入队"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.worker as worker_mod
from app.models.execution import Execution
from tests.conftest import FakeRedis


@pytest.fixture
def sqlite_session_maker(db_engine):
    return async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _use_sqlite_session(monkeypatch, sqlite_session_maker):
    monkeypatch.setattr(worker_mod, "AsyncSessionLocal", sqlite_session_maker)


def _make_execution(**kwargs) -> Execution:
    _make_execution._counter += 1
    defaults = dict(
        id=_make_execution._counter,
        target_type="script",
        target_id=1,
        mode="manual",
        inputs={},
        status="pending",
        logs="",
        outputs={},
        started_at=datetime.now(),
    )
    defaults.update(kwargs)
    return Execution(**defaults)


_make_execution._counter = 0


async def test_running_marked_failed_on_startup(sqlite_session_maker):
    async with sqlite_session_maker() as session:
        session.add_all(
            [
                _make_execution(status="running", logs="start\n"),
                _make_execution(status="success"),
                _make_execution(status="pending"),
            ]
        )
        await session.commit()
        ids = [
            e.id
            for e in (await session.execute(select(Execution).order_by(Execution.id)))
            .scalars()
            .all()
        ]

    redis = FakeRedis()
    await worker_mod.recover_interrupted(redis)

    async with sqlite_session_maker() as session:
        rows = (
            (await session.execute(select(Execution).order_by(Execution.id)))
            .scalars()
            .all()
        )
        assert rows[0].status == "failed"
        assert "worker 重启，执行中断" in rows[0].logs
        assert rows[0].finished_at is not None
        assert rows[1].status == "success"  # 终态不动
        assert rows[2].status == "pending"  # pending 不在此处理
    # 残留 job 键被清理（arq:job: + arq:in-progress:）
    assert f"arq:job:exec:{ids[0]}" in redis.deleted
    assert f"arq:in-progress:exec:{ids[0]}" in redis.deleted


async def test_pending_stale_reenqueued(sqlite_session_maker, monkeypatch):
    old = datetime.now() - timedelta(seconds=300)
    async with sqlite_session_maker() as session:
        session.add_all(
            [
                _make_execution(status="pending", started_at=old),  # 超龄脚本 → 重入队
                _make_execution(status="pending"),  # 刚创建 → 不动
                _make_execution(
                    status="pending", target_type="flow"
                ),  # 历史流程 → 失败，不再入队
            ]
        )
        await session.commit()
        rows = (
            (await session.execute(select(Execution).order_by(Execution.id)))
            .scalars()
            .all()
        )
        stale_script_id, fresh_id, retired_id = rows[0].id, rows[1].id, rows[2].id

    enqueued: list[tuple[int, str]] = []

    async def fake_script(eid, headless_override=None):
        enqueued.append((eid, "script"))

    monkeypatch.setattr(worker_mod, "enqueue_script_run", fake_script)

    redis = FakeRedis()
    await worker_mod.recover_pending(redis)

    assert enqueued == [(stale_script_id, "script")]
    assert f"arq:job:exec:{retired_id}" in redis.deleted
    assert any(member == f"exec:{retired_id}" for _, member in redis.removed_jobs)
    async with sqlite_session_maker() as session:
        retired = await session.get(Execution, retired_id)
        assert retired.status == "failed"
        assert "已停用" in retired.logs
        assert retired.finished_at is not None
    assert (fresh_id, "script") not in enqueued


async def test_recover_pending_noop_when_nothing_stale(
    sqlite_session_maker, monkeypatch
):
    async with sqlite_session_maker() as session:
        session.add(_make_execution(status="pending"))  # 刚创建
        await session.commit()

    enqueued: list[int] = []

    async def fake_script(eid, headless_override=None):
        enqueued.append(eid)

    monkeypatch.setattr(worker_mod, "enqueue_script_run", fake_script)
    await worker_mod.recover_pending(FakeRedis())
    assert enqueued == []
