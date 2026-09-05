from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.global_variable import GlobalVariable
from app.schemas.global_variable import (
    GlobalVariableCreate,
    GlobalVariableOut,
    GlobalVariableUpdate,
)
from app.services import global_variable_service

router = APIRouter()


async def _get_var_or_404(db: AsyncSession, var_id: int) -> GlobalVariable:
    var = await global_variable_service.get_global_variable(db, var_id)
    if not var:
        raise HTTPException(status_code=404, detail="Global variable not found")
    return var


@router.get("", response_model=list[GlobalVariableOut])
async def list_global_variables(db: AsyncSession = Depends(get_db)) -> Any:
    return await global_variable_service.get_global_variables(db)


@router.post("", response_model=GlobalVariableOut, status_code=201)
async def create_global_variable(
    var_in: GlobalVariableCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    return await global_variable_service.create_global_variable(db, var_in)


@router.put("/{var_id}", response_model=GlobalVariableOut)
async def update_global_variable(
    var_id: int, var_in: GlobalVariableUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    var = await _get_var_or_404(db, var_id)
    return await global_variable_service.update_global_variable(db, var, var_in)


@router.delete("/{var_id}", status_code=204)
async def delete_global_variable(
    var_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    var = await _get_var_or_404(db, var_id)
    await global_variable_service.delete_global_variable(db, var)
