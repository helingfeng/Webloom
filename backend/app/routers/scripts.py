from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.script import Script
from app.schemas.script import (
    BatchDeleteIn,
    BatchDeleteOut,
    ScriptCreate,
    ScriptOut,
    ScriptRunRequest,
    ScriptUpdate,
)
from app.services import script_service
from app.services.script_run_service import start_script_execution
from app.task_queue import QueueUnavailableError

router = APIRouter()


async def _get_script_or_404(db: AsyncSession, script_id: int) -> Script:
    script = await script_service.get_script(db, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


@router.get("", response_model=list[ScriptOut])
async def list_scripts(
    skip: int = 0,
    limit: int = 100,
    workspace_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await script_service.get_scripts(
        db, skip=skip, limit=limit, workspace_id=workspace_id
    )


@router.post("", response_model=ScriptOut, status_code=201)
async def create_script(
    script_in: ScriptCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        return await script_service.create_script(db, script_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{script_id}", response_model=ScriptOut)
async def get_script(script_id: int, db: AsyncSession = Depends(get_db)) -> Any:
    return await _get_script_or_404(db, script_id)


@router.put("/{script_id}", response_model=ScriptOut)
async def update_script(
    script_id: int, script_in: ScriptUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    script = await _get_script_or_404(db, script_id)
    try:
        return await script_service.update_script(db, script, script_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{script_id}", status_code=204)
async def delete_script(script_id: int, db: AsyncSession = Depends(get_db)) -> None:
    script = await _get_script_or_404(db, script_id)
    try:
        await script_service.delete_script(db, script)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/batch-delete", response_model=BatchDeleteOut)
async def batch_delete_scripts(
    batch_in: BatchDeleteIn, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        deleted = await script_service.batch_delete(db, batch_in.ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"deleted": deleted}


@router.post("/{script_id}/run")
async def run_script_endpoint(
    script_id: int, request: ScriptRunRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    script = await _get_script_or_404(db, script_id)
    try:
        execution = await start_script_execution(
            db,
            script,
            mode=request.mode or script.run_mode,
            inputs=request.inputs or {},
            headless=script.headless if request.headless is None else request.headless,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QueueUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="执行队列不可用：请确认 Redis 与执行 worker（arq）已启动",
        )
    return {
        "execution_id": execution.id,
        "status": execution.status,
        "outputs": {},
        "logs": "",
    }
