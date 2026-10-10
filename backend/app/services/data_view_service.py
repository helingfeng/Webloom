import asyncio
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.data_view import DataView
from app.models.datasource import Datasource
from app.schemas.data_view import DataViewCreate, DataViewUpdate
from app.schemas.datasource import QueryResult
from app.services import datasource_service
from app.services.datasource_query_service import (
    execute_readonly_query,
    validate_readonly_sql,
)

# 单次预取并行执行的外部 SQL 上限（数据源侧连接池才是真正瓶颈，这里防视图过多时瞬间打满）
VIEW_CONCURRENCY = 4

# 视图结果 TTL 缓存（仅 worker 侧预取使用）：(view_id, updated_at) -> (过期时刻, 行数据)
# updated_at 参与键：编辑视图后自然换键，避免读到旧 SQL 的结果
_view_cache: dict[tuple[int, object], tuple[float, list[dict] | dict]] = {}
# 并发去重：同一视图的并发预取共享同一次查询（防 thundering herd）
_inflight: dict[tuple[int, object], asyncio.Future] = {}


async def get_data_views(db: AsyncSession) -> list[DataView]:
    result = await db.execute(select(DataView).order_by(DataView.id))
    return result.scalars().all()


async def get_data_view(db: AsyncSession, dv_id: int) -> DataView | None:
    result = await db.execute(select(DataView).where(DataView.id == dv_id))
    return result.scalar_one_or_none()


async def get_data_view_by_slug(db: AsyncSession, slug: str) -> DataView | None:
    result = await db.execute(select(DataView).where(DataView.slug == slug))
    return result.scalar_one_or_none()


async def _validate_slug(
    db: AsyncSession, slug: str, exclude_id: int | None = None
) -> None:
    result = await db.execute(select(DataView).where(DataView.slug == slug))
    existing = result.scalar_one_or_none()
    if existing is not None and existing.id != exclude_id:
        raise ValueError(f"slug '{slug}' 已被使用")


async def _validate_datasource(db: AsyncSession, datasource_id: int) -> None:
    ds = await datasource_service.get_datasource(db, datasource_id)
    if not ds:
        raise ValueError(f"数据源 {datasource_id} 不存在")


async def create_data_view(db: AsyncSession, dv_in: DataViewCreate) -> DataView:
    await _validate_slug(db, dv_in.slug)
    validate_readonly_sql(dv_in.sql)
    await _validate_datasource(db, dv_in.datasource_id)
    dv = DataView(**dv_in.model_dump())
    db.add(dv)
    await db.commit()
    await db.refresh(dv)
    return dv


async def update_data_view(
    db: AsyncSession, dv: DataView, dv_in: DataViewUpdate
) -> DataView:
    data = dv_in.model_dump(exclude_unset=True)
    if data.get("slug") and data["slug"] != dv.slug:
        await _validate_slug(db, data["slug"], exclude_id=dv.id)
    if data.get("sql") and data["sql"] != dv.sql:
        validate_readonly_sql(data["sql"])
    if data.get("datasource_id") and data["datasource_id"] != dv.datasource_id:
        await _validate_datasource(db, data["datasource_id"])
    for key, value in data.items():
        setattr(dv, key, value)
    await db.commit()
    await db.refresh(dv)
    return dv


async def delete_data_view(db: AsyncSession, dv: DataView) -> None:
    await db.delete(dv)
    await db.commit()


async def run_data_view(db: AsyncSession, dv: DataView) -> QueryResult:
    """管理端运行预览（不受 enabled 限制，方便调试停用中的视图）"""
    ds = await datasource_service.get_datasource(db, dv.datasource_id)
    if not ds:
        return QueryResult(
            success=False,
            statement_type="query",
            error="关联数据源不存在或已删除",
        )
    return await execute_readonly_query(ds, dv.sql, database=dv.database)


