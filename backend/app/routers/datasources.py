from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.datasource import Datasource
from app.schemas.datasource import (
    DatasourceColumn,
    DatasourceCreate,
    DatasourceOut,
    DatasourceTable,
    DatasourceTestRequest,
    DatasourceTestResult,
    DatasourceUpdate,
    QueryHistoryDetail,
    QueryHistoryPage,
    QueryRequest,
    QueryResult,
)
from app.services import (
    datasource_query_service,
    datasource_service,
    query_history_service,
)

router = APIRouter()


async def _get_ds_or_404(db: AsyncSession, ds_id: int) -> Datasource:
    ds = await datasource_service.get_datasource(db, ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")
    return ds


@router.get("", response_model=list[DatasourceOut])
async def list_datasources(db: AsyncSession = Depends(get_db)) -> Any:
    return await datasource_service.get_datasources(db)


@router.post("", response_model=DatasourceOut, status_code=201)
async def create_datasource(
    ds_in: DatasourceCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    return await datasource_service.create_datasource(db, ds_in)


# 注意：/test 静态路由必须声明在 /{ds_id} 类路由之前
@router.post("/test", response_model=DatasourceTestResult)
async def test_datasource(req: DatasourceTestRequest) -> Any:
    return await datasource_query_service.test_connection(req)


@router.put("/{ds_id}", response_model=DatasourceOut)
async def update_datasource(
    ds_id: int, ds_in: DatasourceUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    ds = await _get_ds_or_404(db, ds_id)
    return await datasource_service.update_datasource(db, ds, ds_in)


@router.delete("/{ds_id}", status_code=204)
async def delete_datasource(ds_id: int, db: AsyncSession = Depends(get_db)) -> None:
    ds = await _get_ds_or_404(db, ds_id)
    await datasource_service.delete_datasource(db, ds)


@router.post("/{ds_id}/test", response_model=DatasourceTestResult)
async def test_datasource_by_id(ds_id: int, db: AsyncSession = Depends(get_db)) -> Any:
    ds = await _get_ds_or_404(db, ds_id)
    return await datasource_query_service.test_connection(
        DatasourceTestRequest(
            host=ds.host,
            port=ds.port,
            user=ds.user,
            password=ds.password,
            database=ds.database,
        )
    )


@router.get("/{ds_id}/databases", response_model=list[str])
async def list_databases(ds_id: int, db: AsyncSession = Depends(get_db)) -> Any:
    ds = await _get_ds_or_404(db, ds_id)
    try:
        return await datasource_query_service.list_databases(ds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"获取数据库列表失败: {exc}")


@router.get("/{ds_id}/tables", response_model=list[DatasourceTable])
async def list_tables(
    ds_id: int,
    database: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    ds = await _get_ds_or_404(db, ds_id)
    try:
        return await datasource_query_service.list_tables(ds, database)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"获取表列表失败: {exc}")


@router.get(
    "/{ds_id}/tables/{table_name}/schema", response_model=list[DatasourceColumn]
)
async def get_table_schema(
    ds_id: int,
    table_name: str,
    database: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    ds = await _get_ds_or_404(db, ds_id)
    try:
        return await datasource_query_service.get_table_schema(ds, table_name, database)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"获取表结构失败: {exc}")


@router.post("/{ds_id}/query", response_model=QueryResult)
async def run_query(
    ds_id: int, req: QueryRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    ds = await _get_ds_or_404(db, ds_id)
    result = await datasource_query_service.execute_query(
        ds, req.sql, database=req.database
    )
    await query_history_service.record_query(
        db, ds.id, req.database or ds.database, req.sql, result
    )
    return result


@router.get("/{ds_id}/query-history", response_model=QueryHistoryPage)
async def list_query_history(
    ds_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Any:
    await _get_ds_or_404(db, ds_id)
    items = await query_history_service.get_histories(
        db, ds_id, skip=skip, limit=limit
    )
    total = await query_history_service.count_histories(db, ds_id)
    return {"items": items, "total": total}


@router.get("/{ds_id}/query-history/{history_id}", response_model=QueryHistoryDetail)
async def get_query_history_detail(
    ds_id: int, history_id: int, db: AsyncSession = Depends(get_db)
) -> Any:
    await _get_ds_or_404(db, ds_id)
    history = await query_history_service.get_history(db, history_id)
    if not history or history.datasource_id != ds_id:
        raise HTTPException(status_code=404, detail="Query history not found")
    return history


@router.delete("/{ds_id}/query-history/{history_id}", status_code=204)
async def delete_query_history(
    ds_id: int, history_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    await _get_ds_or_404(db, ds_id)
    history = await query_history_service.get_history(db, history_id)
    if not history or history.datasource_id != ds_id:
        raise HTTPException(status_code=404, detail="Query history not found")
    await query_history_service.delete_history(db, history)


@router.delete("/{ds_id}/query-history", status_code=204)
async def clear_query_history(
    ds_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    await _get_ds_or_404(db, ds_id)
    await query_history_service.clear_histories(db, ds_id)
