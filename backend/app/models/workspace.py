from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = {"comment": "项目空间表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="空间名称")
    description: Mapped[str] = mapped_column(Text, default="", comment="描述")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
