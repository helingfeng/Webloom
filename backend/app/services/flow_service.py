import asyncio
from collections import deque
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.models.flow import Flow
from app.models.execution import Execution
from app.schemas.flow import FlowCreate, FlowUpdate
from app.services.script_service import get_script
from app.services import global_variable_service, data_view_service, workspace_service
from app.engine.runner import cleanup_execution_temp_files, execute_script_code
from app.engine.mock_generator import generate_mock_inputs
from app.services.log_bus import ExecutionLogBus
from app.task_queue import QueueUnavailableError, enqueue_flow_run

# 流程内同时执行的节点上限（每节点一个 Chromium 实例；全局并发由 worker max_jobs 兜底）
FLOW_NODE_CONCURRENCY = 3


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


async def start_flow_execution(
    db: AsyncSession,
    flow: Flow,
    *,
    mode: str = "manual",
    global_inputs: dict | None = None,
) -> Execution:
    """创建 pending 状态 Execution 并入队，立即返回（worker 调度执行）。

    队列不可用（Redis 未启动）时抛 QueueUnavailableError，该执行留痕为 failed。
    """
    execution = Execution(
        target_type="flow",
        target_id=flow.id,
        mode=mode,
        inputs=global_inputs or {},
        status="pending",
        logs="",
        outputs={},
        started_at=datetime.now(),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    try:
        await enqueue_flow_run(execution.id)
    except QueueUnavailableError:
        execution.status = "failed"
        execution.logs = "Error: 执行队列不可用，请确认 Redis 与执行 worker 已启动\n"
        execution.finished_at = datetime.now()
        await db.commit()
        raise
    return execution


async def run_flow_execution(execution_id: int) -> dict:
    """worker job：执行流程并回写终态。幂等：非 pending 状态直接返回。"""
    async with AsyncSessionLocal() as session:
        execution = await session.get(Execution, execution_id)
        if execution is None or execution.status != "pending":
            return {"status": execution.status if execution else "missing"}

        flow = await get_flow(session, execution.target_id)

        bus = ExecutionLogBus(execution_id)
        await bus.start()

        def log_callback(msg: str):
            bus.append(msg)

        try:
            execution.status = "running"
            execution.started_at = datetime.now()
            await session.commit()

            if flow is None:
                raise ValueError(f"流程 {execution.target_id} 不存在（可能已被删除）")

            await execute_flow(
                session,
                flow,
                execution.mode,
                execution.inputs or {},
                execution_id,
                log_callback,
            )
        except asyncio.CancelledError:
            # worker 超时/关闭取消：落终态 failed，而不是留 running 僵尸记录
            bus.append("Error: 流程执行被取消（worker 超时或关闭）\n")
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


async def execute_flow(
    db: AsyncSession,
    flow: Flow,
    mode: str,
    global_inputs: dict,
    execution_id: int,
    log_callback=None,
) -> None:
    """执行流程节点（供 worker job 调用）；终态回写由调用方统一处理日志与状态。"""
    nodes = flow.nodes or []
    edges = flow.edges or []

    if log_callback is None:

        def log_callback(msg: str):
            pass

    execution = await db.get(Execution, execution_id)
    if not execution:
        raise ValueError(f"Execution {execution_id} not found")

    try:
        context = await _run_flow_nodes(
            db, nodes, edges, mode, global_inputs, execution_id, log_callback
        )
        execution.status = "success"
        execution.outputs = context
        # 节点日志已由 LogBus 增量落库，不再整体覆写 logs
    except Exception as exc:
        execution.status = "failed"
        execution.outputs = {}
        log_callback(f"Error: {exc}\n")
    finally:
        execution.finished_at = datetime.now()
        await db.commit()


async def _run_flow_nodes(
    db: AsyncSession,
    nodes: list[dict],
    edges: list[dict],
    mode: str,
    global_inputs: dict,
    execution_id: int,
    log_callback,
) -> dict:
    script_nodes = {n["id"]: n for n in nodes if n.get("type") == "script"}
    layers = _topological_layers(nodes, edges)

    context = {"global": global_inputs, "nodes": {}}

    # 按域名缓存已加载的全局变量（不同脚本节点起始域名可能不同）
    global_cache: dict[str, tuple[dict, dict, dict, list]] = {}

    async def _load_globals(start_url: str) -> tuple[dict, dict, dict, list]:
        key = start_url or ""
        if key not in global_cache:
            global_cache[key] = await global_variable_service.get_active_globals_grouped(
                db, key
            )
        return global_cache[key]

    # 数据视图整次执行预取一次（所有节点共享同份数据，带 TTL 缓存去重并发执行）
    data_views: dict = {}
    if script_nodes:
        data_views = await data_view_service.collect_view_data_cached(db)
    context["data_views"] = data_views

    sem = asyncio.Semaphore(FLOW_NODE_CONCURRENCY)

    for layer in layers:
        # 先串行完成每节点的会话操作（查脚本/全局变量/解析输入），
        # 再并行执行子进程部分（AsyncSession 不允许并发使用）
        tasks = []
        for node_id in layer:
            node = script_nodes.get(node_id)
            if not node:
                continue
            script_id = node.get("data", {}).get("script_id")
            if not script_id:
                continue

            script = await get_script(db, script_id)
            if not script:
                raise ValueError(f"Script {script_id} not found")

            if script.inherit_global:
                headers, gvars, local_storage, cookies = await _load_globals(
                    script.start_url or ""
                )
            else:
                headers, gvars, local_storage, cookies = {}, {}, {}, []

            input_mapping = node.get("data", {}).get("input_mapping", {})
            inputs = _resolve_inputs(script.inputs, input_mapping, context, mode)

            async def _run_node(
                script=script,
                inputs=inputs,
                headers=headers,
                gvars=gvars,
                local_storage=local_storage,
                cookies=cookies,
                node_id=node_id,
            ):
                def node_log(msg: str):
                    log_callback(f"[node {node_id}] {msg}")

                node_log(f"Running script {script.name}\n")
                async with sem:
                    _, outputs = await execute_script_code(
                        script,
                        inputs,
                        execution_id,
                        node_log,
                        global_headers=headers,
                        global_vars=gvars,
                        global_local_storage=local_storage,
                        global_cookies=cookies,
                        data_views=data_views,
                    )
                node_log("Done\n")
                context["nodes"][node_id] = outputs or {}

            tasks.append(_run_node())

        if tasks:
            # return_exceptions：避免取消同层兄弟节点导致 chromium 子进程变孤儿
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    raise r

    return context


def _topological_layers(nodes: list[dict], edges: list[dict]) -> list[list[str]]:
    """Kahn 分层拓扑排序：同层节点无依赖可并行；存在环时抛 ValueError（不再静默跳过）"""
    node_ids = {n["id"] for n in nodes}
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    in_degree: dict[str, int] = {node_id: 0 for node_id in node_ids}

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source in node_ids and target in node_ids:
            adjacency[source].append(target)
            in_degree[target] += 1

    queue = deque(sorted(node_id for node_id in node_ids if in_degree[node_id] == 0))
    layers: list[list[str]] = []
    visited = 0

    while queue:
        layer = sorted(queue)
        queue = deque()
        visited += len(layer)
        layers.append(layer)
        for current in layer:
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

    if visited < len(node_ids):
        cyclic = sorted(node_id for node_id in node_ids if in_degree[node_id] > 0)
        raise ValueError(f"流程存在环依赖，无法执行，涉及节点: {', '.join(cyclic)}")
    return layers


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
