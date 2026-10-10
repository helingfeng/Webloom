"""数据源连接管理：per-key 锁并行性、按 key 粒度失效"""

import asyncio
import time
from types import SimpleNamespace

from app.services.datasource_query_service import DatasourceConnectionManager


def _ds(ds_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=ds_id, database="db", host="127.0.0.1", port=3306, user="root", password=""
    )


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


async def test_different_keys_run_parallel():
    """不同 (datasource, database) 的建连不互相阻塞"""
    manager = DatasourceConnectionManager()
    delay = 0.05

    async def slow_build(key):
        lock = await manager._key_lock(key)
        async with lock:
            await asyncio.sleep(delay)
            engine = _FakeEngine()
            manager._engines[key] = engine
            return engine

    start = time.perf_counter()
    await asyncio.gather(slow_build((1, "a")), slow_build((1, "b")))
    elapsed = time.perf_counter() - start
    assert elapsed < delay * 1.9  # 串行则 ≥ 2*delay


async def test_same_key_serialized(monkeypatch):
    manager = DatasourceConnectionManager()
    order: list[str] = []

    async def build(key):
        lock = await manager._key_lock(key)
        async with lock:
            order.append("enter")
            await asyncio.sleep(0.02)
            order.append("exit")
            return _FakeEngine()

    await asyncio.gather(build((1, "a")), build((1, "a")))
    # 同 key 严格串行：enter/exit 交替
    assert order == ["enter", "exit", "enter", "exit"]


async def test_invalidate_engine_only_disposes_target_key():
    manager = DatasourceConnectionManager()
    engine_a = _FakeEngine()
    engine_b = _FakeEngine()
    manager._engines[(1, "a")] = engine_a
    manager._engines[(1, "b")] = engine_b

    await manager.invalidate_engine(1, "a")
    assert engine_a.disposed
    assert not engine_b.disposed
    assert (1, "b") in manager._engines
    assert (1, "a") not in manager._engines


async def test_invalidate_disposes_whole_datasource():
    manager = DatasourceConnectionManager()
    engine_a = _FakeEngine()
    engine_b = _FakeEngine()
    engine_other = _FakeEngine()
    manager._engines[(1, "a")] = engine_a
    manager._engines[(1, "b")] = engine_b
    manager._engines[(2, "a")] = engine_other

    await manager.invalidate(1)
    assert engine_a.disposed and engine_b.disposed
    assert not engine_other.disposed
    assert list(manager._engines.keys()) == [(2, "a")]


async def test_invalidate_engine_none_falls_back_to_datasource():
    manager = DatasourceConnectionManager()
    engine_a = _FakeEngine()
    manager._engines[(1, "a")] = engine_a

    await manager.invalidate_engine(1, None)
    assert engine_a.disposed
    assert manager._engines == {}
