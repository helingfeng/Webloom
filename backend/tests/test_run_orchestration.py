"""health 接口与 run 入队编排：排队状态、队列不可用留痕"""

import pytest
from fastapi.testclient import TestClient

import app.main as app_main
from app.models.execution import Execution
from app.models.script import Script
from app.services import script_run_service
from app.task_queue import QueueUnavailableError


def test_health_reports_queue_stats(monkeypatch):
    async def fake_stats():
        return {"available": False, "depth": None, "worker_alive": False}

    monkeypatch.setattr(app_main, "queue_stats", fake_stats)
    client = TestClient(app_main.app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["queue"] == {"available": False, "depth": None, "worker_alive": False}


async def test_start_script_execution_enqueues_pending(db, monkeypatch):
    script = Script(
        id=1,
        workspace_id=1,
        name="s",
        code="pass",
        start_url="",
        inputs=[{"name": "a", "type": "number", "required": False}],
        outputs=[],
        inherit_global=False,
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)

    enqueued: list[tuple[int, object]] = []

    async def fake_enqueue(execution_id, headless_override=None):
        enqueued.append((execution_id, headless_override))

    monkeypatch.setattr(script_run_service, "enqueue_script_run", fake_enqueue)
    execution = await script_run_service.start_script_execution(
        db, script, mode="manual", inputs={"a": 1}, headless=True
    )
    assert execution.status == "pending"
    assert enqueued == [(execution.id, True)]


async def test_start_script_execution_marks_failed_when_queue_down(db, monkeypatch):
    script = Script(
        workspace_id=1,
        name="s",
        code="pass",
        start_url="",
        inputs=[],
        outputs=[],
        inherit_global=False,
    )
    db.add(script)
    await db.commit()
    await db.refresh(script)

    async def broken_enqueue(execution_id, headless_override=None):
        raise QueueUnavailableError("connection refused")

    monkeypatch.setattr(script_run_service, "enqueue_script_run", broken_enqueue)
    with pytest.raises(QueueUnavailableError):
        await script_run_service.start_script_execution(db, script, mode="manual")

    # 留痕为 failed，不会出现永远 pending 的脏数据
    from sqlalchemy import select

    row = (await db.execute(select(Execution))).scalars().one()
    assert row.status == "failed"
    assert "执行队列不可用" in row.logs
    assert row.finished_at is not None
