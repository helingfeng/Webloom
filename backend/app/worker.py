"""arq worker 入口：实际执行采集脚本任务。

启动：``cd backend && ./venv/bin/arq app.worker.WorkerSettings``（无 --reload，改代码需手动重启）。

- 并发上限：``max_jobs = settings.max_concurrent_executions``
- 崩溃恢复（on_startup）：running → failed（中断）；残留 job 键清理；
  pending 由心跳循环兜底重入队（Redis 重启丢队列后自愈）
- 心跳：每 10s 续期 ``fishcode:worker:heartbeat``（TTL 30s），/api/health 据此判断 worker 存活
"""

import asyncio
import time
from datetime import datetime, timedelta

from arq import constants as arq_constants
from arq import func
from arq.connections import RedisSettings
from sqlalchemy import select, or_

from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.engine.runner import cleanup_execution_temp_files
from app.models.execution import Execution
from app.services import script_run_service
from app.services.datasource_query_service import connection_manager
from app.task_queue import (
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TTL,
    WORKER_HEARTBEAT_KEY,
    enqueue_script_run,
    job_key,
)

ORPHAN_FILE_MAX_AGE = 24 * 3600  # 临时目录孤儿文件清扫阈值（秒）
PENDING_REENQUEUE_MIN_AGE = 60  # pending 超过该秒数才兜底重入队（正常排队不受影响）


async def run_script_execution(
    ctx: dict, execution_id: int, headless_override: bool | None = None
) -> dict:
    return await script_run_service.run_script_execution(
        execution_id, headless_override
    )


def cleanup_orphan_files(max_age_seconds: int = ORPHAN_FILE_MAX_AGE) -> None:
    """清扫临时目录中超过阈值的孤儿运行文件/画面帧（崩溃残留兜底）"""
    if not settings.executions_dir.exists():
        return
    cutoff = time.time() - max_age_seconds
    for path in settings.executions_dir.iterdir():
        is_temp = (
            path.name.startswith("run_") and path.suffix == ".py"
        ) or path.name.startswith("frame_")
        if not is_temp or not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


async def recover_interrupted(redis) -> None:
    """worker 启动恢复：running → failed（worker 重启中断），并清理残留 job 键。

    pending 不在此处理：队列中未跑的任务由 arq 自行恢复；
    Redis 侧丢失的任务由心跳循环的 pending 兜底重入队补齐。
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Execution).where(Execution.status == "running")
        )
        interrupted = result.scalars().all()
        ids: list[int] = []
        for execution in interrupted:
            execution.status = "failed"
            prefix = "\n" if execution.logs else ""
            execution.logs = (
                f"{execution.logs or ''}{prefix}Error: worker 重启，执行中断\n"
            )
            execution.finished_at = datetime.now()
            ids.append(execution.id)
        await session.commit()

    if not ids:
        return
    try:
        keys = []
        for execution_id in ids:
            keys.append(job_key(execution_id))
            keys.append(f"{arq_constants.in_progress_key_prefix}exec:{execution_id}")
        await redis.delete(*keys)
    except Exception:
        pass  # 键残留只影响该执行的重入队去重，不影响运行


async def recover_pending(redis) -> None:
    """超龄脚本重入队；已停用类型的遗留任务落失败状态并移出队列。"""
    cutoff = datetime.now() - timedelta(seconds=PENDING_REENQUEUE_MIN_AGE)
    retired_ids: list[int] = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Execution).where(
                Execution.status == "pending",
                or_(Execution.target_type != "script", Execution.started_at < cutoff),
            )
        )
        script_ids: list[int] = []
        for execution in result.scalars().all():
            if execution.target_type == "script":
                script_ids.append(execution.id)
            else:
                execution.status = "failed"
                execution.logs = (
                    execution.logs or ""
                ) + "Error: 该执行类型已停用，任务不会再执行\n"
                execution.finished_at = datetime.now()
                retired_ids.append(execution.id)
        await session.commit()

    for execution_id in retired_ids:
        try:
            await redis.zrem(arq_constants.default_queue_name, f"exec:{execution_id}")
            await redis.delete(job_key(execution_id))
        except Exception:
            pass  # 数据库终态已经阻止再次执行，Redis 残留交由队列清理。
    for execution_id in script_ids:
        try:
            await enqueue_script_run(execution_id)
        except Exception:
            continue  # Redis 不可用时下轮心跳重试


async def _heartbeat(ctx: dict) -> None:
    redis = ctx["redis"]
    while True:
        try:
            await redis.set(WORKER_HEARTBEAT_KEY, "1", ex=HEARTBEAT_TTL)
            await recover_pending(redis)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # Redis 瞬断：下轮心跳重试
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def on_startup(ctx: dict) -> None:
    await init_db()
    await recover_interrupted(ctx["redis"])
    await recover_pending(ctx["redis"])
    cleanup_orphan_files()
    ctx["heartbeat_task"] = asyncio.create_task(_heartbeat(ctx))


async def on_shutdown(ctx: dict) -> None:
    task = ctx.pop("heartbeat_task", None)
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await connection_manager.dispose_all()


class WorkerSettings:
    """arq WorkerSettings：``arq app.worker.WorkerSettings``"""

    functions = [
        func(run_script_execution, max_tries=1),
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = settings.max_concurrent_executions
    # 脚本层 120s 先触发 kill，留回写裕量；超过则 job 被 arq 取消（job 内已兜底落终态）
    job_timeout = settings.script_execution_timeout + 30
    keep_result = 0  # 结果已落 MySQL；job 结束后立即可复用 _job_id
    on_startup = on_startup
    on_shutdown = on_shutdown


def _supervise() -> None:
    """worker 进程入口：``cd backend && ./venv/bin/python3 -m app.worker``

    Redis 瞬断/重启会让 arq 主循环抛 ConnectionError 退出，
    此处自动等待 5s 重建 worker；队列持久在 Redis，恢复后继续消费，
    pending 兜底重入队保证不丢任务。SIGTERM/SIGINT 时优雅退出。
    """
    import sys
    import time

    from arq import run_worker

    while True:
        try:
            run_worker(WorkerSettings)
            return
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"[worker] arq 主循环退出：{exc!r}，5s 后自动重启…", file=sys.stderr)
            time.sleep(5)


if __name__ == "__main__":
    _supervise()
