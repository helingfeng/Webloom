"""由 SQLAlchemy 模型生成 backend/mysql_ddl.sql（按团队建表规范格式化）。

用法：cd backend && python scripts/gen_mysql_ddl.py
规范要点：bigint unsigned 主键、列注释、varchar 默认值、DATETIME 默认
CURRENT_TIMESTAMP / ON UPDATE CURRENT_TIMESTAMP、USING BTREE、InnoDB + utf8mb4。
TEXT/JSON 列因 MySQL 限制不带 DEFAULT。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.dialects.mysql import BIGINT

import app.models  # noqa: F401  注册所有模型到 Base.metadata
from app.database import Base

OUT_FILE = Path(__file__).resolve().parent.parent / "mysql_ddl.sql"

HEADER = """\
-- 采织 Webloom 平台 MySQL 建表 DDL（由 scripts/gen_mysql_ddl.py 从 SQLAlchemy 模型生成，勿手工改列）
-- 改动模型后需重新执行：cd backend && python scripts/gen_mysql_ddl.py
-- 使用前先建库（表已显式声明 utf8mb4）：
-- CREATE DATABASE fishcode DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
"""


def mysql_type(col):
    variant = getattr(col.type, "_variant_mapping", None) or {}
    return variant.get("mysql", col.type)


def type_text(t) -> str:
    if isinstance(t, Boolean):
        return "tinyint(1) unsigned"
    if isinstance(t, Text):  # Text 是 String 子类，先判
        return "text"
    if isinstance(t, JSON):
        return "json"
    if isinstance(t, DateTime):
        return "datetime"
    if isinstance(t, String):
        return f"varchar({t.length})"
    if isinstance(t, BIGINT):
        return "bigint unsigned" if t.unsigned else "bigint"
    if isinstance(t, BigInteger):  # BigInteger 是 Integer 子类，先判
        return "bigint"
    if isinstance(t, Integer):
        return "int"
    raise ValueError(f"未支持的列类型: {t!r}")


def default_text(col, t) -> str:
    if isinstance(t, DateTime):
        parts = []
        if col.default is not None:
            parts.append("DEFAULT CURRENT_TIMESTAMP")
        if col.onupdate is not None:
            parts.append("ON UPDATE CURRENT_TIMESTAMP")
        return " ".join(parts)
    if isinstance(t, (Text, JSON)):  # MySQL 的 TEXT/JSON 列不支持 DEFAULT
        return ""
    if col.default is None or col.default.is_callable:
        return ""
    arg = col.default.arg
    if isinstance(arg, bool):
        return f"DEFAULT '{int(arg)}'"
    if isinstance(arg, int):
        return f"DEFAULT {arg}"
    if isinstance(arg, str):
        return f"DEFAULT '{arg}'"
    return ""


def table_ddl(table) -> str:
    cols = list(table.columns)
    name_w = max(len(f"`{c.name}`") for c in cols) + 1
    type_w = max(len(type_text(mysql_type(c))) for c in cols) + 1

    lines = []
    for c in cols:
        t = mysql_type(c)
        parts = [f"`{c.name}`".ljust(name_w), type_text(t).ljust(type_w)]
        parts.append("NULL" if c.nullable else "NOT NULL")
        dflt = default_text(c, t)
        if dflt:
            parts.append(dflt)
        if c.primary_key and t is not None and isinstance(t, (BigInteger, Integer)):
            parts.append("AUTO_INCREMENT")
        comment = (c.comment or "").replace("'", "''")
        if comment:
            parts.append(f"COMMENT '{comment}'")
        lines.append("    " + " ".join(parts).rstrip())

    lines.append(f"    PRIMARY KEY (`{table.primary_key.columns[0].name}`)")
    for cons in sorted(
        (x for x in table.constraints if x.__class__.__name__ == "UniqueConstraint"),
        key=lambda x: x.name or "",
    ):
        cols_sql = ", ".join(f"`{c.name}`" for c in cons.columns)
        name_sql = f"`{cons.name}` " if cons.name else ""
        lines.append(f"    UNIQUE KEY {name_sql}({cols_sql}) USING BTREE")
    for ix in sorted(table.indexes, key=lambda i: i.name):
        cols_sql = ", ".join(f"`{c.name}`" for c in ix.columns)
        kw = "UNIQUE KEY" if ix.unique else "KEY"
        lines.append(f"    {kw} `{ix.name}` ({cols_sql}) USING BTREE")

    comment = (table.comment or "").replace("'", "''")
    options = (
        f"ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci "
        f"COMMENT='{comment}'"
    )
    return f"CREATE TABLE `{table.name}`\n(\n" + ",\n".join(lines) + f"\n) {options};"


def main() -> None:
    blocks = [table_ddl(t) for t in Base.metadata.sorted_tables]
    OUT_FILE.write_text(HEADER + "\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")
    print(f"written: {OUT_FILE} ({len(blocks)} tables)")


if __name__ == "__main__":
    main()
