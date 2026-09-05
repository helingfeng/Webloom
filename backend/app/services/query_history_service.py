"""数据源工作台 SQL 执行历史：记录与查询。"""

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.query_history import QueryHistory
from app.schemas.datasource import QueryResult

HISTORY_ROWS_SAMPLE_LIMIT = 200  # 历史详情保留的结果行上限，防表膨胀


async def record_query(
    db: AsyncSession,
    datasource_id: int,
    database: str,
    sql: str,
    result: QueryResult,
) -> None:
    """落一条执行历史；rows 仅保留样本行。失败时静默回滚，不影响执行响应"""
    history = QueryHistory(
        datasource_id=datasource_id,
        database=database,
        sql=sql,
        success=result.success,
        statement_type=result.statement_type,
        columns=result.columns,
        rows=result.rows[:HISTORY_ROWS_SAMPLE_LIMIT],
        row_count=result.row_count,
        truncated=result.truncated,
        affected_rows=result.affected_rows,
        elapsed_ms=result.elapsed_ms,
        error=result.error,
    )
    db.add(history)
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()


async def get_histories(
    db: AsyncSession, datasource_id: int, skip: int = 0, limit: int = 20
) -> list[QueryHistory]:
    result = await db.execute(
        select(QueryHistory)
        .where(QueryHistory.datasource_id == datasource_id)
        .order_by(QueryHistory.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


async def count_histories(db: AsyncSession, datasource_id: int) -> int:
    result = await db.execute(
        select(func.count(QueryHistory.id)).where(
            QueryHistory.datasource_id == datasource_id
        )
    )
    return result.scalar_one()


async def get_history(db: AsyncSession, history_id: int) -> QueryHistory | None:
    result = await db.execute(
        select(QueryHistory).where(QueryHistory.id == history_id)
    )
    return result.scalar_one_or_none()


async def delete_history(db: AsyncSession, history: QueryHistory) -> None:
    await db.delete(history)
    await db.commit()


async def clear_histories(db: AsyncSession, datasource_id: int) -> int:
    result = await db.execute(
        delete(QueryHistory).where(QueryHistory.datasource_id == datasource_id)
    )
    await db.commit()
    return result.rowcount or 0


async def delete_histories_by_datasource(db: AsyncSession, datasource_id: int) -> None:
    """删除数据源时级联清理其历史记录"""
    await db.execute(
        delete(QueryHistory).where(QueryHistory.datasource_id == datasource_id)
    )
