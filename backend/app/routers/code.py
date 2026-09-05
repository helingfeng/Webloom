from typing import Any
from fastapi import APIRouter, HTTPException
from app.schemas.code import (
    CodeFormatRequest,
    CodeFormatResult,
    CodeValidateRequest,
    CodeValidateResult,
)
from app.services import code_service

router = APIRouter()


@router.post("/validate", response_model=CodeValidateResult)
async def validate_code(req: CodeValidateRequest) -> Any:
    return code_service.validate_code(req.code)


@router.post("/format", response_model=CodeFormatResult)
async def format_code(req: CodeFormatRequest) -> Any:
    try:
        formatted = code_service.format_code(req.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return CodeFormatResult(code=formatted, changed=formatted != req.code)


@router.post("/sql-validate", response_model=CodeValidateResult)
async def validate_sql(req: CodeValidateRequest) -> Any:
    return code_service.validate_sql(req.code)


@router.post("/sql-format", response_model=CodeFormatResult)
async def format_sql(req: CodeFormatRequest) -> Any:
    try:
        formatted = code_service.format_sql(req.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return CodeFormatResult(code=formatted, changed=formatted != req.code)
