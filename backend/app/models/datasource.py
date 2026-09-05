from datetime import datetime
from sqlalchemy import String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class Datasource(Base):
    __tablename__ = "datasources"
    __table_args__ = {"comment": "外部数据源表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="数据源名称")
    host: Mapped[str] = mapped_column(String(255), nullable=False, comment="主机")
    port: Mapped[int] = mapped_column(Integer, default=3306, comment="端口")
    user: Mapped[str] = mapped_column(String(255), nullable=False, comment="用户名")
    # 本地单用户平台，明文存储；API 响应（DatasourceOut）不回传
    password: Mapped[str] = mapped_column(
        String(255), default="", comment="密码（明文存储，接口不回传）"
    )
    database: Mapped[str] = mapped_column(String(255), default="", comment="默认库")
    description: Mapped[str] = mapped_column(Text, default="", comment="描述")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
