"""开放应用与调用日志管理、采集接口，以及旧版通用采集入口。"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.routers.collectors import public_router as collectors_public_router
from app.database import get_db
from app.schemas.open_platform import (
    OpenApiLogOut,
    OpenApiLogPageOut,
    OpenAppCreate,
    OpenAppDetailOut,
    OpenAppOut,
    OpenAppPageOut,
    OpenAppSecretOut,
    OpenAppUpdate,
)
from app.services import (
    execution_service,
    open_api_service,
    open_app_service,
    script_service,
)
from app.services.script_run_service import start_script_execution
from app.task_queue import QueueUnavailableError

# ---------------- 管理端：开放应用 ----------------

open_apps_router = APIRouter()


async def _get_app_or_404(db: AsyncSession, app_id: int):
    app = await open_app_service.get_open_app(db, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="Open app not found")
    return app


@open_apps_router.get("", response_model=OpenAppPageOut)
async def list_open_apps(
    skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> Any:
    items = await open_app_service.get_open_apps(db, skip=skip, limit=limit)
    total = await open_app_service.count_open_apps(db)
    return {"items": items, "total": total}


@open_apps_router.post("", response_model=OpenAppDetailOut, status_code=201)
async def create_open_app(
    app_in: OpenAppCreate, db: AsyncSession = Depends(get_db)
) -> Any:
    try:
        return await open_app_service.create_open_app(db, app_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@open_apps_router.get("/{app_id}", response_model=OpenAppDetailOut)
async def get_open_app(app_id: int, db: AsyncSession = Depends(get_db)) -> Any:
    return await _get_app_or_404(db, app_id)


@open_apps_router.put("/{app_id}", response_model=OpenAppOut)
async def update_open_app(
    app_id: int, app_in: OpenAppUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    app = await _get_app_or_404(db, app_id)
    try:
        return await open_app_service.update_open_app(db, app, app_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@open_apps_router.post("/{app_id}/regenerate-secret", response_model=OpenAppSecretOut)
async def regenerate_open_app_secret(
    app_id: int, db: AsyncSession = Depends(get_db)
) -> Any:
    app = await _get_app_or_404(db, app_id)
    app = await open_app_service.regenerate_secret(db, app)
    return {"app_key": app.app_key, "app_secret": app.app_secret}


@open_apps_router.delete("/{app_id}", status_code=204)
async def delete_open_app(app_id: int, db: AsyncSession = Depends(get_db)) -> None:
    app = await _get_app_or_404(db, app_id)
    await open_app_service.delete_open_app(db, app)


# ---------------- 管理端：调用日志 ----------------

open_logs_router = APIRouter()


@open_logs_router.get("", response_model=OpenApiLogPageOut)
async def list_open_logs(
    skip: int = 0,
    limit: int = 20,
    app_id: int | None = None,
    success: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    items = await open_api_service.get_logs(
        db, skip=skip, limit=limit, app_id=app_id, success=success
    )
    total = await open_api_service.count_logs(db, app_id=app_id, success=success)
    return {"items": items, "total": total}


@open_logs_router.delete("", status_code=204)
async def clear_open_logs(db: AsyncSession = Depends(get_db)) -> None:
    await open_api_service.clear_logs(db)


# ---------------- 开放端点（/open 前缀）----------------

open_router = APIRouter()

_TRIGGER_PATH = "/open/api/v1/collect/trigger"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


async def _auth_or_response(
    db: AsyncSession, request: Request
) -> tuple[Any, Response | None]:
    """认证 + 失败留痕。通过返回 (app, None)；失败返回 (None, 已记录日志的 401 Response)"""
    app_key = request.headers.get("X-App-Key", "")
    app, err = await open_app_service.authenticate_request(db, request)
    if app is None:
        await open_api_service.record_open_log(
            db,
            app_id=None,
            app_key=app_key,
            path=request.url.path,
            method=request.method,
            status_code=401,
            success=False,
            request_ip=_client_ip(request),
            detail=err,
        )
        return None, Response(
            content=json.dumps({"detail": err}, ensure_ascii=False),
            status_code=401,
            media_type="application/json",
        )
    return app, None


@open_router.post("/api/v1/collect/trigger")
async def open_collect_trigger(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Any:
    """开放数据采集：传入链接发起指定脚本执行（异步，立即返回 execution_id）"""
    app, error_response = await _auth_or_response(db, request)
    if error_response is not None:
        return error_response

    try:
        payload = json.loads(request.state.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = None
    if not isinstance(payload, dict):
        payload = None

    url = str(payload.get("url") or "").strip() if payload else ""
    script_id = payload.get("script_id") if payload else None
    error: str | None = None
    if payload is None:
        error = "请求体必须为 JSON 对象"
    elif not url:
        error = "url 不能为空"
    elif not isinstance(script_id, int):
        error = "script_id 必须为整数"

    if error is not None:
        await open_api_service.record_open_log(
            db,
            app_id=app.id,
            app_key=app.app_key,
            path=request.url.path,
            method=request.method,
            status_code=400,
            success=False,
            request_ip=_client_ip(request),
            detail=error,
        )
        return Response(
            content=json.dumps({"detail": error}, ensure_ascii=False),
            status_code=400,
            media_type="application/json",
        )

    script = await script_service.get_script(db, script_id)
    if script is None:
        error = f"脚本 {script_id} 不存在"
        await open_api_service.record_open_log(
            db,
            app_id=app.id,
            app_key=app.app_key,
            path=request.url.path,
            method=request.method,
            status_code=404,
            success=False,
            request_ip=_client_ip(request),
            detail=error,
        )
        return Response(
            content=json.dumps({"detail": error}, ensure_ascii=False),
            status_code=404,
            media_type="application/json",
        )

    extra_inputs = payload.get("inputs")
    inputs = {**(extra_inputs if isinstance(extra_inputs, dict) else {}), "url": url}
    try:
        execution = await start_script_execution(
            db,
            script,
            mode="manual",
            inputs=inputs,
            headless=payload.get("headless"),
        )
    except QueueUnavailableError as exc:
        await open_api_service.record_open_log(
            db,
            app_id=app.id,
            app_key=app.app_key,
            path=request.url.path,
            method=request.method,
            status_code=503,
            success=False,
            request_ip=_client_ip(request),
            detail=f"执行队列不可用：{exc}",
        )
        return Response(
            content=json.dumps(
                {"detail": "执行队列不可用，请稍后重试"}, ensure_ascii=False
            ),
            status_code=503,
            media_type="application/json",
        )

    await open_api_service.record_open_log(
        db,
        app_id=app.id,
        app_key=app.app_key,
        path=request.url.path,
        method=request.method,
        status_code=200,
        success=True,
        execution_id=execution.id,
        request_ip=_client_ip(request),
        detail=f"脚本 {script.name}",
    )
    return {
        "execution_id": execution.id,
        "status": execution.status,
        "next": f"GET /open/api/v1/collect/result?execution_id={execution.id}",
    }


@open_router.get("/api/v1/collect/result")
async def open_collect_result(
    request: Request, execution_id: int, db: AsyncSession = Depends(get_db)
) -> Any:
    """开放采集结果查询：仅能查询本应用触发的执行"""
    app, error_response = await _auth_or_response(db, request)
    if error_response is not None:
        return error_response

    owned = await open_api_service.owned_execution_ids(
        db, app.id, limit=200, script_path_only=False
    )
    if execution_id not in owned:
        error = "执行不存在或无权查询"
        await open_api_service.record_open_log(
            db,
            app_id=app.id,
            app_key=app.app_key,
            path=request.url.path,
            method=request.method,
            status_code=404,
            success=False,
            execution_id=execution_id,
            request_ip=_client_ip(request),
            detail=error,
        )
        return Response(
            content=json.dumps({"detail": error}, ensure_ascii=False),
            status_code=404,
            media_type="application/json",
        )

    execution = await execution_service.get_execution(db, execution_id)
    if execution is None:
        return Response(
            content=json.dumps({"detail": "执行不存在或无权查询"}, ensure_ascii=False),
            status_code=404,
            media_type="application/json",
        )

    return {
        "execution_id": execution.id,
        "script_id": execution.target_id if execution.target_type == "script" else None,
        "status": execution.status,
        "finished": execution.status in ("success", "failed"),
        "outputs": execution.outputs or {},
        "started_at": execution.started_at,
        "finished_at": execution.finished_at,
    }


@open_router.get("/api/v1/collect/tasks")
async def open_collect_tasks(
    request: Request,
    script_id: int | None = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """开放采集任务列表：本应用最近触发的执行（新→旧，最多 50 条）"""
    app, error_response = await _auth_or_response(db, request)
    if error_response is not None:
        return error_response

    limit = max(1, min(limit, 50))
    owned = await open_api_service.owned_execution_ids(db, app.id, limit=50)
    tasks: list[dict[str, Any]] = []
    for eid in owned:
        execution = await execution_service.get_execution(db, eid)
        if execution is None:
            continue
        if execution.target_type != "script":
            continue
        if script_id is not None and execution.target_id != script_id:
            continue
        tasks.append(
            {
                "execution_id": execution.id,
                "script_id": execution.target_id,
                "status": execution.status,
                "finished": execution.status in ("success", "failed"),
                "started_at": execution.started_at,
                "finished_at": execution.finished_at,
            }
        )
        if len(tasks) >= limit:
            break
    return {"items": tasks, "total": len(tasks)}


open_router.include_router(collectors_public_router)
