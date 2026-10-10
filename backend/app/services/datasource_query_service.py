"""数据源查询服务：MySQL 连接池管理 + 测试连接 + 表结构 + SQL 执行。

唯一有状态的服务：connection_manager 按 (datasource_id, database) 缓存 AsyncEngine。
"""

import asyncio
import time
from decimal import Decimal
from datetime import date, datetime, time as dt_time, timedelta

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings
from app.models.datasource import Datasource
from app.schemas.datasource import (
    DatasourceColumn,
    DatasourceTable,
    DatasourceTestRequest,
    DatasourceTestResult,
    QueryResult,
)

TEST_CONNECT_TIMEOUT = 10  # 测试连接短超时（秒）

# 首 token 白名单：这些语句返回结果集，走查询路径
_QUERY_TOKENS = {
    "select",
    "show",
    "desc",
    "describe",
    "explain",
    "with",
    "values",
    "table",
    "analyze",
    "check",
    "optimize",
    "repair",
    "checksum",
}

# 数据视图只读白名单：刻意不含 analyze/check/optimize/repair/checksum
# （它们虽返回结果集，但可能锁表/修改统计信息）
_READ_ONLY_TOKENS = {
    "select",
    "show",
    "desc",
    "describe",
    "explain",
    "with",
    "values",
    "table",
}


def _build_url(host: str, port: int, user: str, password: str, database: str) -> URL:
    # URL.create 自动转义密码中的特殊字符（@ : / 等）
    return URL.create(
        "mysql+aiomysql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database or None,
        query={"charset": "utf8mb4"},
    )


class DatasourceConnectionManager:
    """按 (datasource_id, database) 缓存 AsyncEngine；配置变更/超时后 invalidate 重建"""

    def __init__(self) -> None:
        self._engines: dict[tuple[int, str], AsyncEngine] = {}
        # master 锁只保护 _locks 字典本身；不同 key 的建连/销毁互不阻塞
        self._master = asyncio.Lock()
        self._locks: dict[tuple[int, str], asyncio.Lock] = {}

    async def _key_lock(self, key: tuple[int, str]) -> asyncio.Lock:
        async with self._master:
            return self._locks.setdefault(key, asyncio.Lock())

    async def get_engine(
        self, ds: Datasource, database: str | None = None
    ) -> AsyncEngine:
        effective = database or ds.database
        key = (ds.id, effective)
        lock = await self._key_lock(key)
        async with lock:
            engine = self._engines.get(key)
            if engine is not None:
                return engine
            engine = create_async_engine(
                _build_url(ds.host, ds.port, ds.user, ds.password, effective),
                pool_pre_ping=True,
                pool_size=settings.datasource_pool_size,
                max_overflow=settings.datasource_max_overflow,
                pool_recycle=3600,
            )
            self._engines[key] = engine
            return engine

    async def invalidate(self, ds_id: int) -> None:
        """释放该数据源全部库的 engine（切库/配置变更后连接状态不可复用）"""
        async with self._master:
            keys = [k for k in self._engines if k[0] == ds_id]
        for key in keys:
            await self.invalidate_engine(ds_id, key[1])

    async def invalidate_engine(self, ds_id: int, database: str | None = None) -> None:
        """仅释放 (datasource_id, database) 对应的 engine；database=None 时退化为整个数据源。

        高并发下一个库的慢查询超时只重建该库的连接池，不殃及其他库。
        """
        if database is None:
            await self.invalidate(ds_id)
            return
        key = (ds_id, database)
        # 与 get_engine 按 key 互斥：等在途建连完成后再销毁
        lock = await self._key_lock(key)
        async with lock:
            async with self._master:
                engine = self._engines.pop(key, None)
        if engine is not None:
            await engine.dispose()

    async def dispose_all(self) -> None:
        async with self._master:
            engines = list(self._engines.values())
            self._engines.clear()
        for engine in engines:
            await engine.dispose()


connection_manager = DatasourceConnectionManager()


async def test_connection(req: DatasourceTestRequest) -> DatasourceTestResult:
    """临时连接测试，不走缓存；失败是业务结果而非异常"""
    start = time.perf_counter()
    engine = create_async_engine(
        _build_url(req.host, req.port, req.user, req.password, req.database)
    )
    try:

        async def _probe() -> str:
            async with engine.connect() as conn:
                result = await conn.exec_driver_sql("SELECT VERSION()")
                return result.scalar_one()

        version = await asyncio.wait_for(_probe(), timeout=TEST_CONNECT_TIMEOUT)
        return DatasourceTestResult(
            success=True,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            server_version=version,
        )
    except TimeoutError:
        # TimeoutError 的 str() 为空，必须给明确文案（否则前端显示"未知错误"）
        return DatasourceTestResult(
            success=False,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            error=f"连接超时（>{TEST_CONNECT_TIMEOUT}s）：请检查主机、端口是否可达及防火墙设置",
        )
    except Exception as exc:
        # 部分异常（如 CancelledError）str 为空，兜底用类名
        error = str(exc) or f"{type(exc).__name__}（无详细信息）"
        return DatasourceTestResult(
            success=False,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            error=error,
        )
    finally:
        await engine.dispose()


