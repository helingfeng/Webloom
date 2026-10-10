"""数据视图并行预取 + TTL 缓存"""

import asyncio
from datetime import datetime

import pytest

from app.models.data_view import DataView
from app.models.datasource import Datasource
from app.schemas.datasource import QueryResult
from app.services import data_view_service


def _qr_ok(rows: list[tuple]) -> QueryResult:
    return QueryResult(
        success=True,
        statement_type="query",
        columns=["id"],
        rows=rows,
        row_count=len(rows),
        truncated=False,
    )


def _qr_err(msg: str) -> QueryResult:
    return QueryResult(success=False, statement_type="query", error=msg)


async def _seed_view(
    db, slug: str, sql: str = "SELECT 1", enabled: bool = True
) -> DataView:
    counter = next(_seed_view._ids)
    ds = Datasource(
        id=counter,
        name="ds",
        host="127.0.0.1",
        port=3306,
        user="root",
        password="",
        database="db",
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    dv = DataView(
        id=counter,
        name=slug,
        slug=slug,
        datasource_id=ds.id,
        database="",
        sql=sql,
        enabled=enabled,
    )
    db.add(dv)
    await db.commit()
    await db.refresh(dv)
    return dv


_seed_view._ids = iter(range(1, 10_000))


@pytest.fixture(autouse=True)
def _clear_cache():
    data_view_service._view_cache.clear()
    data_view_service._inflight.clear()
    yield
    data_view_service._view_cache.clear()
    data_view_service._inflight.clear()


async def test_parallel_collect_all_views(db, monkeypatch):
    await _seed_view(db, "a")
    await _seed_view(db, "b")
    calls: list[str] = []

    async def fake_query(ds, sql, database=None):
        calls.append(sql)
        await asyncio.sleep(0.02)
        return _qr_ok([(1,)])

    monkeypatch.setattr(data_view_service, "execute_readonly_query", fake_query)
    data = await data_view_service.collect_view_data(db)
    assert data == {"a": [{"id": 1}], "b": [{"id": 1}]}
    assert sorted(calls) == ["SELECT 1", "SELECT 1"]


async def test_collect_error_isolation(db, monkeypatch):
    await _seed_view(db, "good")
    dv_bad = await _seed_view(db, "bad", sql="SELECT bad")

    async def fake_query(ds, sql, database=None):
        if sql == "SELECT bad":
            return _qr_err("boom")
        return _qr_ok([(1,)])

    monkeypatch.setattr(data_view_service, "execute_readonly_query", fake_query)
    data = await data_view_service.collect_view_data(db)
    assert data["good"] == [{"id": 1}]
    assert data["bad"] == {"_error": "boom"}
    assert dv_bad.id  # noop keep linter calm


async def test_cache_hit_within_ttl(db, monkeypatch):
    dv = await _seed_view(db, "v")
    calls = 0

    async def fake_query(ds, sql, database=None):
        nonlocal calls
        calls += 1
        return _qr_ok([(calls,)])

    monkeypatch.setattr(data_view_service, "execute_readonly_query", fake_query)
    first = await data_view_service.collect_view_data_cached(db, ttl=60)
    second = await data_view_service.collect_view_data_cached(db, ttl=60)
    assert calls == 1
    assert first == second == {"v": [{"id": 1}]}
    assert dv.id


async def test_cache_expired_refetch(db, monkeypatch):
    await _seed_view(db, "v")
    calls = 0
    clock = {"t": 1000.0}

    async def fake_query(ds, sql, database=None):
        nonlocal calls
        calls += 1
        return _qr_ok([(calls,)])

    monkeypatch.setattr(data_view_service, "execute_readonly_query", fake_query)

    real_monotonic = data_view_service.time.monotonic

    def fake_monotonic():
        return clock["t"]

    monkeypatch.setattr(data_view_service.time, "monotonic", fake_monotonic)
    await data_view_service.collect_view_data_cached(db, ttl=10)
    clock["t"] += 11  # 超过 TTL
    await data_view_service.collect_view_data_cached(db, ttl=10)
    assert calls == 2
    monkeypatch.setattr(data_view_service.time, "monotonic", real_monotonic)


async def test_updated_at_changes_cache_key(db, monkeypatch):
    dv = await _seed_view(db, "v")
    calls = 0

    async def fake_query(ds, sql, database=None):
        nonlocal calls
        calls += 1
        return _qr_ok([(calls,)])

    monkeypatch.setattr(data_view_service, "execute_readonly_query", fake_query)
    await data_view_service.collect_view_data_cached(db, ttl=60)
    # 模拟编辑视图：updated_at 变化 → 新键 → 重新查询
    dv.updated_at = datetime.now()
    await data_view_service.collect_view_data_cached(db, ttl=60)
    assert calls == 2
    # 旧键已被清理
    assert all(
        k[0] == dv.id and k[1] == dv.updated_at for k in data_view_service._view_cache
    )


async def test_failed_view_not_cached(db, monkeypatch):
    await _seed_view(db, "v")
    calls = 0

    async def fake_query(ds, sql, database=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _qr_err("boom")
        return _qr_ok([(1,)])

    monkeypatch.setattr(data_view_service, "execute_readonly_query", fake_query)
    first = await data_view_service.collect_view_data_cached(db, ttl=60)
    assert first == {"v": {"_error": "boom"}}
    second = await data_view_service.collect_view_data_cached(db, ttl=60)
    assert second == {"v": [{"id": 1}]}  # 失败不缓存，下次重试
    assert calls == 2


async def test_inflight_dedup_concurrent_requests(db, monkeypatch):
    await _seed_view(db, "v")
    calls = 0
    gate = asyncio.Event()

    async def slow_query(ds, sql, database=None):
        nonlocal calls
        calls += 1
        await gate.wait()
        return _qr_ok([(1,)])

    monkeypatch.setattr(data_view_service, "execute_readonly_query", slow_query)

    async def release():
        await asyncio.sleep(0.05)
        gate.set()

    results = await asyncio.gather(
        data_view_service.collect_view_data_cached(db, ttl=60),
        data_view_service.collect_view_data_cached(db, ttl=60),
        data_view_service.collect_view_data_cached(db, ttl=60),
        release(),
    )
    assert calls == 1  # 三个并发请求共享同一次查询
    assert results[0] == results[1] == results[2] == {"v": [{"id": 1}]}


async def test_ttl_zero_bypasses_cache(db, monkeypatch):
    await _seed_view(db, "v")
    calls = 0

    async def fake_query(ds, sql, database=None):
        nonlocal calls
        calls += 1
        return _qr_ok([(calls,)])

    monkeypatch.setattr(data_view_service, "execute_readonly_query", fake_query)
    await data_view_service.collect_view_data_cached(db, ttl=0)
    await data_view_service.collect_view_data_cached(db, ttl=0)
    assert calls == 2
