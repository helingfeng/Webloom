import asyncio
from collections import deque
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.flow import Flow
from app.models.execution import Execution
from app.schemas.flow import FlowCreate, FlowUpdate
from app.services.script_service import get_script
from app.services import global_variable_service, data_view_service, workspace_service
from app.engine.runner import execute_script_code
from app.engine.mock_generator import generate_mock_inputs
from app.websocket import manager


async def get_flows(
    db: AsyncSession, skip: int = 0, limit: int = 100, workspace_id: int | None = None
) -> list[Flow]:
    stmt = select(Flow)
    if workspace_id is not None:
        stmt = stmt.where(Flow.workspace_id == workspace_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return result.scalars().all()


async def get_flow(db: AsyncSession, flow_id: int) -> Flow | None:
    result = await db.execute(select(Flow).where(Flow.id == flow_id))
    return result.scalar_one_or_none()


async def _validate_workspace(db: AsyncSession, workspace_id: int) -> None:
    ws = await workspace_service.get_workspace(db, workspace_id)
    if not ws:
        raise ValueError(f"项目空间 {workspace_id} 不存在")


def _validated_dump(flow_in: FlowCreate | FlowUpdate) -> dict:
    data = flow_in.model_dump()
    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError("流程名称不能为空")
    data["name"] = name
    return data


async def create_flow(db: AsyncSession, flow_in: FlowCreate) -> Flow:
    await _validate_workspace(db, flow_in.workspace_id)
    data = _validated_dump(flow_in)
    flow = Flow(**data)
    db.add(flow)
    await db.commit()
    await db.refresh(flow)
    return flow


async def update_flow(db: AsyncSession, flow: Flow, flow_in: FlowUpdate) -> Flow:
    if flow_in.workspace_id != flow.workspace_id:
        await _validate_workspace(db, flow_in.workspace_id)
    data = _validated_dump(flow_in)
    for key, value in data.items():
        setattr(flow, key, value)
    await db.commit()
    await db.refresh(flow)
    return flow


async def delete_flow(db: AsyncSession, flow: Flow) -> None:
    await db.delete(flow)
    await db.commit()


async def run_flow(
    db: AsyncSession,
    flow: Flow,
    mode: str = "manual",
    global_inputs: dict | None = None,
) -> Execution:
    global_inputs = global_inputs or {}

    execution = Execution(
        target_type="flow",
        target_id=flow.id,
        mode=mode,
        inputs=global_inputs,
        status="running",
        logs="",
        outputs={},
        started_at=datetime.now(),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    await execute_flow(db, flow, mode, global_inputs, execution.id)
    return execution


async def execute_flow(
    db: AsyncSession,
    flow: Flow,
    mode: str,
    global_inputs: dict,
    execution_id: int,
    log_callback=None,
) -> None:
    nodes = flow.nodes or []
    edges = flow.edges or []

    if log_callback is None:

        def log_callback(msg: str):
            asyncio.create_task(manager.send_log(execution_id, msg))

    execution = await db.get(Execution, execution_id)
    if not execution:
        raise ValueError(f"Execution {execution_id} not found")

    try:
        context = await _run_flow_nodes(
            db, nodes, edges, mode, global_inputs, execution_id, log_callback
        )
        execution.status = "success"
        execution.outputs = context
        execution.logs = "Flow executed successfully"
    except Exception as exc:
        execution.status = "failed"
        detail_logs = getattr(exc, "logs", "") or ""
        error_msg = f"Error: {exc}"
        execution.logs = (
            f"{detail_logs}\n{error_msg}".strip() if detail_logs else error_msg
        )
        execution.outputs = {}
        log_callback(f"{error_msg}\n")
    finally:
        execution.finished_at = datetime.now()
        await db.commit()
        await db.refresh(execution)


async def _run_flow_nodes(
    db: AsyncSession,
    nodes: list[dict],
    edges: list[dict],
    mode: str,
    global_inputs: dict,
    execution_id: int,
    log_callback,
) -> dict:
    script_nodes = [n for n in nodes if n.get("type") == "script"]
    ordered_node_ids = _topological_sort(nodes, edges)

    context = {"global": global_inputs, "nodes": {}}

    # 按域名缓存已加载的全局变量（不同脚本节点起始域名可能不同）
    global_cache: dict[str, tuple[dict, dict, dict, list]] = {}

    async def _load_globals(start_url: str) -> tuple[dict, dict, dict, list]:
        key = start_url or ""
        if key not in global_cache:
            global_cache[key] = (
                await global_variable_service.get_active_headers(db, key),
                await global_variable_service.get_active_vars(db, key),
                await global_variable_service.get_active_local_storage(db, key),
                await global_variable_service.get_active_cookies(db, key),
            )
        return global_cache[key]

    for node_id in ordered_node_ids:
        node = next((n for n in script_nodes if n["id"] == node_id), None)
        if not node:
            continue

        script_id = node.get("data", {}).get("script_id")
        if not script_id:
            continue

        script = await get_script(db, script_id)
        if not script:
            raise ValueError(f"Script {script_id} not found")

        if script.inherit_global:
            headers, gvars, local_storage, cookies = await _load_globals(script.start_url or "")
        else:
            headers, gvars, local_storage, cookies = {}, {}, {}, []

        input_mapping = node.get("data", {}).get("input_mapping", {})
        inputs = _resolve_inputs(script.inputs, input_mapping, context, mode)

        # 数据视图按次执行预取一次（所有节点共享同份数据）
        if "data_views" not in context:
            context["data_views"] = await data_view_service.collect_view_data(db)

        log_callback(f"[node {node_id}] Running script {script.name}\n")
        logs, outputs = await execute_script_code(
            script,
            inputs,
            execution_id,
            log_callback,
            global_headers=headers,
            global_vars=gvars,
            global_local_storage=local_storage,
            global_cookies=cookies,
            data_views=context["data_views"],
        )
        log_callback(f"[node {node_id}] Done\n")

        context["nodes"][node_id] = outputs or {}

    return context


def _topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    node_ids = {n["id"] for n in nodes}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    in_degree: dict[str, int] = {node_id: 0 for node_id in node_ids}

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source in node_ids and target in node_ids:
            adjacency[source].append(target)
            in_degree[target] += 1

    queue = deque([node_id for node_id in node_ids if in_degree[node_id] == 0])
    result: list[str] = []

    while queue:
        current = queue.popleft()
        result.append(current)
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result


def _resolve_inputs(
    script_inputs: list[dict],
    input_mapping: dict,
    context: dict,
    mode: str,
) -> dict:
    result: dict = {}
    for variable in script_inputs:
        name = variable.get("name")
        mapping = input_mapping.get(name)
        if mapping:
            result[name] = _resolve_value(mapping, context)
        elif mode == "mock":
            result[name] = generate_mock_inputs([variable]).get(name)
        else:
            result[name] = variable.get("default")
    return result


def _resolve_value(mapping: str, context: dict) -> any:
    mapping = mapping.strip()
    if mapping.startswith("{{") and mapping.endswith("}}"):
        path = mapping[2:-2].strip()
        return _get_context_value(path, context)
    return mapping


def _get_context_value(path: str, context: dict) -> any:
    if path.startswith("global."):
        key = path[7:]
        return context.get("global", {}).get(key)

    if path.startswith("node_"):
        rest = path[5:]
        dot_index = rest.find(".")
        if dot_index == -1:
            return None
        node_id = rest[:dot_index]
        output_key = rest[dot_index + 1 :]
        return context.get("nodes", {}).get(node_id, {}).get(output_key)

    return context.get("global", {}).get(path)
