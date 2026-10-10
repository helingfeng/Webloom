"""异步测试基建：SQLite 内存库 + 假 Redis。

pytest.ini 已设 asyncio_mode=auto，async 测试函数无需装饰器。
"""

import asyncio
from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):
    """SQLite 下把 BIGINT 主键编译为 INTEGER，使 rowid 别名自增生效（仅测试环境）"""
    return "INTEGER"


@pytest_asyncio.fixture
async def db_engine():
    """每个测试独立的 SQLite 内存库（含全部表结构）"""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


class FakeRedis:
    """最小可用的假 Redis：pub/sub 收集 + kv + 删除记录，供单测注入"""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.kv: dict[str, str] = {}
        self.deleted: list[str] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.kv[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            self.deleted.append(k)
            if k in self.kv:
                del self.kv[k]
                n += 1
        return n

    async def zcard(self, key: str) -> int:
        return 0


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()
