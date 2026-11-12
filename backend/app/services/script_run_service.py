"""脚本运行共享编排：REST 路由（POST /api/scripts/{id}/run）与 MCP run_script 工具共用。

- start_script_execution：创建 pending 状态 Execution 并提交执行队列，立即返回
  （worker 进程按 max_concurrent_executions 并发上限调度实际执行）
- run_script_execution：worker 侧 job 业务体（LogBus 流式日志 → 子进程执行 → 回写终态）
"""

import asyncio
from datetime import datetime
from typing import Any, Literal, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.engine.mock_generator import generate_mock_inputs
from app.engine.runner import (
    cleanup_execution_temp_files,
    execute_script_code,
    validate_script_code,
)
from app.models.execution import Execution
from app.models.script import Script
from app.services import (
    data_view_service,
    execution_service,
    global_variable_service,
    script_service,
)
from app.services.log_bus import ExecutionLogBus
from app.task_queue import QueueUnavailableError, enqueue_script_run


async def start_script_execution(
    db: AsyncSession,
    script: Script,
    *,
    mode: Literal["manual", "mock"] = "manual",
    inputs: dict[str, Any] | None = None,
    headless: bool | None = None,
    on_created: Callable[[Execution], None] | None = None,
) -> Execution:
    """创建 pending 状态 Execution 并入队，立即返回。

    队列不可用（Redis 未启动）时抛 QueueUnavailableError，该执行留痕为 failed。
    """
    validate_script_code(script.code)
    user_inputs = {
        d["name"]: d["default"]
        for d in (script.inputs or [])
        if d.get("default") is not None
    }
    user_inputs.update(inputs or {})
    execution = Execution(
        target_type="script",
        target_id=script.id,
        mode=mode,
        inputs=user_inputs,
        status="pending",
        logs="",
        outputs={},
        started_at=datetime.now(),
    )
    db.add(execution)
    await db.flush()
    if on_created is not None:
        on_created(execution)
    await db.commit()
    await db.refresh(execution)

    try:
        await enqueue_script_run(execution.id, headless_override=headless)
    except QueueUnavailableError:
        execution.status = "failed"
        execution.logs = "Error: 执行队列不可用，请确认 Redis 与执行 worker 已启动\n"
        execution.finished_at = datetime.now()
        await db.commit()
        raise
    return execution


async def run_script_execution(
    execution_id: int, headless_override: bool | None = None
) -> dict:
    """worker job：执行单个脚本并回写终态。幂等：非 pending 状态直接返回。

    日志经 ExecutionLogBus 实时推送 + 增量落库；终态回写不整体覆写 logs，
    避免覆盖落库协程写入的增量。
    """
    async with AsyncSessionLocal() as session:
        execution = await execution_service.get_execution(session, execution_id)
        if execution is None or execution.status != "pending":
            return {"status": execution.status if execution else "missing"}

        if execution.target_type != "script":
            execution.status = "failed"
            execution.logs = (execution.logs or "") + "Error: 该执行类型已停用\n"
            execution.finished_at = datetime.now()
            await session.commit()
            return {"status": execution.status}

        bus = ExecutionLogBus(execution_id)
        await bus.start()

        def log_callback(msg: str):
            bus.append(msg)

        try:
            execution.status = "running"
            execution.started_at = datetime.now()
            await session.commit()

            script = await script_service.get_script(session, execution.target_id)
            if script is None:
                raise RuntimeError(f"脚本 {execution.target_id} 不存在（可能已被删除）")

            task_inputs = (
                execution.inputs
                if execution.mode == "manual"
                else generate_mock_inputs(script.inputs)
            )

            if script.inherit_global:
                headers, gvars, local_storage, cookies = (
                    await global_variable_service.get_active_globals_grouped(
                        session, script.start_url or ""
                    )
                )
            else:
                headers, gvars, local_storage, cookies = {}, {}, {}, []

            view_data = (
                await data_view_service.collect_view_data_cached(session)
                if validate_script_code(script.code)["uses_data_views"]
                else {}
            )

            _, outputs = await execute_script_code(
                script,
                task_inputs,
                execution_id,
                log_callback,
                global_headers=headers,
                global_vars=gvars,
                global_local_storage=local_storage,
                global_cookies=cookies,
                data_views=view_data,
                headless=(
                    headless_override
                    if headless_override is not None
                    else script.headless
                ),
            )
            execution.status = "success"
            execution.outputs = outputs
        except asyncio.CancelledError:
            # worker 超时/关闭取消：落终态 failed，而不是留 running 僵尸记录
            bus.append("Error: 执行被取消（worker 超时或关闭）\n")
            execution.status = "failed"
            execution.outputs = {}
        except Exception as exc:
            bus.append(f"Error: {exc}\n")
            execution.status = "failed"
            execution.outputs = {}
        finally:
            execution.finished_at = datetime.now()
            await bus.finalize()  # 最后一次增量落库（终态 commit 之前）
            await session.commit()
            await bus.close(publish_eof=True)  # EOF 在终态落库后发布
            cleanup_execution_temp_files(execution_id)
        return {"status": execution.status}
