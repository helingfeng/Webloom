from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,63}$"


class DataViewBase(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(pattern=SLUG_PATTERN)
    datasource_id: int
    database: str = ""  # 指定执行库；空 = 沿用数据源默认库
    sql: str = Field(min_length=1)
    description: str = ""
    enabled: bool = True


class DataViewCreate(DataViewBase):
    pass


class DataViewUpdate(BaseModel):
    name: str | None = None
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    datasource_id: int | None = None
    database: str | None = None  # 显式传 "" 表示清空回退默认库
    sql: str | None = None
    description: str | None = None
    enabled: bool | None = None


class DataViewOut(DataViewBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class DataQueryResult(BaseModel):
    """外部取数接口响应：records 为对象数组，外部系统直接消费"""

    columns: list[str]
    records: list[dict[str, Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
