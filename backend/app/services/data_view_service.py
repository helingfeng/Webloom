from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.data_view import DataView
from app.models.datasource import Datasource
from app.schemas.data_view import DataViewCreate, DataViewUpdate
from app.schemas.datasource import QueryResult
from app.services import datasource_service
from app.services.datasource_query_service import (
    execute_readonly_query,
    validate_readonly_sql,
)


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


async def collect_view_data(db: AsyncSession) -> dict[str, list[dict] | dict]:
    """预取所有启用数据视图的查询结果，脚本执行时注入 DATA_VIEWS。

    形状与外部取数接口一致：{slug: [ {col: val}, ... ]}。
    单个视图失败不影响脚本执行，值为 {"_error": 原因}。
    """
    result = await db.execute(
        select(DataView).where(DataView.enabled == True)
    )  # noqa: E712
    views = result.scalars().all()
    data: dict[str, list[dict] | dict] = {}
    for dv in views:
        ds = await datasource_service.get_datasource(db, dv.datasource_id)
        if not ds:
            data[dv.slug] = {"_error": f"关联数据源不存在或已删除（视图 {dv.name}）"}
            continue
        qr = await execute_readonly_query(ds, dv.sql, database=dv.database)
        if not qr.success:
            data[dv.slug] = {"_error": qr.error or "查询失败"}
        else:
            data[dv.slug] = [dict(zip(qr.columns, row)) for row in qr.rows]
    return data
