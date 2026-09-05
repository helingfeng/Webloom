from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = {"comment": "需求表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    # 逻辑归属 Workspace（无外键，空间删除前有服务层清空校验）
    workspace_id: Mapped[int] = mapped_column(
        BigIntUnsigned, nullable=False, index=True, comment="逻辑归属 Workspace（无外键）"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="需求名称")
    description: Mapped[str] = mapped_column(Text, default="", comment="描述")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
