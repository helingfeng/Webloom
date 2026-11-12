"""采集接口发布、授权、幂等提交、任务查询及结果数据。"""

import asyncio
import hashlib
import json
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only
from app.models.collector import Collector, CollectorTask
from app.models.execution import Execution
from app.models.open_platform import OpenApp
from app.schemas.collector import CollectorCreate, CollectorRun
from app.services import script_service
from app.services.script_run_service import start_script_execution
from app.engine.runner import validate_script_code, _extract_error_line
from app.engine.parameters import resolve_inputs, normalize_definitions


class CollectorError(ValueError):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.status = status


async def get_collector(db, collector_id):
    item = await db.get(Collector, collector_id)
    if not item or item.archived:
        raise CollectorError("采集接口不存在或已移除", 404)
    return item


async def save_collector(
    db: AsyncSession, payload: CollectorCreate, collector_id: int | None = None
):
    script = await script_service.get_script(db, payload.script_id)
    if not script:
        raise CollectorError("请选择存在的采集脚本")
    validate_script_code(script.code)
    ids = sorted(set(payload.app_ids))
    found = (
        (await db.execute(select(OpenApp.id).where(OpenApp.id.in_(ids))))
        .scalars()
        .all()
    )
    if len(found) != len(ids):
        raise CollectorError("授权应用不存在，请刷新应用列表")
    item = await get_collector(db, collector_id) if collector_id else Collector()
    data = payload.model_dump()
    data["name"] = data["name"].strip()
    if not data["name"]:
        raise CollectorError("接口名称不能为空")
    data["app_ids"] = ids
    if collector_id and payload.slug != item.slug:
        raise CollectorError("接口标识发布后不可修改，请新建接口以免已有调用失效")
    for k, v in data.items():
        setattr(item, k, v)
    db.add(item)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise CollectorError(
            "接口标识已被使用（含已移除接口），请使用新标识", 409
        ) from exc
    await db.refresh(item)
    return item


async def remove_collector(db: AsyncSession, collector_id: int) -> None:
    """移除发布入口，保留接口记录以维持历史任务的归属和结果查询。"""
    item = await db.get(Collector, collector_id)
    if not item:
        raise CollectorError("采集接口不存在", 404)
    item.archived = True
    item.enabled = False
    await db.commit()


async def list_collectors(db, skip=0, limit=20, app_id=None):
    items = (
        (
            await db.execute(
                select(Collector)
                .where(Collector.archived.is_(False))
                .order_by(Collector.id.desc())
            )
        )
        .scalars()
        .all()
    )
    if app_id is not None:
        items = [c for c in items if c.enabled and app_id in c.app_ids]
    return {"items": items[skip : skip + limit], "total": len(items)}


async def by_slug(db, slug, app_id):
    item = (
        await db.execute(select(Collector).where(Collector.slug == slug))
    ).scalar_one_or_none()
    if not item or item.archived or not item.enabled or app_id not in item.app_ids:
        raise CollectorError("接口不存在、未发布或未授权给此应用", 404)
    return item


def input_schema(definitions):
    types = {"number": "number", "boolean": "boolean"}
    properties, required = {}, []
    for item in definitions or []:
        prop = {
            "type": types.get(item["type"], "string"),
            "description": item.get("description", ""),
        }
        if item.get("default") is not None and item["type"] not in (
            "secret",
            "cookie",
            "header",
            "localStorage",
        ):
            prop["default"] = item["default"]
        if item["type"] in ("secret", "cookie", "header", "localStorage"):
            prop["writeOnly"] = True
        properties[item["name"]] = prop
        if item.get("required", True) and item.get("default") is None:
            required.append(item["name"])
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


async def contract(db, collector):
    script = await script_service.get_script(db, collector.script_id)
    if not script:
        raise CollectorError("关联脚本已删除，请联系接口发布者", 409)
    schema = input_schema(normalize_definitions(script.inputs or []))
    example = {
        k: v.get(
            "default",
            (
                False
                if v["type"] == "boolean"
                else (
                    10
                    if v["type"] == "number"
                    else "https://example.com" if k == "url" else ""
                )
            ),
        )
        for k, v in schema["properties"].items()
        if not v.get("writeOnly")
    }
    return {
        "id": collector.id,
        "name": collector.name,
        "slug": collector.slug,
        "description": collector.description,
        "method": "POST",
        "path": f"/open/v1/collectors/{collector.slug}/runs",
        "input_schema": schema,
        "outputs": script.outputs or [],
        "example": {"inputs": example, "wait_seconds": 0},
        "auth": "Authorization: Bearer <App Key>.<App Secret>",
    }


def validate_inputs(script, inputs):
    try:
        return resolve_inputs(script.inputs or [], inputs)
    except ValueError as exc:
        raise CollectorError(str(exc)) from exc


