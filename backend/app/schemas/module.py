from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ModuleBase(BaseModel):
    requirement_id: int
    name: str = Field(min_length=1)


class ModuleCreate(ModuleBase):
    pass


class ModuleUpdate(ModuleBase):
    pass


class ModuleOut(ModuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
