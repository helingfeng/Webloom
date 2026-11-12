"""worker job 业务体的真实路径冒烟：捕获导入/引用类错误（如 NameError）

LogBus 的默认落库/发布指向测试用 SQLite 会话与假 Redis，
避免冒烟测试把日志写进真实 MySQL / Redis。
"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.services.log_bus as log_bus
import app.services.script_run_service as script_run_service
from app.models.execution import Execution
from tests.conftest import FakeRedis


@pytest.fixture
def sqlite_session_maker(db_engine):
    return async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _use_sqlite(monkeypatch, sqlite_session_maker):
    monkeypatch.setattr(script_run_service, "AsyncSessionLocal", sqlite_session_maker)
    monkeypatch.setattr(log_bus, "AsyncSessionLocal", sqlite_session_maker)
    monkeypatch.setattr(log_bus, "_redis_client", FakeRedis())


def _execution(target_type: str = "script", **kwargs) -> Execution:
    defaults = dict(
        target_type=target_type,
        target_id=999,  # 不存在的脚本
        mode="manual",
        inputs={},
        status="pending",
        logs="",
        outputs={},
        started_at=datetime.now(),
    )
    defaults.update(kwargs)
    return Execution(**defaults)


async def test_run_script_execution_missing_returns_missing(sqlite_session_maker):
    async with sqlite_session_maker() as session:
        pass
    result = await script_run_service.run_script_execution(424242)
    assert result == {"status": "missing"}


async def test_run_script_execution_deleted_script_marks_failed(sqlite_session_maker):
    async with sqlite_session_maker() as session:
        session.add(_execution())
        await session.commit()
        from sqlalchemy import select

        eid = (await session.execute(select(Execution))).scalars().one().id

    result = await script_run_service.run_script_execution(eid)
    assert result["status"] == "failed"

    async with sqlite_session_maker() as session:
        from sqlalchemy import select

        row = (await session.execute(select(Execution))).scalars().one()
        assert row.status == "failed"
        assert "不存在" in row.logs
        assert row.finished_at is not None


async def test_retired_execution_never_runs_script(sqlite_session_maker):
    async with sqlite_session_maker() as session:
        execution = _execution(target_type="flow")
        session.add(execution)
        await session.commit()
        eid = execution.id
    result = await script_run_service.run_script_execution(eid)
    assert result == {"status": "failed"}
    async with sqlite_session_maker() as session:
        execution = await session.get(Execution, eid)
        assert "已停用" in execution.logs
        assert execution.finished_at is not None
