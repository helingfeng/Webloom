from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.data_view import DataView
from app.schemas.datasource import QueryResult
from app.schemas.data_view import (
    DataQueryResult,
    DataViewCreate,
    DataViewOut,
    DataViewUpdate,
)
from app.services import data_view_service, datasource_service
from app.services.datasource_query_service import execute_readonly_query

router = APIRouter()
public_router = APIRouter()


async def _get_dv_or_404(db: AsyncSession, dv_id: int) -> DataView:
    dv = await data_view_service.get_data_view(db, dv_id)
    if not dv:
        raise HTTPException(status_code=404, detail="Data view not found")
    return dv


@router.get("", response_model=list[DataViewOut])
async def list_data_views(db: AsyncSession = Depends(get_db)) -> Any:
    return await data_view_service.get_data_views(db)


@router.post("", response_model=DataViewOut, status_code=201)
async def create_data_view(
    dv_in: DataViewCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        return await data_view_service.create_data_view(db, dv_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{dv_id}", response_model=DataViewOut)
async def update_data_view(
    dv_id: int, dv_in: DataViewUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    dv = await _get_dv_or_404(db, dv_id)
    try:
        return await data_view_service.update_data_view(db, dv, dv_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{dv_id}", status_code=204)
async def delete_data_view(dv_id: int, db: AsyncSession = Depends(get_db)) -> None:
    dv = await _get_dv_or_404(db, dv_id)
    await data_view_service.delete_data_view(db, dv)


@router.post("/{dv_id}/run", response_model=QueryResult)
async def run_data_view(dv_id: int, db: AsyncSession = Depends(get_db)) -> Any:
    """管理端运行预览：始终 200，失败在 error 字段"""
    dv = await _get_dv_or_404(db, dv_id)
    return await data_view_service.run_data_view(db, dv)


@public_router.get("/{slug}", response_model=DataQueryResult)
async def get_view_data(
    slug: str, response: Response, db: AsyncSession = Depends(get_db)
) -> Any:
    """外部取数接口：无需鉴权；手动加 CORS 头支持跨域 GET（简单请求无需预检）"""
    # 无论成功还是 404/500，都允许跨域读取错误信息
    response.headers["Access-Control-Allow-Origin"] = "*"

    dv = await data_view_service.get_data_view_by_slug(db, slug)
    if not dv:
        raise HTTPException(status_code=404, detail="数据视图不存在")
    if not dv.enabled:
        raise HTTPException(status_code=404, detail="数据视图不存在")

    ds = await datasource_service.get_datasource(db, dv.datasource_id)
    if not ds:
        raise HTTPException(status_code=502, detail="关联数据源不存在或已删除")

    result = await execute_readonly_query(ds, dv.sql, database=dv.database)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    return DataQueryResult(
        columns=result.columns,
        records=[dict(zip(result.columns, row)) for row in result.rows],
        row_count=result.row_count,
        truncated=result.truncated,
        elapsed_ms=result.elapsed_ms,
    )