async def _collect_single_view(
    ds: Datasource | None, dv: DataView
) -> list[dict] | dict:
    """执行单个视图查询；失败返回 {"_error": ...}，不抛异常"""
    if ds is None:
        return {"_error": f"关联数据源不存在或已删除（视图 {dv.name}）"}
    qr = await execute_readonly_query(ds, dv.sql, database=dv.database)
    if not qr.success:
        return {"_error": qr.error or "查询失败"}
    return [dict(zip(qr.columns, row)) for row in qr.rows]


async def _load_enabled_views_with_ds(
    db: AsyncSession,
) -> list[tuple[DataView, Datasource | None]]:
    """一次取回全部启用视图 + 关联数据源映射（替代逐视图查一次 datasource）"""
    result = await db.execute(
        select(DataView).where(DataView.enabled == True)  # noqa: E712
    )
    views = result.scalars().all()
    if not views:
        return []
    ds_ids = {dv.datasource_id for dv in views}
    ds_result = await db.execute(select(Datasource).where(Datasource.id.in_(ds_ids)))
    ds_map = {ds.id: ds for ds in ds_result.scalars().all()}
    return [(dv, ds_map.get(dv.datasource_id)) for dv in views]


async def collect_view_data(db: AsyncSession) -> dict[str, list[dict] | dict]:
    """预取所有启用数据视图的查询结果，脚本执行时注入 DATA_VIEWS。

    形状与外部取数接口一致：{slug: [ {col: val}, ... ]}。
    单个视图失败不影响脚本执行，值为 {"_error": 原因}。
    视图 SQL 并行执行（受 VIEW_CONCURRENCY 限制），不使用缓存。
    """
    pairs = await _load_enabled_views_with_ds(db)
    if not pairs:
        return {}
    sem = asyncio.Semaphore(VIEW_CONCURRENCY)

    async def _run(dv: DataView, ds: Datasource | None):
        async with sem:
            return dv.slug, await _collect_single_view(ds, dv)

    return dict(await asyncio.gather(*[_run(dv, ds) for dv, ds in pairs]))


async def _get_view_rows_cached(
    ds: Datasource | None, dv: DataView, ttl: float
) -> list[dict] | dict:
    key = (dv.id, dv.updated_at)
    now = time.monotonic()
    cached = _view_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]
    fut = _inflight.get(key)
    if fut is not None:
        # 并发请求共享同一次查询；shield 保证取消方不影响他人
        return await asyncio.shield(fut)
    fut = asyncio.get_running_loop().create_future()
    _inflight[key] = fut
    try:
        try:
            rows = await _collect_single_view(ds, dv)
        except asyncio.CancelledError:
            # 取消方退出，但共享 fut 必须有结果，否则其他等待者永久挂起
            if not fut.done():
                fut.set_result({"_error": "查询被取消"})
            raise
        except Exception as exc:  # 外部数据源异常不应影响脚本执行
            rows = {"_error": str(exc)}
        if not (isinstance(rows, dict) and "_error" in rows):
            _view_cache[key] = (time.monotonic() + ttl, rows)
            # 同视图编辑后旧键立即丢弃，避免缓存无限增长
            for old_key in [k for k in _view_cache if k[0] == dv.id and k != key]:
                _view_cache.pop(old_key, None)
        if not fut.done():
            fut.set_result(rows)
        return rows
    finally:
        _inflight.pop(key, None)


async def collect_view_data_cached(
    db: AsyncSession, *, ttl: float | None = None
) -> dict[str, list[dict] | dict]:
    """带 TTL 缓存的视图预取：并发执行去重复计算，高并发跑脚本时避免重复执行外部 SQL。

    仅缓存成功结果（失败视图下次重试）；管理端预览与公开取数不走此函数。
    """
    if ttl is None:
        ttl = float(settings.cache_ttl_seconds)
    if ttl <= 0:
        return await collect_view_data(db)
    pairs = await _load_enabled_views_with_ds(db)
    if not pairs:
        return {}

    async def _run(dv: DataView, ds: Datasource | None):
        return dv.slug, await _get_view_rows_cached(ds, dv, ttl)

    return dict(await asyncio.gather(*[_run(dv, ds) for dv, ds in pairs]))
