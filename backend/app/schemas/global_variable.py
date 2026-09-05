from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict


class GlobalVariableBase(BaseModel):
    name: str
    value: str = ""
    type: Literal["header", "variable", "localStorage", "cookie"] = "header"
    domain: str = ""
    enabled: bool = True
    description: str = ""


class GlobalVariableCreate(GlobalVariableBase):
    pass


class GlobalVariableUpdate(GlobalVariableBase):
    pass


class GlobalVariableOut(GlobalVariableBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
