from sqlalchemy import delete, func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.execution import Execution
from app.models.script import Script
from app.models.flow import Flow


def _apply_workspace_filter(stmt, workspace_id: int | None):
    """执行记录经多态关联（target_type/target_id）OR-join script/flow 按空间过滤"""
    if workspace_id is None:
        return stmt
    return (
        stmt.outerjoin(
            Script,
            and_(Execution.target_type == "script", Execution.target_id == Script.id),
        )
        .outerjoin(
            Flow,
            and_(Execution.target_type == "flow", Execution.target_id == Flow.id),
        )
        .where(or_(Script.workspace_id == workspace_id, Flow.workspace_id == workspace_id))
    )


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
    result = await db.execute(stmt.order_by(Execution.id.desc()).offset(skip).limit(limit))
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


async def clear_executions(db: AsyncSession) -> int:
    result = await db.execute(delete(Execution))
    await db.commit()
    return result.rowcount or 0
