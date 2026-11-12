"""发布的采集接口与持久任务归属；不依赖可清理的调用日志。"""

from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class Collector(Base):
    __tablename__ = "collectors"
    __table_args__ = {"comment": "发布的采集接口"}
    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    slug: Mapped[str] = mapped_column(String(80), unique=True, comment="稳定接口标识")
    name: Mapped[str] = mapped_column(String(255), comment="接口名称")
    description: Mapped[str] = mapped_column(
        Text, default="", comment="面向调用方的说明"
    )
    script_id: Mapped[int] = mapped_column(
        BigIntUnsigned, index=True, comment="绑定脚本 ID"
    )
    app_ids: Mapped[list] = mapped_column(
        JSON, default=list, comment="授权应用 ID 列表"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否发布")
    archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", comment="是否已移除（保留历史任务）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )


class CollectorTask(Base):
    __tablename__ = "collector_tasks"
    __table_args__ = (
        UniqueConstraint("app_id", "request_key", name="uq_collector_task_request"),
        {"comment": "采集任务持久归属与幂等记录"},
    )
    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    collector_id: Mapped[int] = mapped_column(
        BigIntUnsigned, index=True, comment="发布接口 ID"
    )
    app_id: Mapped[int] = mapped_column(
        BigIntUnsigned, index=True, comment="调用应用 ID"
    )
    execution_id: Mapped[int] = mapped_column(
        BigIntUnsigned, unique=True, comment="执行记录 ID"
    )
    request_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="调用方幂等键"
    )
    request_hash: Mapped[str] = mapped_column(String(64), comment="幂等请求摘要")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="提交时间"
    )
