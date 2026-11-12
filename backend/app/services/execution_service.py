from sqlalchemy import delete, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.engine.runner import cleanup_execution_temp_files
from app.models.execution import Execution
from app.models.script import Script


def _apply_workspace_filter(stmt, workspace_id: int | None):
    """按脚本所属空间过滤；未指定空间时仍可查看历史执行记录。"""
    if workspace_id is None:
        return stmt
    return stmt.join(
        Script,
        and_(Execution.target_type == "script", Execution.target_id == Script.id),
    ).where(Script.workspace_id == workspace_id)


async def get_executions(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    workspace_id: int | None = None,
    script_id: int | None = None,
) -> list[Execution]:
    stmt = _apply_workspace_filter(select(Execution), workspace_id)
    if script_id is not None:
        stmt = stmt.where(
            and_(Execution.target_type == "script", Execution.target_id == script_id)
        )
    result = await db.execute(
        stmt.order_by(Execution.id.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


async def count_executions(
    db: AsyncSession, workspace_id: int | None = None, script_id: int | None = None
) -> int:
    stmt = _apply_workspace_filter(select(func.count(Execution.id)), workspace_id)
    if script_id is not None:
        stmt = stmt.where(
            and_(Execution.target_type == "script", Execution.target_id == script_id)
        )
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_execution(db: AsyncSession, execution_id: int) -> Execution | None:
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    return result.scalar_one_or_none()


async def delete_execution(db: AsyncSession, execution: Execution) -> None:
    await db.delete(execution)
    await db.commit()
    cleanup_execution_temp_files(execution.id)


async def clear_executions(db: AsyncSession) -> int:
    ids = (await db.execute(select(Execution.id))).scalars().all()
    result = await db.execute(delete(Execution))
    await db.commit()
    for execution_id in ids:
        cleanup_execution_temp_files(execution_id)
    return result.rowcount or 0
