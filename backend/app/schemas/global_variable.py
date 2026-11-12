from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

GlobalVariableType = Literal["header", "variable", "localStorage", "cookie"]


class GlobalVariableCreate(BaseModel):
    name: str
    value: str = ""
    type: GlobalVariableType = "variable"
    domain: str = ""
    enabled: bool = True
    description: str = ""


class GlobalVariableUpdate(BaseModel):
    name: str | None = None
    value: str | None = None
    type: GlobalVariableType | None = None
    domain: str | None = None
    enabled: bool | None = None
    description: str | None = None


class GlobalVariableOut(BaseModel):
    """列表与写入结果不包含明文值。"""

    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: GlobalVariableType
    domain: str
    enabled: bool
    description: str
    has_value: bool
    created_at: datetime
    updated_at: datetime


class GlobalVariableDetailOut(GlobalVariableOut):
    value: str
