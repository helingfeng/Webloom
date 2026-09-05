from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

CaseStatus = Literal["pending", "in_progress", "completed", "blocked"]


class TestCaseBase(BaseModel):
    requirement_id: int
    module_id: int | None = None
    title: str = Field(min_length=1)
    precondition: str = ""
    steps: list[str] = []
    expected_result: str = ""
    status: CaseStatus = "pending"


class TestCaseCreate(TestCaseBase):
    pass


class TestCaseUpdate(TestCaseBase):
    pass


class TestCaseOut(TestCaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class StatusUpdate(BaseModel):
    status: CaseStatus


class BatchStatusUpdate(BaseModel):
    ids: list[int] = Field(min_length=1)
    status: CaseStatus


class BatchStatusOut(BaseModel):
    updated: int


class BatchDeleteIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class BatchDeleteOut(BaseModel):
    deleted: int


class ImportCaseIn(BaseModel):
    title: str = Field(min_length=1)
    precondition: str = ""
    steps: list[str] = []
    expected_result: str = ""


class ImportModuleIn(BaseModel):
    name: str = Field(min_length=1)
    cases: list[ImportCaseIn] = []


class TestCaseImportIn(BaseModel):
    workspace_id: int
    requirement_id: int | None = None
    requirement_name: str = ""
    modules: list[ImportModuleIn] = []
    cases: list[ImportCaseIn] = []


class TestCaseImportOut(BaseModel):
    requirement_id: int
    requirement_name: str
    module_count: int
    case_count: int
