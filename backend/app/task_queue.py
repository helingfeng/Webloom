"""执行后端入口：默认数据库持久队列 + 本地执行器，可选 Redis/arq。

API 创建 Execution(status=pending) 并提交，再由选定执行器并发执行。
本地模式不初始化 Redis。显式 Redis 模式依赖独立 worker，
队列不可用时抛 QueueUnavailableError，由调用方转为 503 / ToolError。
"""

import asyncio

from arq import constants as arq_constants
from arq.connections import ArqRedis, RedisSettings, create_pool

from app.config import settings

WORKER_HEARTBEAT_KEY = "fishcode:worker:heartbeat"
HEARTBEAT_TTL = 30  # 秒；worker 每 10s 续期
HEARTBEAT_INTERVAL = 10  # 秒
EXECUTION_JOB_PREFIX = "exec:"


class QueueUnavailableError(RuntimeError):
    """任务队列不可用（Redis 连接失败等）"""


_pool: ArqRedis | None = None
_pool_lock = asyncio.Lock()


async def get_pool() -> ArqRedis:
    """懒初始化模块级 RpcPool（Redis 不可达时抛 QueueUnavailableError）"""
    global _pool
    if settings.execution_backend != "redis":
        raise QueueUnavailableError("本地执行模式不使用 Redis")
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            try:
                _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            except Exception as exc:
                raise QueueUnavailableError(f"任务队列不可用：{exc}") from exc
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            await _pool.aclose()
        except Exception:
            pass
        _pool = None


def _job_id(execution_id: int) -> str:
    return f"{EXECUTION_JOB_PREFIX}{execution_id}"


def job_key(execution_id: int) -> str:
    """arq 侧 job 哈希键（崩溃恢复清理残留用）"""
    return f"{arq_constants.job_key_prefix}{_job_id(execution_id)}"


async def enqueue_script_run(
    execution_id: int, headless_override: bool | None = None
) -> None:
    if settings.execution_backend == "local":
        from app.services.local_execution_service import local_executor

        if not local_executor.running:
            raise QueueUnavailableError(
                "本地执行器未启动，请通过应用 lifespan 启动服务"
            )
        local_executor.notify()
        return
    try:
        pool = await get_pool()
        await pool.enqueue_job(
            "run_script_execution",
            execution_id,
            headless_override,
            _job_id=_job_id(execution_id),
        )
    except QueueUnavailableError:
        raise
    except Exception as exc:
        # 连接中断（Redis 重启/宕机）等统一转为 QueueUnavailableError
        await _drop_broken_pool(exc)
        raise QueueUnavailableError(f"任务队列不可用：{exc}") from exc


async def _drop_broken_pool(exc: Exception) -> None:
    """连接类异常时丢弃缓存池，下次入队重建（Redis 重启后自愈）"""
    from redis.exceptions import ConnectionError as RedisConnectionError

    if isinstance(exc, RedisConnectionError) or "Connection" in type(exc).__name__:
        global _pool
        _pool = None


async def queue_stats() -> dict:
    """队列健康状态：{available, depth, worker_alive}；任何异常降级为不可用，绝不抛出"""
    try:
        if settings.execution_backend == "local":
            from app.services.local_execution_service import local_executor

            return await local_executor.stats()
        pool = await get_pool()
        depth = await pool.zcard(arq_constants.default_queue_name)
        alive = await pool.get(WORKER_HEARTBEAT_KEY)
        return {"available": True, "depth": depth, "worker_alive": alive is not None}
    except Exception:
        return {"available": False, "depth": None, "worker_alive": False}


async def start_execution_backend() -> None:
    if settings.execution_backend == "local":
        from app.services.local_execution_service import local_executor

        await local_executor.start()
    else:
        try:
            await get_pool()
        except QueueUnavailableError:
            pass  # Redis 故障时保留管理功能，提交执行返回 503。


async def stop_execution_backend() -> None:
    if settings.execution_backend == "local":
        from app.services.local_execution_service import local_executor

        await local_executor.stop()
    await close_pool()
    from app.services.log_bus import close_redis

    await close_redis()
