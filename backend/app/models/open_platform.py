from datetime import datetime
from sqlalchemy import String, Text, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class OpenApp(Base):
    __tablename__ = "open_apps"
    __table_args__ = {"comment": "开放平台应用表（App Key + Secret 凭证）"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="应用名称")
    app_key: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, comment="开放应用 App Key（调用方标识）"
    )
    # 本地单用户平台，明文存储；管理端列表不回传，详情/重新生成时返回
    app_secret: Mapped[str] = mapped_column(String(128), nullable=False, comment="App Secret（签名密钥）")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用：1-启用/0-停用")
    description: Mapped[str] = mapped_column(Text, default="", comment="描述")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )


class OpenApiRoute(Base):
    __tablename__ = "open_apis"
    __table_args__ = {"comment": "开放接口表（代理规则：外部路径 → 平台内部 /api 接口）"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="接口名称")
    method: Mapped[str] = mapped_column(String(10), default="GET", comment="HTTP 方法：GET/POST/PUT/DELETE/PATCH")
    # 外部调用路径（相对 /open 前缀），支持 {param} 路径参数，如 /v1/executions/{execution_id}
    path: Mapped[str] = mapped_column(String(255), nullable=False, comment="外部调用路径（相对 /open，支持 {param}）")
    # 平台内部目标路径，必须以 /api/ 开头，支持 {param} 占位替换
    target_path: Mapped[str] = mapped_column(String(255), nullable=False, comment="内部目标路径（以 /api/ 开头）")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用：1-启用/0-停用")
    description: Mapped[str] = mapped_column(Text, default="", comment="描述")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )


class OpenApiLog(Base):
    __tablename__ = "open_api_logs"
    __table_args__ = {"comment": "开放接口调用日志表（含认证失败记录）"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    # 逻辑关联 OpenApp（无外键；认证失败时为 NULL，用 app_key 记录调用方）
    app_id: Mapped[int | None] = mapped_column(BigIntUnsigned, nullable=True, index=True, comment="应用 ID（认证失败为空）")
    app_key: Mapped[str] = mapped_column(String(64), default="", comment="调用方 App Key")
    path: Mapped[str] = mapped_column(String(255), default="", comment="请求路径")
    method: Mapped[str] = mapped_column(String(10), default="", comment="HTTP 方法")
    status_code: Mapped[int] = mapped_column(Integer, default=0, comment="响应状态码")
    success: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否成功：1-成功/0-失败")
    # 采集触发类调用关联的执行记录（用于归属校验与结果查询）
    execution_id: Mapped[int | None] = mapped_column(BigIntUnsigned, nullable=True, index=True, comment="关联执行 ID（采集触发）")
    request_ip: Mapped[str] = mapped_column(String(64), default="", comment="调用方 IP")
    detail: Mapped[str] = mapped_column(Text, default="", comment="摘要/失败原因")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
