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


async def test_queued_job_uses_submission_snapshot_and_effective_url(
    sqlite_session_maker, monkeypatch
):
    from unittest.mock import AsyncMock
    from app.models.script import Script
    from app.schemas.script import ScriptUpdate
    from app.services import script_service

    monkeypatch.setattr(script_run_service, "enqueue_script_run", AsyncMock())
    seen = {}

    async def execute(script, inputs, *args, **kwargs):
        seen.update(code=script.code, inputs=inputs, headless=kwargs["headless"])
        return "", {"snapshot": True}

    globals_mock = AsyncMock(return_value=({}, {}, {}, []))
    monkeypatch.setattr(script_run_service, "execute_script_code", execute)
    monkeypatch.setattr(
        script_run_service.global_variable_service,
        "get_active_globals_grouped",
        globals_mock,
    )
    async with sqlite_session_maker() as db:
        script = Script(
            name="saved",
            code='print("saved")',
            workspace_id=1,
            start_url="https://old.test",
            inherit_global=True,
            inputs=[
                {"name": "url", "type": "string"},
                {"name": "count", "type": "number", "default": "2"},
            ],
            outputs=[],
        )
        db.add(script)
        await db.commit()
        await db.refresh(script)
        task = await script_run_service.start_script_execution(
            db, script, inputs={"url": "https://new.test"}, headless=False
        )
        execution_id = task.id
        script.code = 'print("changed after enqueue")'
        script.start_url = "https://changed.test"
        script.headless = True
        await db.commit()
    result = await script_run_service.run_script_execution(execution_id)
    assert result["status"] == "success"
    assert seen == {
        "code": 'print("saved")',
        "inputs": {"url": "https://new.test", "count": 2},
        "headless": False,
    }
    assert globals_mock.call_args.args[1] == "https://new.test"
