from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class DatasourceBase(BaseModel):
    name: str
    host: str
    port: int = Field(default=3306, ge=1, le=65535)
    user: str
    database: str = ""
    description: str = ""


class DatasourceCreate(DatasourceBase):
    password: str


class DatasourceUpdate(BaseModel):
    """全字段可选；password 为 None/空串表示不修改（Out 不回传密码，编辑时拿不到旧值）"""

    name: str | None = None
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str | None = None
    password: str | None = None
    database: str | None = None
    description: str | None = None


class DatasourceOut(DatasourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class DatasourceTestRequest(BaseModel):
    """保存前测试连接：全量连接参数"""

    host: str
    port: int = Field(default=3306, ge=1, le=65535)
    user: str
    password: str = ""
    database: str = ""


class DatasourceTestResult(BaseModel):
    success: bool
    elapsed_ms: int
    server_version: str | None = None
    error: str | None = None


class DatasourceTable(BaseModel):
    name: str
    table_type: str  # BASE TABLE / VIEW
    table_rows: int | None = None  # information_schema 近似值
    comment: str = ""


class DatasourceColumn(BaseModel):
    name: str
    column_type: str
    nullable: bool
    column_key: str  # PRI / UNI / MUL / ''
    default: str | None = None
    extra: str
    comment: str = ""


class QueryRequest(BaseModel):
    sql: str = Field(min_length=1)
    database: str | None = None  # 缺省回退数据源默认库


class QueryHistoryItem(BaseModel):
    """历史列表摘要：不含结果明细"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    database: str
    sql: str
    success: bool
    statement_type: str
    row_count: int
    affected_rows: int
    elapsed_ms: int
    error: str | None
    created_at: datetime


class QueryHistoryDetail(QueryHistoryItem):
    """历史详情：含执行当时的结果快照（rows 最多保留 200 行样本）"""

    columns: list[str] = []
    rows: list[list[Any]] = []
    truncated: bool = False


class QueryHistoryPage(BaseModel):
    items: list[QueryHistoryItem]
    total: int


class QueryResult(BaseModel):
    success: bool
    statement_type: str  # query | execute
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    affected_rows: int = 0
    truncated: bool = False
    elapsed_ms: int = 0
    error: str | None = None
