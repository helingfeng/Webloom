from datetime import datetime
from sqlalchemy import String, Text, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class Script(Base):
    __tablename__ = "scripts"
    __table_args__ = {"comment": "测试脚本表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    # 逻辑归属 Workspace（无外键，空间删除前有服务层清空校验）
    workspace_id: Mapped[int | None] = mapped_column(
        BigIntUnsigned, nullable=True, index=True, comment="逻辑归属 Workspace（无外键）"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="脚本名称")
    description: Mapped[str] = mapped_column(Text, default="", comment="描述")
    start_url: Mapped[str] = mapped_column(Text, default="", comment="起始 URL")
    inputs: Mapped[list[dict]] = mapped_column(
        JSON,
        default=list,
        comment="输入参数定义 [{name,type,description,default,required}]，type 含 string/number/boolean/secret/header/cookie/localStorage",
    )
    outputs: Mapped[list[dict]] = mapped_column(
        JSON, default=list, comment="输出定义 [{name,description}]"
    )
    code: Mapped[str] = mapped_column(Text, default="", comment="用户 Playwright 代码片段")
    inherit_global: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否继承全局变量：1-继承/0-不继承"
    )
    run_mode: Mapped[str] = mapped_column(String(16), default="manual", comment="运行方式：manual-手动")
    headless: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否无头运行：1-是/0-否")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
