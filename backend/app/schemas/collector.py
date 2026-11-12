from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class CollectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{1,79}$")
    script_id: int = Field(gt=0)
    description: str = ""
    app_ids: list[int] = Field(min_length=1)
    enabled: bool = True


class CollectorOut(CollectorCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class CollectorPage(BaseModel):
    items: list[CollectorOut]
    total: int


class CollectorRun(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    wait_seconds: int = Field(default=0, ge=0, le=20)


class CollectorDebug(CollectorRun):
    app_id: int


class CollectorTaskOut(BaseModel):
    task_id: int
    execution_id: int
    collector_id: int
    collector_name: str
    app_id: int
    status: Literal["pending", "running", "success", "failed"]
    finished: bool
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    result_url: str
    data_url: str


class CollectorTaskPage(BaseModel):
    items: list[CollectorTaskOut]
    total: int
