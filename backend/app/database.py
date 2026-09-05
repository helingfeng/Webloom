from sqlalchemy import BigInteger
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# 统一主键/ID 列类型：MySQL 下为 bigint unsigned，其他方言回退 BigInteger
BigIntUnsigned = BigInteger().with_variant(BIGINT(unsigned=True), "mysql")

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # 简单迁移：为已有表补充新增列（create_all 不会更新已有表；裸 SQL 用反引号兼容 MySQL，SQLite 也支持）
        def _migrate(sync_conn):
            from sqlalchemy import text, inspect

            inspector = inspect(sync_conn)
            if "scripts" in inspector.get_table_names():
                columns = {c["name"] for c in inspector.get_columns("scripts")}
                if "inherit_global" not in columns:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE `scripts` ADD COLUMN inherit_global BOOLEAN DEFAULT 1"
                        )
                    )
                if "run_mode" not in columns:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE `scripts` ADD COLUMN run_mode VARCHAR(16) DEFAULT 'manual'"
                        )
                    )
                if "headless" not in columns:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE `scripts` ADD COLUMN headless BOOLEAN DEFAULT 1"
                        )
                    )
            if "global_variables" in inspector.get_table_names():
                columns = {c["name"] for c in inspector.get_columns("global_variables")}
                if "domain" not in columns:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE `global_variables` ADD COLUMN domain VARCHAR(255) DEFAULT ''"
                        )
                    )
            # ---- workspace 归属迁移（幂等）----
            if "workspaces" in inspector.get_table_names():
                # 仅空表时插入默认空间（条件是表空而非名字不存在，避免删除后被复活）
                count = sync_conn.execute(
                    text("SELECT COUNT(*) FROM workspaces")
                ).scalar()
                if not count:
                    sync_conn.execute(
                        text(
                            "INSERT INTO `workspaces` (name, description, created_at, updated_at) "
                            "VALUES ('默认空间', '系统迁移自动创建', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                        )
                    )
                for table in ("scripts", "flows"):
                    if table in inspector.get_table_names():
                        columns = {c["name"] for c in inspector.get_columns(table)}
                        if "workspace_id" not in columns:
                            sync_conn.execute(
                                text(
                                    f"ALTER TABLE `{table}` ADD COLUMN workspace_id INTEGER"
                                )
                            )
                            # create_all 不会为 ALTER 补的列建索引，手动补
                            # （MySQL 无 CREATE INDEX IF NOT EXISTS，用 inspector 判断是否已存在）
                            index_names = {
                                ix["name"] for ix in inspector.get_indexes(table)
                            }
                            if f"ix_{table}_workspace_id" not in index_names:
                                sync_conn.execute(
                                    text(
                                        f"CREATE INDEX `ix_{table}_workspace_id` "
                                        f"ON `{table}` (workspace_id)"
                                    )
                                )
                        # 回填存量数据指向默认空间（优先"默认空间"，无则第一个空间）
                        sync_conn.execute(
                            text(
                                f"UPDATE `{table}` SET workspace_id = ("
                                "  SELECT id FROM `workspaces` WHERE name = '默认空间' "
                                "  UNION ALL SELECT id FROM `workspaces` LIMIT 1"
                                ") WHERE workspace_id IS NULL"
                            )
                        )
            # ---- data_views.database 迁移（幂等）----
            if "data_views" in inspector.get_table_names():
                columns = {c["name"] for c in inspector.get_columns("data_views")}
                if "database" not in columns:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE `data_views` ADD COLUMN `database` VARCHAR(255) DEFAULT ''"
                        )
                    )
            # ---- flows 运行配置迁移（幂等）----
            if "flows" in inspector.get_table_names():
                columns = {c["name"] for c in inspector.get_columns("flows")}
                if "run_mode" not in columns:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE `flows` ADD COLUMN run_mode VARCHAR(16) DEFAULT 'manual'"
                        )
                    )
                if "global_inputs" not in columns:
                    sync_conn.execute(
                        text("ALTER TABLE `flows` ADD COLUMN global_inputs JSON")
                    )
                    sync_conn.execute(
                        text("UPDATE `flows` SET global_inputs = '{}' WHERE global_inputs IS NULL")
                    )

        await conn.run_sync(_migrate)