# 系统库：列表中对用户无意义，过滤
_SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}


async def list_databases(ds: Datasource) -> list[str]:
    """列出该连接账号可见的数据库（过滤系统库）"""
    engine = await connection_manager.get_engine(ds)
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql("SHOW DATABASES")
        return [row[0] for row in result.all() if row[0] not in _SYSTEM_DATABASES]


async def list_tables(
    ds: Datasource, database: str | None = None
) -> list[DatasourceTable]:
    effective = database or ds.database
    if not effective:
        raise ValueError("该连接未指定数据库，无法列出表")
    engine = await connection_manager.get_engine(ds, effective)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name, table_type, table_rows, table_comment "
                "FROM information_schema.tables "
                "WHERE table_schema = :db ORDER BY table_name"
            ),
            {"db": effective},
        )
        return [
            DatasourceTable(
                name=row[0],
                table_type=row[1],
                table_rows=row[2],
                comment=row[3] or "",
            )
            for row in result.all()
        ]


async def get_table_schema(
    ds: Datasource, table_name: str, database: str | None = None
) -> list[DatasourceColumn]:
    effective = database or ds.database
    if not effective:
        raise ValueError("该连接未指定数据库，无法查看表结构")
    engine = await connection_manager.get_engine(ds, effective)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name, column_type, is_nullable, column_key, "
                "column_default, extra, column_comment "
                "FROM information_schema.columns "
                "WHERE table_schema = :db AND table_name = :t "
                "ORDER BY ordinal_position"
            ),
            {"db": effective, "t": table_name},
        )
        return [
            DatasourceColumn(
                name=row[0],
                column_type=row[1],
                nullable=row[2] == "YES",
                column_key=row[3] or "",
                default=row[4],
                extra=row[5] or "",
                comment=row[6] or "",
            )
            for row in result.all()
        ]


# ---------- SQL 执行 ----------


