"""开放平台：签名认证、内置采集接口、调用日志。

全部通过 HTTP 走真实路由（TestClient），数据库为独立 SQLite 内存库
（monkeypatch app.database.AsyncSessionLocal），入队被 mock 捕获。
"""

import asyncio
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.database as app_database
import app.main as app_main
import app.services.script_run_service as script_run_service
from app.database import Base
from app.models.execution import Execution
from app.models.open_platform import OpenApiLog


# ---------- 工具 ----------


def make_sign(secret: str, method: str, path: str, timestamp: str, body: bytes) -> str:
    canonical = f"{method}\n{path}\n{timestamp}\n{hashlib.sha256(body).hexdigest()}"
    return hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def signed_request(
    client: TestClient,
    method: str,
    path: str,
    app_key: str,
    app_secret: str,
    body: dict | None = None,
    *,
    query: str = "",
    timestamp: str | None = None,
    sign: str | None = None,
):
    """签名只覆盖 path（不含 query）；query 单独拼到 URL"""
    raw = json.dumps(body).encode() if body is not None else b""
    ts = timestamp or str(int(time.time()))
    s = sign or make_sign(app_secret, method, path, ts, raw)
    headers = {"X-App-Key": app_key, "X-Timestamp": ts, "X-Sign": s}
    if body is not None:
        headers["Content-Type"] = "application/json"
    url = path + (f"?{query}" if query else "")
    return client.request(
        method, url, content=raw if body is not None else None, headers=headers
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client(monkeypatch):
    """TestClient：独立 SQLite 内存库 + 假队列（捕获入队调用）"""
    engine = create_async_engine("sqlite+aiosqlite://")
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _create_all():
        import app.models  # noqa: F401  # 注册模型

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run(_create_all())
    monkeypatch.setattr(app_database, "AsyncSessionLocal", maker)

    captured: list[tuple[int, object]] = []

    async def fake_enqueue(execution_id, headless_override=None):
        captured.append((execution_id, headless_override))

    monkeypatch.setattr(script_run_service, "enqueue_script_run", fake_enqueue)

    test_client = TestClient(app_main.app)
    test_client.captured = captured  # type: ignore[attr-defined]
    test_client.session_maker = maker  # type: ignore[attr-defined]
    yield test_client
    _run(engine.dispose())


def seed_via_api(client: TestClient) -> dict:
    """经管理端 API 造数：空间 + 采集脚本 + 开放应用，返回 {app_key, app_secret, script_id}"""
    ws = client.post("/api/workspaces", json={"name": "默认空间"}).json()
    script = client.post(
        "/api/scripts",
        json={
            "workspace_id": ws["id"],
            "name": "采集脚本",
            "code": "pass",
            "inputs": [
                {"name": "url", "type": "string", "required": True, "description": ""}
            ],
            "outputs": [],
        },
    ).json()
    app = client.post("/api/open-apps", json={"name": "外部系统"}).json()
    return {
        "app_key": app["app_key"],
        "app_secret": app["app_secret"],
        "script_id": script["id"],
        "app_id": app["id"],
    }


def _fetch_one(client: TestClient, model, conditions: tuple):
    async def _get():
        async with client.session_maker() as session:
            row = (
                (await session.execute(select(model).where(*conditions)))
                .scalars()
                .all()
            )
            return row

    return _run(_get())


# ---------- 签名认证 ----------


def test_missing_auth_headers_rejected(client):
    resp = client.post("/open/api/v1/collect/trigger", json={})
    assert resp.status_code == 401
    assert "缺少认证头" in resp.json()["detail"]


def test_expired_timestamp_rejected(client):
    creds = seed_via_api(client)
    old_ts = str(int(time.time()) - 3600)
    resp = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={"url": "https://x.com"},
        timestamp=old_ts,
    )
    assert resp.status_code == 401
    assert "过期" in resp.json()["detail"]


def test_bad_signature_rejected(client):
    creds = seed_via_api(client)
    resp = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={"url": "https://x.com"},
        sign="0" * 64,
    )
    assert resp.status_code == 401
    assert "签名校验失败" in resp.json()["detail"]


def test_disabled_app_rejected(client):
    creds = seed_via_api(client)
    client.put(f"/api/open-apps/{creds['app_id']}", json={"enabled": False})
    resp = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={"url": "https://x.com", "script_id": creds["script_id"]},
    )
    assert resp.status_code == 401
    assert "停用" in resp.json()["detail"]


def test_auth_failure_logged(client):
    client.post("/open/api/v1/collect/trigger", json={})
    logs = _fetch_one(client, OpenApiLog, ())
    assert len(logs) == 1
    assert logs[0].success is False
    assert logs[0].app_id is None
    assert logs[0].status_code == 401


# ---------- 采集触发 / 结果查询 ----------


def test_collect_trigger_enqueues_with_url(client):
    creds = seed_via_api(client)
    resp = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={"url": "https://example.com/post/1", "script_id": creds["script_id"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    eid = data["execution_id"]

    async def _check():
        async with client.session_maker() as session:
            execution = await session.get(Execution, eid)
            log = (
                await session.execute(
                    select(OpenApiLog).where(OpenApiLog.execution_id == eid)
                )
            ).scalar_one()
            return execution, log

    execution, log = _run(_check())
    assert execution.inputs["url"] == "https://example.com/post/1"
    assert client.captured == [(eid, None)]
    assert log.app_id == creds["app_id"] and log.success is True


def test_collect_trigger_extra_inputs_merged(client):
    creds = seed_via_api(client)
    resp = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={
            "url": "https://x.com",
            "script_id": creds["script_id"],
            "inputs": {"keyword": "测试", "url": "https://覆盖"},
        },
    )
    eid = resp.json()["execution_id"]

    async def _get():
        async with client.session_maker() as session:
            return (await session.get(Execution, eid)).inputs

    inputs = _run(_get())
    # 顶层 url 强制覆盖 inputs.url；其余透传
    assert inputs == {"keyword": "测试", "url": "https://x.com"}


def test_collect_trigger_validates_payload(client):
    creds = seed_via_api(client)
    resp = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={"script_id": creds["script_id"]},
    )
    assert resp.status_code == 400
    resp = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={"url": "https://x.com"},
    )
    assert resp.status_code == 400
    resp = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={"url": "https://x.com", "script_id": 999},
    )
    assert resp.status_code == 404


def test_collect_result_ownership(client):
    creds = seed_via_api(client)
    other = client.post("/api/open-apps", json={"name": "另一个应用"}).json()
    eid = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={"url": "https://x.com", "script_id": creds["script_id"]},
    ).json()["execution_id"]

    resp = signed_request(
        client,
        "GET",
        "/open/api/v1/collect/result",
        creds["app_key"],
        creds["app_secret"],
        query=f"execution_id={eid}",
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    resp = signed_request(
        client,
        "GET",
        "/open/api/v1/collect/result",
        other["app_key"],
        other["app_secret"],
        query=f"execution_id={eid}",
    )
    assert resp.status_code == 404


def test_collect_tasks_lists_owned(client):
    creds = seed_via_api(client)
    eid = signed_request(
        client,
        "POST",
        "/open/api/v1/collect/trigger",
        creds["app_key"],
        creds["app_secret"],
        body={"url": "https://x.com", "script_id": creds["script_id"]},
    ).json()["execution_id"]
    resp = signed_request(
        client,
        "GET",
        "/open/api/v1/collect/tasks",
        creds["app_key"],
        creds["app_secret"],
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [t["execution_id"] for t in items] == [eid]
    assert items[0]["script_id"] == creds["script_id"]


# ---------- 管理端 ----------


def test_admin_app_crud_masks_secret_in_list(client):
    detail = client.post("/api/open-apps", json={"name": "外部系统A"}).json()
    assert detail["app_key"].startswith("fk")
    assert len(detail["app_secret"]) == 48  # 创建响应返回 secret 便于立即保存

    listed = client.get("/api/open-apps").json()
    assert listed["total"] == 1
    assert "app_secret" not in listed["items"][0]  # 列表不回传 secret

    got = client.get(f"/api/open-apps/{detail['id']}").json()
    assert got["app_secret"] == detail["app_secret"]

    regen = client.post(f"/api/open-apps/{detail['id']}/regenerate-secret").json()
    assert regen["app_secret"] != detail["app_secret"]


def test_admin_logs_list_and_clear(client):
    seed_via_api(client)
    client.post("/open/api/v1/collect/trigger", json={})  # 认证失败留痕
    logs = client.get("/api/open-logs").json()
    assert logs["total"] == 1
    assert logs["items"][0]["success"] is False
    assert client.delete("/api/open-logs").status_code == 204
    assert client.get("/api/open-logs").json()["total"] == 0


def test_archived_proxy_rules_never_forward_requests(client):
    from sqlalchemy import text

    creds = seed_via_api(client)

    async def seed_archived_rule():
        async with client.session_maker() as db:
            await db.execute(
                text(
                    "CREATE TABLE open_apis (id INTEGER PRIMARY KEY, method TEXT, path TEXT, target_path TEXT, enabled BOOLEAN)"
                )
            )
            await db.execute(
                text(
                    "INSERT INTO open_apis VALUES (1, 'GET', '/v1/legacy-app', '/api/open-apps/1', 1)"
                )
            )
            await db.commit()

    _run(seed_archived_rule())
    for method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
        response = signed_request(
            client, method, "/open/v1/legacy-app", creds["app_key"], creds["app_secret"]
        )
        assert response.status_code == 404
    for method in ("GET", "POST", "PUT", "DELETE"):
        assert client.request(method, "/api/open-apis").status_code == 404
    assert "open_apis" not in Base.metadata.tables

    async def count_archived_rules():
        async with client.session_maker() as db:
            return await db.scalar(text("SELECT COUNT(*) FROM open_apis"))

    assert _run(count_archived_rules()) == 1
