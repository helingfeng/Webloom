from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.module import Module
from app.schemas.module import ModuleCreate, ModuleOut, ModuleUpdate
from app.services import module_service

router = APIRouter()


async def _get_module_or_404(db: AsyncSession, module_id: int) -> Module:
    module = await module_service.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return module


@router.get("", response_model=list[ModuleOut])
async def list_modules(
    requirement_id: int | None = None, db: AsyncSession = Depends(get_db)
) -> Any:
    return await module_service.get_modules(db, requirement_id=requirement_id)


@router.post("", response_model=ModuleOut, status_code=201)
async def create_module(module_in: ModuleCreate, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        return await module_service.create_module(db, module_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{module_id}", response_model=ModuleOut)
async def update_module(
    module_id: int, module_in: ModuleUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    module = await _get_module_or_404(db, module_id)
    try:
        return await module_service.update_module(db, module, module_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{module_id}", status_code=204)
async def delete_module(module_id: int, db: AsyncSession = Depends(get_db)) -> None:
    module = await _get_module_or_404(db, module_id)
    try:
        await module_service.delete_module(db, module)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
