from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------- 开放应用 ----------


class OpenAppBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    enabled: bool = True


class OpenAppCreate(OpenAppBase):
    pass


class OpenAppUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    enabled: bool | None = None


class OpenAppOut(OpenAppBase):
    """列表用：不回传 app_secret"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    app_key: str
    created_at: datetime
    updated_at: datetime


class OpenAppDetailOut(OpenAppOut):
    """详情用：回传 app_secret（本地单用户平台）"""

    app_secret: str


class OpenAppSecretOut(BaseModel):
    app_key: str
    app_secret: str


class OpenAppPageOut(BaseModel):
    items: list[OpenAppOut]
    total: int


# ---------- 调用日志 ----------


class OpenApiLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    app_id: int | None
    app_key: str
    path: str
    method: str
    status_code: int
    success: bool
    execution_id: int | None
    request_ip: str
    detail: str
    created_at: datetime


class OpenApiLogPageOut(BaseModel):
    items: list[OpenApiLogOut]
    total: int


# ---------- 开放采集接口出入参 ----------


class OpenCollectTriggerRequest(BaseModel):
    url: str = Field(
        min_length=1, description="要采集的目标页面链接（合入脚本 inputs.url）"
    )
    script_id: int = Field(description="要执行的采集脚本 ID")
    inputs: dict[str, Any] = Field(
        default_factory=dict, description="附加输入变量（url 之外）"
    )
    headless: bool | None = Field(
        default=None, description="是否无头运行；缺省用脚本保存值"
    )


class OpenCollectTaskOut(BaseModel):
    execution_id: int
    script_id: int
    status: str
    finished: bool
    started_at: datetime | None = None
    finished_at: datetime | None = None
