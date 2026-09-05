from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models.execution import Execution
from app.schemas.execution import ExecutionOut, ExecutionPageOut
from app.services import execution_service

router = APIRouter()


async def _get_execution_or_404(db: AsyncSession, execution_id: int) -> Execution:
    execution = await execution_service.get_execution(db, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("", response_model=ExecutionPageOut)
async def list_executions(
    skip: int = 0,
    limit: int = 20,
    workspace_id: int | None = None,
    script_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    items = await execution_service.get_executions(
        db, skip=skip, limit=limit, workspace_id=workspace_id, script_id=script_id
    )
    total = await execution_service.count_executions(
        db, workspace_id=workspace_id, script_id=script_id
    )
    return {"items": items, "total": total}


@router.get("/{execution_id}", response_model=ExecutionOut)
async def get_execution(
    execution_id: int, db: AsyncSession = Depends(get_db)
) -> Any:
    return await _get_execution_or_404(db, execution_id)


@router.delete("/{execution_id}", status_code=204)
async def delete_execution(
    execution_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    execution = await _get_execution_or_404(db, execution_id)
    await execution_service.delete_execution(db, execution)


@router.delete("", status_code=204)
async def clear_executions(db: AsyncSession = Depends(get_db)) -> None:
    await execution_service.clear_executions(db)


@router.get("/{execution_id}/frame")
async def get_execution_frame(execution_id: int) -> FileResponse:
    """实时画面帧：子进程 screencast 持续覆写该文件，前端轮询展示。"""
    frame_file = settings.executions_dir / f"frame_{execution_id}.jpg"
    if not frame_file.exists():
        raise HTTPException(status_code=404, detail="Frame not available")
    return FileResponse(
        frame_file,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )
