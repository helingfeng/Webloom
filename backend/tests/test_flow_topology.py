"""流程拓扑：分层排序、环检测、层内并行与输出传递"""

import asyncio
from types import SimpleNamespace

import pytest

from app.services import data_view_service, flow_service, global_variable_service


def _node(node_id: str, script_id: int, input_mapping: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": "script",
        "data": {"script_id": script_id, "input_mapping": input_mapping or {}},
    }


def test_topological_layers_respects_dependencies():
    nodes = [_node("a", 1), _node("b", 2), _node("c", 3)]
    edges = [
        {"source": "a", "target": "c"},
        {"source": "b", "target": "c"},
    ]
    layers = flow_service._topological_layers(nodes, edges)
    assert layers == [["a", "b"], ["c"]]


def test_topological_layers_independent_nodes_same_layer():
    nodes = [_node("a", 1), _node("b", 2), _node("c", 3)]
    layers = flow_service._topological_layers(nodes, [])
    assert layers == [["a", "b", "c"]]


def test_topological_layers_detects_cycle_raises():
    nodes = [_node("a", 1), _node("b", 2)]
    edges = [
        {"source": "a", "target": "b"},
        {"source": "b", "target": "a"},
    ]
    with pytest.raises(ValueError, match="环依赖"):
        flow_service._topological_layers(nodes, edges)


async def test_parallel_layers_outputs_feed_next_layer(monkeypatch):
    """无依赖节点并行执行；下一层节点可引用上一层节点输出"""
    nodes = [_node("a", 1), _node("b", 2), _node("c", 3, {"q": "{{node_a.out}}"})]
    edges = [
        {"source": "a", "target": "c"},
        {"source": "b", "target": "c"},
    ]
    scripts = {
        1: SimpleNamespace(
            id=1, name="s1", inputs=[], inherit_global=False, start_url="", code=""
        ),
        2: SimpleNamespace(
            id=2, name="s2", inputs=[], inherit_global=False, start_url="", code=""
        ),
        3: SimpleNamespace(
            id=3,
            name="s3",
            inputs=[{"name": "q"}],
            inherit_global=False,
            start_url="",
            code="",
        ),
    }

    concurrent = 0
    max_concurrent = 0
    received: dict[int, dict] = {}

    async def fake_execute(script, inputs, execution_id, log_callback, **kwargs):
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        await asyncio.sleep(0.02)
        received[script.id] = dict(inputs)
        concurrent -= 1
        return "", {"out": f"OUT{script.id}"}

    async def fake_globals(db, start_url):
        return {}, {}, {}, []

    async def fake_views(db):
        return {}

    async def fake_get_script(db, sid):
        return scripts[sid]

    monkeypatch.setattr(flow_service, "execute_script_code", fake_execute)
    monkeypatch.setattr(flow_service, "get_script", fake_get_script)
    monkeypatch.setattr(
        global_variable_service, "get_active_globals_grouped", fake_globals
    )
    monkeypatch.setattr(data_view_service, "collect_view_data_cached", fake_views)

    context = await flow_service._run_flow_nodes(
        None, nodes, edges, "manual", {}, 999, lambda msg: None
    )

    # a/b 同层并行（峰值并发 ≥ 2），c 在其后
    assert max_concurrent >= 2
    # c 的输入来自 a 的输出（节点输出按 node_id 组织）
    assert received[3] == {"q": "OUT1"}
    assert context["nodes"]["a"] == {"out": "OUT1"}
    assert context["nodes"]["b"] == {"out": "OUT2"}
    assert context["nodes"]["c"] == {"out": "OUT3"}


def _async(value):
    async def _get(*args, **kwargs):
        return value

    return _get