async def submit(db, collector, app_id, payload: CollectorRun, request_key=None):
    request_key = request_key.strip() if request_key else None
    if request_key and len(request_key) > 128:
        raise CollectorError("Idempotency-Key 最长 128 字符")
    digest = hashlib.sha256(
        json.dumps(
            {"collector": collector.id, "inputs": payload.inputs},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()

    async def existing():
        if not request_key:
            return None
        task = (
            await db.execute(
                select(CollectorTask).where(
                    CollectorTask.app_id == app_id,
                    CollectorTask.request_key == request_key,
                )
            )
        ).scalar_one_or_none()
        if task and task.request_hash != digest:
            raise CollectorError("相同 Idempotency-Key 已用于不同请求，请使用新键", 409)
        return task

    task = await existing()
    if task:
        return task
    script = await script_service.get_script(db, collector.script_id)
    if not script:
        raise CollectorError("关联脚本已删除", 409)
    validate_inputs(script, payload.inputs)
    task = CollectorTask(
        collector_id=collector.id,
        app_id=app_id,
        request_key=request_key,
        request_hash=digest,
    )

    def attach(execution):
        task.execution_id = execution.id
        db.add(task)

    try:
        await start_script_execution(
            db,
            script,
            mode="manual",
            inputs=payload.inputs,
            headless=True,
            on_created=attach,
        )
    except IntegrityError:
        await db.rollback()
        task = await existing()
        if task:
            return task
        raise
    return task


def task_summary(task, execution, collector):
    return {
        "task_id": execution.id,
        "execution_id": execution.id,
        "collector_id": collector.id,
        "collector_name": collector.name,
        "app_id": task.app_id,
        "status": execution.status,
        "finished": execution.status in ("success", "failed"),
        "error": (
            (
                _extract_error_line(execution.logs or "")
                or "采集失败，请联系接口发布者查看执行日志"
            )
            if execution.status == "failed"
            else None
        ),
        "created_at": task.created_at,
        "finished_at": execution.finished_at,
        "result_url": f"/open/v1/tasks/{execution.id}",
        "data_url": f"/open/v1/tasks/{execution.id}/data",
    }


async def task_detail(
    db, execution_id, app_id=None, include_outputs=True, include_logs=False
):
    stmt = (
        select(CollectorTask, Execution, Collector)
        .join(Execution, Execution.id == CollectorTask.execution_id)
        .join(Collector, Collector.id == CollectorTask.collector_id)
        .where(Execution.id == execution_id)
    )
    if app_id is not None:
        stmt = stmt.where(CollectorTask.app_id == app_id)
    row = (await db.execute(stmt.execution_options(populate_existing=True))).first()
    if not row:
        raise CollectorError("任务不存在或无权查看", 404)
    task, execution, collector = row
    result = task_summary(task, execution, collector)
    if include_outputs:
        result["outputs"] = execution.outputs or {}
    if include_logs:
        result["logs"] = (execution.logs or "")[-20000:]
        script = await script_service.get_script(db, collector.script_id)
        definitions = (
            execution.script_snapshot.get("inputs", [])
            if execution.script_snapshot
            else (script.inputs if script else [])
        )
        hidden = {
            d["name"]
            for d in definitions
            if d.get("type") in ("secret", "cookie", "header", "localStorage")
        }
        result["inputs"] = {
            k: "******" if k in hidden else v
            for k, v in (execution.inputs or {}).items()
        }
    return result


async def wait_result(db, execution_id, seconds, app_id=None, include_logs=False):
    deadline = asyncio.get_running_loop().time() + seconds
    while True:
        result = await task_detail(db, execution_id, app_id, include_logs=include_logs)
        if result["finished"] or asyncio.get_running_loop().time() >= deadline:
            return result
        # 释放事务快照，否则 MySQL REPEATABLE READ 会看不到 worker 的更新。
        await db.commit()
        await asyncio.sleep(0.5)


async def list_tasks(db, skip=0, limit=20, app_id=None, collector_id=None, status=None):
    stmt = select(CollectorTask.execution_id).join(
        Execution, Execution.id == CollectorTask.execution_id
    )
    if app_id is not None:
        stmt = stmt.where(CollectorTask.app_id == app_id)
    if collector_id is not None:
        stmt = stmt.where(CollectorTask.collector_id == collector_id)
    if status:
        stmt = stmt.where(Execution.status == status)
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await db.execute(
            select(CollectorTask, Execution, Collector)
            .join(Execution, Execution.id == CollectorTask.execution_id)
            .join(Collector, Collector.id == CollectorTask.collector_id)
            .where(CollectorTask.execution_id.in_(stmt))
            .options(
                load_only(
                    Execution.id,
                    Execution.status,
                    Execution.logs,
                    Execution.finished_at,
                )
            )
            .order_by(CollectorTask.id.desc())
            .offset(skip)
            .limit(limit)
        )
    ).all()
    return {"items": [task_summary(*row) for row in rows], "total": total}


def result_rows(result, field=None, skip=0, limit=100):
    outputs = result.get("outputs", {})
    fields = list(outputs)
    if field is None:
        field = next(
            (key for key, value in outputs.items() if isinstance(value, list)),
            next(iter(outputs), None),
        )
    if field and field not in outputs:
        raise CollectorError("输出字段不存在，可选字段: " + ", ".join(fields))
    value = outputs.get(field) if field else []
    values = value if isinstance(value, list) else [value]
    rows = [
        v if isinstance(v, dict) else {"value": v} for v in values[skip : skip + limit]
    ]
    columns = list(dict.fromkeys(k for row in rows for k in row))
    return {
        "status": result["status"],
        "finished": result["finished"],
        "error": result["error"],
        "field": field,
        "fields": fields,
        "items": rows,
        "columns": columns,
        "total": len(values),
        "skip": skip,
        "limit": limit,
    }
