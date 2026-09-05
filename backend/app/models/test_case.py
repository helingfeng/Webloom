from datetime import datetime
from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class TestCase(Base):
    __tablename__ = "test_cases"
    __table_args__ = {"comment": "测试用例表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    # 逻辑归属 Requirement（无外键）
    requirement_id: Mapped[int] = mapped_column(
        BigIntUnsigned, nullable=False, index=True, comment="逻辑归属 Requirement（无外键）"
    )
    # 模块可选：用例可直属于需求
    module_id: Mapped[int | None] = mapped_column(
        BigIntUnsigned, nullable=True, index=True, comment="模块 ID（空为直属于需求）"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="用例标题")
    precondition: Mapped[str] = mapped_column(Text, default="", comment="前置条件")
    steps: Mapped[list[str]] = mapped_column(JSON, default=list, comment="测试步骤 JSON")
    expected_result: Mapped[str] = mapped_column(Text, default="", comment="预期结果")
    status: Mapped[str] = mapped_column(
        String(16), default="pending", comment="状态：pending/in_progress/completed/blocked"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
