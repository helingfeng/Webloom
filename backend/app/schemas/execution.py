from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class ExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_type: str
    target_id: int
    mode: str
    inputs: dict[str, Any]
    status: str
    logs: str
    outputs: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None


class ExecutionPageOut(BaseModel):
    items: list[ExecutionOut]
    total: int
