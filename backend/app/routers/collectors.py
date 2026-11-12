"""发布管理与外部采集 API；业务规则统一由 collector_service 执行。"""

import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.collector import (
    CollectorCreate,
    CollectorOut,
    CollectorPage,
    CollectorRun,
    CollectorDebug,
    CollectorTaskPage,
)
from app.services import (
    collector_service as service,
    open_app_service,
    open_api_service,
)
from app.task_queue import QueueUnavailableError


class CollectorRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except service.CollectorError as exc:
                raise HTTPException(exc.status, detail=str(exc)) from exc
            except QueueUnavailableError as exc:
                raise HTTPException(
                    503, detail="执行队列暂不可用，请稍后重试或到任务列表查看失败记录"
                ) from exc
            except ValueError as exc:
                raise HTTPException(400, detail=str(exc)) from exc

        return handler


admin_router = APIRouter(route_class=CollectorRoute)
tasks_router = APIRouter(route_class=CollectorRoute)
public_router = APIRouter(route_class=CollectorRoute)


@admin_router.get("", response_model=CollectorPage)
async def list_collectors(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_collectors(db, skip, limit)


@admin_router.post("", response_model=CollectorOut, status_code=201)
async def create_collector(
    payload: CollectorCreate, db: AsyncSession = Depends(get_db)
):
    return await service.save_collector(db, payload)


@admin_router.put("/{collector_id}", response_model=CollectorOut)
async def update_collector(
    collector_id: int, payload: CollectorCreate, db: AsyncSession = Depends(get_db)
):
    return await service.save_collector(db, payload, collector_id)


@admin_router.delete("/{collector_id}", status_code=204)
async def remove_collector(collector_id: int, db: AsyncSession = Depends(get_db)):
    await service.remove_collector(db, collector_id)
    return Response(status_code=204)


@admin_router.get("/{collector_id}/contract")
async def get_contract(collector_id: int, db: AsyncSession = Depends(get_db)):
    return await service.contract(db, await service.get_collector(db, collector_id))


@admin_router.post("/{collector_id}/debug")
async def debug_collector(
    collector_id: int, payload: CollectorDebug, db: AsyncSession = Depends(get_db)
):
    collector = await service.get_collector(db, collector_id)
    app = await open_app_service.get_open_app(db, payload.app_id)
    if not app or not app.enabled or app.id not in collector.app_ids:
        raise service.CollectorError("请选择此接口已授权且启用的应用")
    if not collector.enabled:
        raise service.CollectorError("请先发布接口再调试")
    task = await service.submit(db, collector, app.id, payload)
    return await service.wait_result(
        db, task.execution_id, payload.wait_seconds, include_logs=True
    )


@tasks_router.get("", response_model=CollectorTaskPage)
async def list_admin_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    app_id: int | None = None,
    collector_id: int | None = None,
    status: Literal["pending", "running", "success", "failed"] | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await service.list_tasks(db, skip, limit, app_id, collector_id, status)


@tasks_router.get("/{execution_id}")
async def admin_task(execution_id: int, db: AsyncSession = Depends(get_db)):
    return await service.task_detail(db, execution_id, include_logs=True)


def data_response(result, field, skip, limit, format):
    data = service.result_rows(result, field, skip, limit)
    if format == "json":
        return data
    if result["status"] != "success":
        raise service.CollectorError("采集尚未成功，请先查询任务状态", 409)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=data["columns"])
    writer.writeheader()

    def cell(value):
        import json

        text = (
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else str(value if value is not None else "")
        )
        return (
            "'" + text
            if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
            else text
        )

    for row in data["items"]:
        writer.writerow({k: cell(v) for k, v in row.items()})
    return Response(
        "\ufeff" + stream.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="collection-{result["execution_id"]}.csv"'
        },
    )


@tasks_router.get("/{execution_id}/data")
async def admin_data(
    execution_id: int,
    field: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    format: Literal["json", "csv"] = "json",
    db: AsyncSession = Depends(get_db),
):
    return data_response(
        await service.task_detail(db, execution_id), field, skip, limit, format
    )


async def external_app(request: Request, db: AsyncSession = Depends(get_db)):
    app, error = await open_app_service.authenticate_request(db, request)
    app_id = app.id if app else None
    app_key = app.app_key if app else request.headers.get("X-App-Key", "")
    status, detail = 200, ""
    try:
        if not app:
            raise HTTPException(401, detail=error)
        yield app
    except Exception as exc:
        status = getattr(
            exc,
            "status",
            getattr(
                exc,
                "status_code",
                503 if isinstance(exc, QueueUnavailableError) else 400,
            ),
        )
        detail = str(getattr(exc, "detail", str(exc)))
        raise
    finally:
        await open_api_service.record_open_log(
            db,
            app_id=app_id,
            app_key=app_key,
            path=request.url.path,
            method=request.method,
            status_code=getattr(request.state, "response_status", status),
            success=status < 400,
            execution_id=getattr(request.state, "execution_id", None),
            request_ip=request.client.host if request.client else "",
            detail=detail,
        )


@public_router.get("/v1/collectors")
async def external_collectors(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    app=Depends(external_app),
    db: AsyncSession = Depends(get_db),
):
    page = await service.list_collectors(db, skip, limit, app.id)
    return {
        "items": [await service.contract(db, c) for c in page["items"]],
        "total": page["total"],
    }


@public_router.get("/v1/collectors/{slug}")
async def external_contract(
    slug: str, app=Depends(external_app), db: AsyncSession = Depends(get_db)
):
    return await service.contract(db, await service.by_slug(db, slug, app.id))


@public_router.post("/v1/collectors/{slug}/runs")
async def external_run(
    slug: str,
    payload: CollectorRun,
    request: Request,
    app=Depends(external_app),
    db: AsyncSession = Depends(get_db),
):
    collector = await service.by_slug(db, slug, app.id)
    task = await service.submit(
        db, collector, app.id, payload, request.headers.get("Idempotency-Key")
    )
    execution_id = task.execution_id
    request.state.execution_id = execution_id
    result = await service.wait_result(db, execution_id, payload.wait_seconds, app.id)
    status = 200 if result["finished"] else 202
    request.state.response_status = status
    return JSONResponse(
        jsonable_encoder(result),
        status_code=status,
        headers={
            "Location": result["result_url"],
            **({"Retry-After": "2"} if not result["finished"] else {}),
        },
    )


@public_router.get("/v1/tasks")
async def external_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    collector_id: int | None = None,
    status: Literal["pending", "running", "success", "failed"] | None = None,
    app=Depends(external_app),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_tasks(db, skip, limit, app.id, collector_id, status)


@public_router.get("/v1/tasks/{execution_id}")
async def external_task(
    execution_id: int,
    wait_seconds: int = Query(0, ge=0, le=20),
    app=Depends(external_app),
    db: AsyncSession = Depends(get_db),
):
    return await service.wait_result(db, execution_id, wait_seconds, app.id)


@public_router.get("/v1/tasks/{execution_id}/data")
async def external_data(
    execution_id: int,
    field: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    format: Literal["json", "csv"] = "json",
    app=Depends(external_app),
    db: AsyncSession = Depends(get_db),
):
    return data_response(
        await service.task_detail(db, execution_id, app.id), field, skip, limit, format
    )
