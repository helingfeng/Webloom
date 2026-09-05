from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.requirement import Requirement
from app.schemas.requirement import RequirementCreate, RequirementOut, RequirementUpdate
from app.services import requirement_service

router = APIRouter()


async def _get_requirement_or_404(db: AsyncSession, req_id: int) -> Requirement:
    req = await requirement_service.get_requirement(db, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return req


@router.get("", response_model=list[RequirementOut])
async def list_requirements(
    workspace_id: int | None = None, db: AsyncSession = Depends(get_db)
) -> Any:
    return await requirement_service.get_requirements(db, workspace_id=workspace_id)


@router.post("", response_model=RequirementOut, status_code=201)
async def create_requirement(
    req_in: RequirementCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        return await requirement_service.create_requirement(db, req_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{req_id}", response_model=RequirementOut)
async def update_requirement(
    req_id: int, req_in: RequirementUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    req = await _get_requirement_or_404(db, req_id)
    try:
        return await requirement_service.update_requirement(db, req, req_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{req_id}", status_code=204)
async def delete_requirement(req_id: int, db: AsyncSession = Depends(get_db)) -> None:
    req = await _get_requirement_or_404(db, req_id)
    try:
        await requirement_service.delete_requirement(db, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
