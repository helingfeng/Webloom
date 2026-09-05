from datetime import datetime
from sqlalchemy import String, Text, DateTime, Boolean, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base, BigIntUnsigned


class QueryHistory(Base):
    """数据源工作台 SQL 执行历史；点击历史可回看当时的 SQL 与结果"""

    __tablename__ = "query_history"
    __table_args__ = {"comment": "SQL 执行历史表"}

    id: Mapped[int] = mapped_column(BigIntUnsigned, primary_key=True, comment="主键")
    # 逻辑关联 Datasource（无外键，删除数据源时级联清理）
    datasource_id: Mapped[int] = mapped_column(
        BigIntUnsigned, index=True, comment="逻辑关联数据源 ID（无外键）"
    )
    database: Mapped[str] = mapped_column(String(255), default="", comment="执行库")
    sql: Mapped[str] = mapped_column(Text, nullable=False, comment="执行的 SQL")
    success: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否成功：1-成功/0-失败")
    statement_type: Mapped[str] = mapped_column(
        String(20), default="query", comment="语句类型：query/execute"
    )
    # 查询类结果：rows 最多保留 200 行样本，row_count 记录真实行数
    columns: Mapped[list] = mapped_column(JSON, default=list, comment="结果列名 JSON")
    rows: Mapped[list] = mapped_column(
        JSON, default=list, comment="结果行 JSON（最多 200 行样本）"
    )
    row_count: Mapped[int] = mapped_column(Integer, default=0, comment="真实行数")
    truncated: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="结果是否被截断：1-是/0-否"
    )
    affected_rows: Mapped[int] = mapped_column(Integer, default=0, comment="影响行数")
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0, comment="耗时（毫秒）")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
