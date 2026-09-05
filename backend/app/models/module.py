from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class Module(Base):
    __tablename__ = "modules"
    __table_args__ = {"comment": "模块表（需求下的功能模块）"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    # 逻辑归属 Requirement（无外键，需求删除前有服务层清空校验）
    requirement_id: Mapped[int] = mapped_column(
        BigIntUnsigned, nullable=False, index=True, comment="逻辑归属 Requirement（无外键）"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="模块名称")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
