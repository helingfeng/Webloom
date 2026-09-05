from pydantic import BaseModel


class CodeValidateRequest(BaseModel):
    code: str


class CodeError(BaseModel):
    line: int
    column: int
    message: str


class CodeValidateResult(BaseModel):
    ok: bool
    errors: list[CodeError] = []


class CodeFormatRequest(BaseModel):
    code: str


class CodeFormatResult(BaseModel):
    code: str
    changed: bool
