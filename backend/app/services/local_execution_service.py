"""单进程本地执行器：数据库 pending 记录是持久队列，不依赖 Redis。"""

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.execution import Execution


class LocalExecutor:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        run_job: Callable[[int], Awaitable[object]] | None = None,
        max_jobs: int | None = None,
        lock_path: str | Path | None = None,
        poll_interval: float = 0.5,
    ):
        self.session_factory = session_factory or AsyncSessionLocal
        self.run_job = run_job
        self.max_jobs = max_jobs or settings.max_concurrent_executions
        self.lock_path = Path(lock_path or settings.storage_dir / "local-executor.lock")
        self.poll_interval = poll_interval
        self.jobs: dict[int, asyncio.Task] = {}
        self._dispatcher: asyncio.Task | None = None
        self._wake: asyncio.Event | None = None
        self._lock_file = None
        self.running = False

    def _acquire_lock(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                handle.write(b"0")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError(
                "本地执行器已运行：local 模式仅允许一个服务进程，请使用 --workers 1，且不要同时启动完整应用和最小 MCP 应用"
            ) from exc
        self._lock_file = handle

    def _release_lock(self) -> None:
        if self._lock_file is not None:
            if os.name == "nt":
                import msvcrt

                self._lock_file.seek(0)
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            self._lock_file.close()
            self._lock_file = None

    async def start(self) -> None:
        if self.running:
            return
        self._acquire_lock()
        try:
            from app.engine.runner import (
                cleanup_execution_temp_files,
                cleanup_orphan_execution_files,
            )

            async with self.session_factory() as db:
                interrupted = list(
                    (
                        await db.scalars(
                            select(Execution.id).where(Execution.status == "running")
                        )
                    ).all()
                )
                await db.execute(
                    update(Execution)
                    .where(Execution.status == "running")
                    .values(
                        status="failed",
                        finished_at=datetime.now(),
                        logs=func.coalesce(Execution.logs, "")
                        + "\nError: 本地服务重启，执行中断\n",
                    )
                )
                await db.execute(
                    update(Execution)
                    .where(
                        Execution.status == "pending", Execution.target_type != "script"
                    )
                    .values(
                        status="failed",
                        finished_at=datetime.now(),
                        logs=func.coalesce(Execution.logs, "")
                        + "\nError: 该执行类型已停用\n",
                    )
                )
                await db.commit()
            for execution_id in interrupted:
                cleanup_execution_temp_files(execution_id)
            cleanup_orphan_execution_files()
            self._wake = asyncio.Event()
            self.running = True
            self._dispatcher = asyncio.create_task(self._dispatch_loop())
        except BaseException:
            self._release_lock()
            raise

    def notify(self) -> None:
        if self._wake is not None:
            self._wake.set()

    async def _dispatch_loop(self) -> None:
        while self.running:
            self._wake.clear()
            try:
                slots = self.max_jobs - len(self.jobs)
                if slots > 0:
                    async with self.session_factory() as db:
                        ids = list(
                            (
                                await db.scalars(
                                    select(Execution.id)
                                    .where(
                                        Execution.status == "pending",
                                        Execution.target_type == "script",
                                        Execution.id.not_in(list(self.jobs)),
                                    )
                                    .order_by(Execution.id)
                                    .limit(slots)
                                )
                            ).all()
                        )
                    for execution_id in ids:
                        self.jobs[execution_id] = asyncio.create_task(
                            self._execute(execution_id)
                        )
            except asyncio.CancelledError:
                raise
            except Exception:
                # 数据库短暂不可用时保留 pending，下轮继续，不丢弃持久任务。
                pass
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    async def _mark_failed(self, execution_id: int, message: str) -> None:
        async with self.session_factory() as db:
            await db.execute(
                update(Execution)
                .where(
                    Execution.id == execution_id,
                    Execution.status.in_(["pending", "running"]),
                )
                .values(
                    status="failed",
                    finished_at=datetime.now(),
                    logs=func.coalesce(Execution.logs, "") + message,
                )
            )
            await db.commit()

    async def _execute(self, execution_id: int) -> None:
        try:
            from app.services.script_run_service import run_script_execution

            await asyncio.wait_for(
                (self.run_job or run_script_execution)(execution_id),
                timeout=settings.script_execution_timeout + 30,
            )
        except asyncio.CancelledError:
            await self._record_failure(
                execution_id, "\nError: 本地执行器已停止，任务中断\n"
            )
        except Exception as exc:
            await self._record_failure(
                execution_id, f"\nError: 本地执行器异常（{type(exc).__name__}）\n"
            )
        finally:
            self.jobs.pop(execution_id, None)
            self.notify()

    async def _record_failure(self, execution_id: int, message: str) -> None:
        try:
            await self._mark_failed(execution_id, message)
        except Exception as exc:
            print(
                f"[local] 任务 {execution_id} 失败状态落库失败：{type(exc).__name__}",
                file=sys.stderr,
            )

    async def stop(self) -> None:
        self.running = False
        try:
            if self._dispatcher is not None:
                self._dispatcher.cancel()
                with suppress(asyncio.CancelledError):
                    await self._dispatcher
                self._dispatcher = None
            tasks = list(self.jobs.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.jobs.clear()
        finally:
            self._release_lock()

    async def stats(self) -> dict:
        async with self.session_factory() as db:
            depth = await db.scalar(
                select(func.count())
                .select_from(Execution)
                .where(Execution.status == "pending")
            )
        return {
            "backend": "local",
            "available": self.running,
            "depth": depth,
            "worker_alive": self.running,
            "running": len(self.jobs),
        }


local_executor = LocalExecutor()
