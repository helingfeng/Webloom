"""脚本运行共享编排：创建 Execution + 后台任务。

REST 路由（POST /api/scripts/{id}/run）与 MCP run_script 工具共用，
避免各自复制全局变量/数据视图注入逻辑。
"""

import asyncio
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.engine.mock_generator import generate_mock_inputs
from app.engine.runner import execute_script_code
from app.models.execution import Execution
from app.models.script import Script
from app.services import data_view_service, execution_service, global_variable_service, script_service
from app.websocket import manager

# 持有后台任务引用，防止被 GC 提前回收
_background_tasks: set[asyncio.Task] = set()


async def start_script_execution(
    db: AsyncSession,
    script: Script,
    *,
    mode: Literal["manual", "mock"] = "manual",
    inputs: dict[str, Any] | None = None,
    headless: bool = True,
) -> Execution:
    """创建 running 状态 Execution 并提交，随后启动后台执行任务，立即返回。"""
    user_inputs = inputs or {}
    execution = Execution(
        target_type="script",
        target_id=script.id,
        mode=mode,
        inputs=user_inputs,
        status="running",
        logs="",
        outputs={},
        started_at=datetime.now(),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    task = asyncio.create_task(
        _run_script_task(execution.id, script.id, mode, user_inputs, headless)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return execution


async def _run_script_task(
    execution_id: int,
    script_id: int,
    mode: str,
    user_inputs: dict[str, Any],
    headless: bool,
) -> None:
    """后台执行：独立会话，完成后回写执行记录。"""
    async with AsyncSessionLocal() as session:
        execution = await execution_service.get_execution(session, execution_id)
        if not execution:
            return
        try:
            script = await script_service.get_script(session, script_id)
            if not script:
                raise RuntimeError(f"脚本 {script_id} 不存在（可能已被删除）")
            task_inputs = (
                user_inputs if mode == "manual" else generate_mock_inputs(script.inputs)
            )

            def log_callback(msg: str):
                asyncio.create_task(manager.send_log(execution_id, msg))

            if script.inherit_global:
                start_url = script.start_url or ""
                headers = await global_variable_service.get_active_headers(session, start_url)
                gvars = await global_variable_service.get_active_vars(session, start_url)
                local_storage = await global_variable_service.get_active_local_storage(
                    session, start_url
                )
                cookies = await global_variable_service.get_active_cookies(session, start_url)
            else:
                headers, gvars, local_storage, cookies = {}, {}, {}, []

            view_data = await data_view_service.collect_view_data(session)

            logs, outputs = await execute_script_code(
                script,
                task_inputs,
                execution_id,
                log_callback,
                global_headers=headers,
                global_vars=gvars,
                global_local_storage=local_storage,
                global_cookies=cookies,
                data_views=view_data,
                headless=headless,
            )
            execution.status = "success"
            execution.logs = logs
            execution.outputs = outputs
        except Exception as exc:
            execution.status = "failed"
            detail_logs = getattr(exc, "logs", "") or ""
            error_msg = f"Error: {exc}"
            execution.logs = (
                f"{detail_logs}\n{error_msg}".strip() if detail_logs else error_msg
            )
            execution.outputs = {}
            asyncio.create_task(manager.send_log(execution_id, error_msg))
        finally:
            execution.finished_at = datetime.now()
            await session.commit()
