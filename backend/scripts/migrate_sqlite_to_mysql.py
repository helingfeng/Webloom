"""一次性脚本：把 SQLite 存量数据迁移到 MySQL。

用法（先确保 MySQL 已建库，库级字符集 utf8mb4）：
    cd backend && python scripts/migrate_sqlite_to_mysql.py
可选参数 --sqlite-url / --mysql-url 覆盖默认连接（默认取 config.settings）。

行为：
1. 按 SQLAlchemy 模型在 MySQL 侧建表（create_all，幂等）；
2. 逐表从 SQLite 读出经 ORM 类型处理（JSON/Boolean/DateTime）后写回 MySQL，
   显式携带 id，AUTO_INCREMENT 自动对齐；
3. MySQL 侧已有数据的表跳过（保证重复执行不覆盖目标库）；
4. 结束打印两侧行数对比，并 dispose 全部引擎（不留连接）。
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, inspect, select
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  注册所有模型到 Base.metadata
from app.config import BASE_DIR, settings
from app.database import Base

DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///{BASE_DIR}/storage/app.db"


async def table_count(conn, table) -> int:
    return await conn.scalar(select(func.count()).select_from(table))


async def main(sqlite_url: str, mysql_url: str) -> None:
    sqlite_engine = create_async_engine(sqlite_url)
    mysql_engine = create_async_engine(mysql_url, pool_pre_ping=True)

    try:
        async with mysql_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with sqlite_engine.connect() as s_conn:
            existing = await s_conn.run_sync(
                lambda sync_conn: __import__("sqlalchemy.inspection", fromlist=["inspect"]).inspect(
                    sync_conn
                ).get_table_names()
            )
            for table in Base.metadata.sorted_tables:
                if table.name not in existing:
                    print(f"[skip] sqlite 无表 {table.name}")
                    continue

                async with mysql_engine.connect() as m_conn:
                    if await table_count(m_conn, table) > 0:
                        print(f"[skip] mysql 已有数据 {table.name}")
                        continue

                rows = (await s_conn.execute(table.select())).mappings().all()
                if not rows:
                    print(f"[empty] {table.name}: 0 行")
                    continue

                async with mysql_engine.begin() as m_conn:
                    await m_conn.execute(table.insert(), list(rows))
                print(f"[ok] {table.name}: {len(rows)} 行")

        print("\n行数对比（sqlite -> mysql）:")
        total_src = total_dst = 0
        async with sqlite_engine.connect() as s_conn, mysql_engine.connect() as m_conn:
            for table in Base.metadata.sorted_tables:
                if table.name not in existing:
                    continue
                src = await table_count(s_conn, table)
                dst = await table_count(m_conn, table)
                total_src += src
                total_dst += dst
                flag = "OK" if src == dst else "!!"
                print(f"  [{flag}] {table.name}: {src} -> {dst}")
        print(f"合计: {total_src} -> {total_dst}")
    finally:
        await sqlite_engine.dispose()
        await mysql_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SQLite -> MySQL 数据迁移")
    parser.add_argument("--sqlite-url", default=DEFAULT_SQLITE_URL)
    parser.add_argument("--mysql-url", default=settings.database_url)
    args = parser.parse_args()
    if not args.mysql_url.startswith("mysql+"):
        sys.exit("目标库不是 MySQL，拒绝执行")
    asyncio.run(main(args.sqlite_url, args.mysql_url))
