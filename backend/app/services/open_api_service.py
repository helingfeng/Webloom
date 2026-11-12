"""开放平台调用日志与旧版通用采集接口的归属查询。"""

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.open_platform import OpenApiLog


# ---------- 调用日志（静默落库，镜像 query_history 约定）----------


async def record_open_log(
    db: AsyncSession,
    *,
    app_id: int | None,
    app_key: str,
    path: str,
    method: str,
    status_code: int,
    success: bool,
    execution_id: int | None = None,
    request_ip: str = "",
    detail: str = "",
) -> None:
    log = OpenApiLog(
        app_id=app_id,
        app_key=app_key,
        path=path,
        method=method,
        status_code=status_code,
        success=success,
        execution_id=execution_id,
        request_ip=request_ip,
        detail=detail,
    )
    db.add(log)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()


async def get_logs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    app_id: int | None = None,
    success: bool | None = None,
) -> list[OpenApiLog]:
    stmt = select(OpenApiLog)
    if app_id is not None:
        stmt = stmt.where(OpenApiLog.app_id == app_id)
    if success is not None:
        stmt = stmt.where(OpenApiLog.success == success)
    result = await db.execute(
        stmt.order_by(OpenApiLog.id.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


async def count_logs(
    db: AsyncSession, app_id: int | None = None, success: bool | None = None
) -> int:
    stmt = select(func.count(OpenApiLog.id))
    if app_id is not None:
        stmt = stmt.where(OpenApiLog.app_id == app_id)
    if success is not None:
        stmt = stmt.where(OpenApiLog.success == success)
    result = await db.execute(stmt)
    return result.scalar_one()


async def clear_logs(db: AsyncSession) -> int:
    result = await db.execute(delete(OpenApiLog))
    await db.commit()
    return result.rowcount or 0


# ---------- 采集触发归属查询 ----------


async def owned_execution_ids(
    db: AsyncSession, app_id: int, limit: int = 50, script_path_only: bool = True
) -> list[int]:
    """该应用通过采集触发接口发起过的 execution_id（新→旧）"""
    stmt = select(OpenApiLog.execution_id).where(
        OpenApiLog.app_id == app_id,
        OpenApiLog.execution_id.is_not(None),
        OpenApiLog.success == True,  # noqa: E712
    )
    if script_path_only:
        stmt = stmt.where(OpenApiLog.path == "/open/api/v1/collect/trigger")
    result = await db.execute(stmt.order_by(OpenApiLog.id.desc()).limit(limit))
    return [eid for (eid,) in result.all()]
