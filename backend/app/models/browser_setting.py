from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, BigIntUnsigned


class BrowserSetting(Base):
    __tablename__ = "browser_settings"
    __table_args__ = {"comment": "平台浏览器设置（固定单行）"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="固定主键 1")
    cloakbrowser_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="是否启用 CloakBrowser"
    )
