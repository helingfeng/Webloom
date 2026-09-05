from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from app.services import workspace_service

router = APIRouter()


async def _get_ws_or_404(db: AsyncSession, ws_id: int) -> Workspace:
    ws = await workspace_service.get_workspace(db, ws_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(db: AsyncSession = Depends(get_db)) -> Any:
    return await workspace_service.get_workspaces(db)


@router.post("", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    ws_in: WorkspaceCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        return await workspace_service.create_workspace(db, ws_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{ws_id}", response_model=WorkspaceOut)
async def update_workspace(
    ws_id: int, ws_in: WorkspaceUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    ws = await _get_ws_or_404(db, ws_id)
    try:
        return await workspace_service.update_workspace(db, ws, ws_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{ws_id}", status_code=204)
async def delete_workspace(ws_id: int, db: AsyncSession = Depends(get_db)) -> None:
    ws = await _get_ws_or_404(db, ws_id)
    try:
        await workspace_service.delete_workspace(db, ws)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