def _strip_comments_and_literals(sql: str) -> str:
    """状态机剥离注释与引号字符串内容，返回用于分析结构的骨架。

    覆盖：-- 行注释、# 行注释、块注释、'' "" `` 引号字符串。
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        # 行注释
        if ch == "-" and nxt == "-" or ch == "#":
            while i < n and sql[i] != "\n":
                i += 1
            continue
        # 块注释
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i = min(i + 2, n)
            out.append(" ")
            continue
        # 引号字符串（保留空占位，跳过内容）
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            while i < n:
                if sql[i] == "\\" and quote != "`" and i + 1 < n:
                    i += 2
                    continue
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:  # 转义的重复引号
                        i += 2
                        continue
                    break
                i += 1
            i = min(i + 1, n)
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _preprocess(sql: str) -> str:
    """校验并清洗 SQL：空语句/多语句直接抛 ValueError"""
    skeleton = _strip_comments_and_literals(sql).strip()
    if not skeleton:
        raise ValueError("SQL 语句为空")
    # 去掉尾部单个分号后仍含分号 → 多语句
    if skeleton.endswith(";"):
        skeleton = skeleton[:-1].rstrip()
    if ";" in skeleton:
        raise ValueError("一次只能执行一条 SQL 语句，请移除多余的 ;")
    return sql.strip()


def _classify(sql: str) -> str:
    skeleton = _strip_comments_and_literals(sql).strip().lower()
    token = skeleton.split(maxsplit=1)[0] if skeleton else ""
    return "query" if token in _QUERY_TOKENS else "execute"


def validate_readonly_sql(sql: str) -> str:
    """校验 SQL 为只读查询语句（数据视图保存/执行双保险之一）。

    基于剥离注释后的骨架判断首 token，免疫 `/* */ UPDATE ...` 等注释绕过。
    通过则返回 strip 后的 SQL，否则抛 ValueError。
    """
    skeleton = _strip_comments_and_literals(sql).strip()
    if not skeleton:
        raise ValueError("SQL 语句为空")
    token = skeleton.lower().split(maxsplit=1)[0]
    if token not in _READ_ONLY_TOKENS:
        raise ValueError(
            "仅允许只读查询语句（SELECT/SHOW/DESC/DESCRIBE/EXPLAIN/WITH/VALUES/TABLE）"
        )
    return sql.strip()


def _escape_percent(sql: str) -> str:
    """aiomysql（pyformat）对无绑定参数的 SQL 也做 % 格式化，
    字面 %（如 LIKE '%x%'）必须转义为 %%，执行时由驱动还原"""
    return sql.replace("%", "%%")


def _serialize_value(value):
    """MySQL 返回值转 JSON 可序列化形式"""
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, bytes):
        return f"<binary {len(value)}B>"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, dt_time, timedelta)):
        return str(value)
    return str(value)


async def _do_fetch(engine: AsyncEngine, sql: str) -> QueryResult:
    """执行查询语句并取结果（fetchmany 截断保护），供工作台与数据视图共用"""
    max_rows = settings.sql_max_rows
    sql = _escape_percent(sql)
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql(sql, ())
        fetched = result.fetchmany(max_rows + 1)
        truncated = len(fetched) > max_rows
        rows = fetched[:max_rows]
        columns = list(result.keys())
        result.close()
        return QueryResult(
            success=True,
            statement_type="query",
            columns=columns,
            rows=[[_serialize_value(v) for v in row] for row in rows],
            row_count=len(rows),
            truncated=truncated,
        )


async def _do_execute(engine: AsyncEngine, sql: str, is_query: bool) -> QueryResult:
    max_rows = settings.sql_max_rows
    sql = _escape_percent(sql)
    async with engine.connect() as conn:
        result = await conn.exec_driver_sql(sql, ())
        if is_query:
            try:
                fetched = result.fetchmany(max_rows + 1)
                truncated = len(fetched) > max_rows
                rows = fetched[:max_rows]
                columns = list(result.keys())
                result.close()
                return QueryResult(
                    success=True,
                    statement_type="query",
                    columns=columns,
                    rows=[[_serialize_value(v) for v in row] for row in rows],
                    row_count=len(rows),
                    truncated=truncated,
                )
            except SQLAlchemyError:
                # WITH ... INSERT/UPDATE 等被误判为查询：回退走 execute 路径
                await conn.rollback()
                result = await conn.exec_driver_sql(sql)
        affected = result.rowcount
        await conn.commit()
        return QueryResult(
            success=True,
            statement_type="execute",
            affected_rows=max(affected, 0),
        )


async def execute_query(
    ds: Datasource, sql_in: str, database: str | None = None
) -> QueryResult:
    start = time.perf_counter()

    def _elapsed() -> int:
        return int((time.perf_counter() - start) * 1000)

    try:
        sql = _preprocess(sql_in)
    except ValueError as exc:
        return QueryResult(
            success=False,
            statement_type="execute",
            error=str(exc),
            elapsed_ms=_elapsed(),
        )

    is_query = _classify(sql) == "query"

    try:
        engine = await connection_manager.get_engine(ds, database)
        result = await asyncio.wait_for(
            _do_execute(engine, sql, is_query),
            timeout=settings.sql_query_timeout,
        )
        result.elapsed_ms = _elapsed()
        return result
    except TimeoutError:
        # 被取消的连接状态不可知，必须销毁（仅该库，不殃及同数据源其他库）
        await connection_manager.invalidate_engine(ds.id, database or ds.database)
        return QueryResult(
            success=False,
            statement_type="query" if is_query else "execute",
            error=f"查询超时（>{settings.sql_query_timeout}s），已终止",
            elapsed_ms=_elapsed(),
        )
    except OperationalError:
        await connection_manager.invalidate_engine(ds.id, database or ds.database)
        return QueryResult(
            success=False,
            statement_type="query" if is_query else "execute",
            error="数据库连接异常，连接已重置，请重试",
            elapsed_ms=_elapsed(),
        )
    except SQLAlchemyError as exc:
        return QueryResult(
            success=False,
            statement_type="query" if is_query else "execute",
            error=str(exc),
            elapsed_ms=_elapsed(),
        )
    except Exception as exc:
        return QueryResult(
            success=False,
            statement_type="query" if is_query else "execute",
            error=str(exc),
            elapsed_ms=_elapsed(),
        )


async def execute_readonly_query(
    ds: Datasource, sql_in: str, database: str | None = None
) -> QueryResult:
    """数据视图专用：只读校验 + 仅查询路径执行（无 execute 回退，堵死 WITH...DML）"""
    start = time.perf_counter()

    def _elapsed() -> int:
        return int((time.perf_counter() - start) * 1000)

    try:
        sql = _preprocess(sql_in)
    except ValueError as exc:
        return QueryResult(
            success=False, statement_type="query", error=str(exc), elapsed_ms=_elapsed()
        )

    try:
        sql = validate_readonly_sql(sql)
    except ValueError as exc:
        return QueryResult(
            success=False, statement_type="query", error=str(exc), elapsed_ms=_elapsed()
        )

    try:
        engine = await connection_manager.get_engine(ds, database)
        result = await asyncio.wait_for(
            _do_fetch(engine, sql),
            timeout=settings.sql_query_timeout,
        )
        result.elapsed_ms = _elapsed()
        return result
    except TimeoutError:
        await connection_manager.invalidate(ds.id)
        return QueryResult(
            success=False,
            statement_type="query",
            error=f"查询超时（>{settings.sql_query_timeout}s），已终止",
            elapsed_ms=_elapsed(),
        )
    except OperationalError:
        await connection_manager.invalidate(ds.id)
        return QueryResult(
            success=False,
            statement_type="query",
            error="数据库连接异常，连接已重置，请重试",
            elapsed_ms=_elapsed(),
        )
    except SQLAlchemyError as exc:
        return QueryResult(
            success=False,
            statement_type="query",
            error=str(exc),
            elapsed_ms=_elapsed(),
        )
    except Exception as exc:
        return QueryResult(
            success=False,
            statement_type="query",
            error=str(exc),
            elapsed_ms=_elapsed(),
        )
