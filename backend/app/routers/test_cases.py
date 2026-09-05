from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.test_case import TestCase
from app.schemas.test_case import (
    BatchDeleteIn,
    BatchDeleteOut,
    BatchStatusOut,
    BatchStatusUpdate,
    StatusUpdate,
    TestCaseCreate,
    TestCaseImportIn,
    TestCaseImportOut,
    TestCaseOut,
    TestCaseUpdate,
)
from app.services import test_case_service

router = APIRouter()


async def _get_case_or_404(db: AsyncSession, case_id: int) -> TestCase:
    case = await test_case_service.get_test_case(db, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="TestCase not found")
    return case


@router.get("", response_model=list[TestCaseOut])
async def list_test_cases(
    workspace_id: int | None = None,
    requirement_id: int | None = None,
    module_id: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await test_case_service.get_test_cases(
        db,
        workspace_id=workspace_id,
        requirement_id=requirement_id,
        module_id=module_id,
        status=status,
    )


@router.post("", response_model=TestCaseOut, status_code=201)
async def create_test_case(
    case_in: TestCaseCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        return await test_case_service.create_test_case(db, case_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{case_id}", response_model=TestCaseOut)
async def update_test_case(
    case_id: int, case_in: TestCaseUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    case = await _get_case_or_404(db, case_id)
    try:
        return await test_case_service.update_test_case(db, case, case_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{case_id}", status_code=204)
async def delete_test_case(case_id: int, db: AsyncSession = Depends(get_db)) -> None:
    case = await _get_case_or_404(db, case_id)
    await test_case_service.delete_test_case(db, case)


@router.patch("/{case_id}/status", response_model=TestCaseOut)
async def update_test_case_status(
    case_id: int, status_in: StatusUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    case = await _get_case_or_404(db, case_id)
    return await test_case_service.update_status(db, case, status_in.status)


@router.post("/batch-status", response_model=BatchStatusOut)
async def batch_update_status(
    batch_in: BatchStatusUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        updated = await test_case_service.batch_update_status(
            db, batch_in.ids, batch_in.status
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"updated": updated}


@router.post("/batch-delete", response_model=BatchDeleteOut)
async def batch_delete_cases(
    batch_in: BatchDeleteIn, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        deleted = await test_case_service.batch_delete(db, batch_in.ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"deleted": deleted}


@router.post("/import", response_model=TestCaseImportOut, status_code=201)
async def import_test_cases(
    payload: TestCaseImportIn, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        return await test_case_service.import_test_cases(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
