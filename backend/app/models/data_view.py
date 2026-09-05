from datetime import datetime
from sqlalchemy import String, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class DataView(Base):
    __tablename__ = "data_views"
    __table_args__ = {"comment": "数据视图表（数据源 + 只读 SQL 对外取数）"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="视图名称")
    # 外部取数 URL 标识：GET /api/data/{slug}
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, comment="对外取数标识（GET /api/data/{slug}）"
    )
    # 逻辑关联 Datasource（无外键，数据源删除后视图悬空，取数时报错）
    datasource_id: Mapped[int] = mapped_column(
        BigIntUnsigned, index=True, comment="逻辑关联数据源 ID（无外键）"
    )
    # 指定执行库；空串 = 沿用数据源默认库
    database: Mapped[str] = mapped_column(
        String(255), default="", comment="执行库（空为数据源默认库）"
    )
    sql: Mapped[str] = mapped_column(Text, nullable=False, comment="只读 SQL")
    description: Mapped[str] = mapped_column(Text, default="", comment="描述")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用：1-启用/0-停用")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
