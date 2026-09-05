from datetime import datetime
from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = {"comment": "脚本技能模板表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="技能名称")
    description: Mapped[str] = mapped_column(Text, default="", comment="描述")
    prompt_template: Mapped[str] = mapped_column(Text, default="", comment="提示词模板")
    example_code: Mapped[str] = mapped_column(Text, default="", comment="示例代码")
    example_inputs: Mapped[list[dict]] = mapped_column(JSON, default=list, comment="示例输入 JSON")
    example_outputs: Mapped[list[dict]] = mapped_column(JSON, default=list, comment="示例输出 JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )
