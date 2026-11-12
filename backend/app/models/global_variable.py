from datetime import datetime
from sqlalchemy import String, Text, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class GlobalVariable(Base):
    __tablename__ = "global_variables"
    __table_args__ = {"comment": "全局变量表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="变量名")
    value: Mapped[str] = mapped_column(
        Text, default="", comment="配置内容（列表接口不回传）"
    )
    type: Mapped[str] = mapped_column(
        String(50),
        default="variable",
        comment="类型：header/variable/localStorage/cookie",
    )
    # 绑定域名：留空对所有域名生效；非空时仅当脚本起始 URL 的 host 等于该域名或为其子域名时加载
    domain: Mapped[str] = mapped_column(
        String(255), default="", comment="绑定域名（空为对全部域名生效）"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否启用：1-启用/0-禁用"
    )
    description: Mapped[str] = mapped_column(Text, default="", comment="备注")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )

    @property
    def has_value(self) -> bool:
        return bool(self.value)
