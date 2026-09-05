from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    prompt_template: str
    example_code: str
    example_inputs: list[dict[str, Any]]
    example_outputs: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class SkillCloneResponse(BaseModel):
    prompt_template: str
    example_code: str
    example_inputs: list[dict[str, Any]]
    example_outputs: list[dict[str, Any]]
