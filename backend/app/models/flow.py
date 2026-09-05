from datetime import datetime
from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class Flow(Base):
    __tablename__ = "flows"
    __table_args__ = {"comment": "自动化流程表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    # 逻辑归属 Workspace（无外键，空间删除前有服务层清空校验）
    workspace_id: Mapped[int | None] = mapped_column(
        BigIntUnsigned, nullable=True, index=True, comment="逻辑归属 Workspace（无外键）"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="流程名称")
    description: Mapped[str] = mapped_column(Text, default="", comment="描述")
    nodes: Mapped[list[dict]] = mapped_column(JSON, default=list, comment="画布节点 JSON")
    edges: Mapped[list[dict]] = mapped_column(JSON, default=list, comment="画布连线 JSON")
    run_mode: Mapped[str] = mapped_column(
        String(16), default="manual", comment="运行方式：manual-手动输入/mock-自动 Mock"
    )
    global_inputs: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="全局输入默认值 JSON（手动模式用）"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
