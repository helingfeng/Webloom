"""task_queue：入队参数、队列健康降级"""

import pytest

from app import task_queue


class _FakePool:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.zcard_value = 0
        self.kv: dict = {}

    async def enqueue_job(self, function, *args, _job_id=None, **kwargs):
        self.calls.append(
            {"function": function, "args": args, "_job_id": _job_id, **kwargs}
        )
        return None

    async def zcard(self, key: str) -> int:
        return self.zcard_value

    async def get(self, key: str):
        return self.kv.get(key)


@pytest.fixture(autouse=True)
def _reset_pool():
    task_queue._pool = None
    yield
    task_queue._pool = None


async def test_enqueue_script_run_uses_expected_job(monkeypatch):
    pool = _FakePool()

    async def fake_get_pool():
        return pool

    monkeypatch.setattr(task_queue, "get_pool", fake_get_pool)
    await task_queue.enqueue_script_run(7, headless_override=True)
    call = pool.calls[0]
    assert call["function"] == "run_script_execution"
    assert call["args"] == (7, True)
    assert call["_job_id"] == "exec:7"


async def test_job_key_format():
    assert task_queue.job_key(3) == "arq:job:exec:3"


async def test_queue_stats_degrades_when_redis_down(monkeypatch):
    async def broken_get_pool():
        raise task_queue.QueueUnavailableError("connection refused")

    monkeypatch.setattr(task_queue, "get_pool", broken_get_pool)
    stats = await task_queue.queue_stats()
    assert stats == {"available": False, "depth": None, "worker_alive": False}


async def test_queue_stats_reports_depth_and_worker(monkeypatch):
    pool = _FakePool()
    pool.zcard_value = 3
    pool.kv[task_queue.WORKER_HEARTBEAT_KEY] = "1"

    async def fake_get_pool():
        return pool

    monkeypatch.setattr(task_queue, "get_pool", fake_get_pool)
    stats = await task_queue.queue_stats()
    assert stats == {"available": True, "depth": 3, "worker_alive": True}
