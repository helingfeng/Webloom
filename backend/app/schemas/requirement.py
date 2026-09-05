from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class RequirementBase(BaseModel):
    workspace_id: int
    name: str = Field(min_length=1)
    description: str = ""


class RequirementCreate(RequirementBase):
    pass


class RequirementUpdate(RequirementBase):
    pass


class RequirementOut(RequirementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
