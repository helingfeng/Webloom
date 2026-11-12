"""MCP 创作试跑：使用正式执行模板，不创建脚本或依赖任务队列。"""

import asyncio
import uuid

from app.engine.parameters import resolve_inputs, effective_start_url
from app.database import AsyncSessionLocal
from app.engine.runner import (
    execute_script_code,
    ScriptExecutionError,
    validate_script_code,
)
from app.models.script import Script
from app.schemas.script import ScriptCreate
from app.services import global_variable_service

_preview_slots = asyncio.Semaphore(2)


async def preview_script(payload: ScriptCreate, inputs: dict) -> dict:
    if validate_script_code(payload.code)["uses_data_views"]:
        raise ValueError("试跑不加载 DATA_VIEWS，请保存脚本后用 run_script 验证")
    values = resolve_inputs([d.model_dump() for d in payload.inputs], inputs)
    script = Script(**payload.model_dump())
    headers, variables, storage, cookies = {}, {}, {}, []
    if payload.inherit_global:
        async with AsyncSessionLocal() as db:
            headers, variables, storage, cookies = (
                await global_variable_service.get_active_globals_grouped(
                    db, effective_start_url(payload.start_url, values)
                )
            )
    # 试跑不启用实时截帧，不落库；随机 ID 避免与正式执行相互覆盖。
    async with _preview_slots:
        try:
            logs, outputs = await execute_script_code(
                script,
                values,
                -uuid.uuid4().int,
                global_headers=headers,
                global_vars=variables,
                global_local_storage=storage,
                global_cookies=cookies,
                headless=True,
                capture_frames=False,
            )
            return {"status": "success", "outputs": outputs, "logs": logs[-12000:]}
        except ScriptExecutionError as exc:
            return {"status": "failed", "error": str(exc), "logs": exc.logs[-12000:]}
