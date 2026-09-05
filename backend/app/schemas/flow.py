from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class FlowBase(BaseModel):
    workspace_id: int
    name: str
    description: str = ""
    run_mode: str = "manual"
    global_inputs: dict[str, Any] = {}
    nodes: list[dict] = []
    edges: list[dict] = []


class FlowCreate(FlowBase):
    pass


class FlowUpdate(FlowBase):
    pass


class FlowOut(FlowBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class FlowRunRequest(BaseModel):
    mode: str = "manual"
    global_inputs: dict[str, Any] = {}
