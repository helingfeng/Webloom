from datetime import datetime
from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = {"comment": "脚本执行记录表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="目标类型：script（兼容历史执行类型）"
    )
    target_id: Mapped[int] = mapped_column(
        BigIntUnsigned, nullable=False, comment="目标 ID"
    )
    mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="执行模式：manual-真实入参/mock-按输入定义生成 mock",
    )
    inputs: Mapped[dict] = mapped_column(JSON, default=dict, comment="输入参数 JSON")
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        comment="状态：pending/running/success/failed/timeout",
    )
    logs: Mapped[str] = mapped_column(Text, default="", comment="完整日志")
    outputs: Mapped[dict] = mapped_column(JSON, default=dict, comment="输出结果 JSON")
    script_snapshot: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="提交时的脚本与运行配置快照，兼容历史执行为空"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="开始时间"
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="结束时间"
    )
