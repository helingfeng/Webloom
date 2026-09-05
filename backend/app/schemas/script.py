from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class VariableDefinition(BaseModel):
    name: str
    type: Literal["string", "number", "boolean", "secret", "header", "cookie", "localStorage"]
    description: str = ""
    default: Any = None
    required: bool = True


class OutputDefinition(BaseModel):
    name: str
    description: str = ""


class ScriptBase(BaseModel):
    workspace_id: int
    name: str
    description: str = ""
    start_url: str = ""
    inputs: list[VariableDefinition] = []
    outputs: list[OutputDefinition] = []
    code: str = ""
    inherit_global: bool = True
    run_mode: Literal["manual", "mock"] = "manual"
    headless: bool = True


class ScriptCreate(ScriptBase):
    pass


class ScriptUpdate(ScriptBase):
    pass


class ScriptOut(ScriptBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ScriptRunRequest(BaseModel):
    mode: Literal["manual", "mock"] | None = None
    inputs: dict[str, Any] = {}
    headless: bool | None = None


class BatchDeleteIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class BatchDeleteOut(BaseModel):
    deleted: int
