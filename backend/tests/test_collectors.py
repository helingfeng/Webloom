"""采集接口发布与外部调用闭环（真实 HTTP 路由，独立 SQLite，假队列）。"""

from datetime import datetime
from test_open_platform import client, seed_via_api, signed_request, _run
from app.models.execution import Execution


def publish(client):
    creds = seed_via_api(client)
    response = client.post(
        "/api/collectors",
        json={
            "name": "商品采集",
            "slug": "products",
            "script_id": creds["script_id"],
            "app_ids": [creds["app_id"]],
        },
    )
    assert response.status_code == 201, response.text
    return creds, response.json()


def auth(creds):
    return {"Authorization": f"Bearer {creds['app_key']}.{creds['app_secret']}"}


def run(client, creds, key=None, inputs=None):
    headers = auth(creds)
    if key:
        headers["Idempotency-Key"] = key
    return client.post(
        "/open/v1/collectors/products/runs",
        headers=headers,
        json={
            "inputs": inputs if inputs is not None else {"url": "https://example.com"}
        },
    )


def finish(client, eid, status="success", outputs=None):
    async def update():
        async with client.session_maker() as db:
            e = await db.get(Execution, eid)
            e.status = status
            e.finished_at = datetime.now()
            e.outputs = (
                outputs
                if outputs is not None
                else {"items": [{"name": "A"}, {"name": "B"}]}
            )
            e.logs = "ValueError: invalid target\n" if status == "failed" else "done\n"
            await db.commit()

    _run(update())


def test_catalog_auth_and_signature(client):
    creds, c = publish(client)
    response = client.get("/open/v1/collectors", headers=auth(creds))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["input_schema"]["required"] == ["url"]
    assert "code" not in data["items"][0]
    assert client.get("/open/v1/collectors").status_code == 401
    assert (
        client.get(
            "/open/v1/collectors", headers={"Authorization": "Bearer invalid"}
        ).status_code
        == 401
    )
    signed = signed_request(
        client, "GET", "/open/v1/collectors", creds["app_key"], creds["app_secret"]
    )
    assert signed.status_code == 200
    client.post(f"/api/open-apps/{creds['app_id']}/regenerate-secret")
    assert client.get("/open/v1/collectors", headers=auth(creds)).status_code == 401


def test_durable_ownership_and_idempotency(client):
    creds, _ = publish(client)
    first = run(client, creds, "key")
    assert first.status_code == 202, first.text
    eid = first.json()["execution_id"]
    assert first.headers["retry-after"] == "2"
    assert run(client, creds, "key").json()["execution_id"] == eid
    assert len(client.captured) == 1
    assert run(client, creds, "key", {"url": "different"}).status_code == 409
    client.delete("/api/open-logs")
    assert client.get(f"/open/v1/tasks/{eid}", headers=auth(creds)).status_code == 200
    assert client.get("/api/collector-tasks").json()["total"] == 1


def test_authorization_and_disabled_apps(client):
    creds, _ = publish(client)
    other = client.post("/api/open-apps", json={"name": "other"}).json()
    assert client.get("/open/v1/collectors", headers=auth(other)).json()["total"] == 0
    assert run(client, other).status_code == 404
    eid = run(client, creds).json()["execution_id"]
    assert client.get(f"/open/v1/tasks/{eid}", headers=auth(other)).status_code == 404
    assert (
        client.get(f"/open/v1/tasks/{eid}/data", headers=auth(other)).status_code == 404
    )
    assert client.get("/open/v1/tasks", headers=auth(other)).json()["total"] == 0
    client.put(f"/api/open-apps/{creds['app_id']}", json={"enabled": False})
    assert client.get(f"/open/v1/tasks/{eid}", headers=auth(creds)).status_code == 401


def test_validation_and_unpublish(client):
    creds, c = publish(client)
    data = {
        k: c[k]
        for k in ("name", "slug", "script_id", "description", "app_ids", "enabled")
    }
    assert client.post("/api/collectors", json=data).status_code == 409
    assert (
        client.put(
            f"/api/collectors/{c['id']}", json={**data, "slug": "changed"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/collectors", json={**data, "slug": "bad-app", "app_ids": [9999]}
        ).status_code
        == 400
    )
    for inputs in ({}, {"url": 123}, {"url": "x", "extra": 1}):
        assert run(client, creds, inputs=inputs).status_code == 400
    assert not client.captured
    client.put(f"/api/collectors/{c['id']}", json={**data, "enabled": False})
    assert run(client, creds).status_code == 404


def test_data_pages_csv_and_failure(client):
    creds, _ = publish(client)
    eid = run(client, creds).json()["execution_id"]
    finish(client, eid)
    detail = client.get(f"/open/v1/tasks/{eid}", headers=auth(creds)).json()
    assert detail["finished"] and detail["status"] == "success"
    assert "logs" not in detail and "inputs" not in detail
    data = client.get(
        f"/open/v1/tasks/{eid}/data?skip=1&limit=1", headers=auth(creds)
    ).json()
    assert data["total"] == 2 and data["items"] == [{"name": "B"}]
    assert (
        client.get(
            f"/open/v1/tasks/{eid}/data?field=missing", headers=auth(creds)
        ).status_code
        == 400
    )
    csv = client.get(f"/open/v1/tasks/{eid}/data?format=csv", headers=auth(creds))
    assert "name" in csv.text and "attachment" in csv.headers["content-disposition"]
    page = client.get("/api/collector-tasks?status=success&limit=1").json()
    assert page["total"] == 1 and "outputs" not in page["items"][0]
    assert client.get(f"/api/collector-tasks/{eid}").json()["logs"] == "done\n"
    finish(client, eid, "failed")
    assert (
        client.get(f"/open/v1/tasks/{eid}", headers=auth(creds)).json()["error"]
        == "ValueError: invalid target"
    )
    finish(client, eid, outputs={"items": [{"value": "=1+1"}]})
    assert (
        "'=1+1"
        in client.get(f"/open/v1/tasks/{eid}/data?format=csv", headers=auth(creds)).text
    )


def test_failed_enqueue_is_visible(client, monkeypatch):
    from app.services import script_run_service
    from app.task_queue import QueueUnavailableError

    creds, _ = publish(client)

    async def unavailable(*args, **kwargs):
        raise QueueUnavailableError("offline")

    monkeypatch.setattr(script_run_service, "enqueue_script_run", unavailable)
    response = run(client, creds, "failed")
    assert response.status_code == 503, response.text
    tasks = client.get("/open/v1/tasks", headers=auth(creds)).json()
    assert tasks["total"] == 1 and tasks["items"][0]["status"] == "failed"
    assert run(client, creds, "failed").json()["status"] == "failed"


def test_debug_uses_persistent_tasks(client):
    creds, c = publish(client)
    response = client.post(
        f"/api/collectors/{c['id']}/debug",
        json={"app_id": creds["app_id"], "inputs": {"url": "https://example.com"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    assert client.get("/api/collector-tasks").json()["total"] == 1


def test_bound_script_cannot_be_deleted(client):
    creds, _ = publish(client)
    assert client.delete(f"/api/scripts/{creds['script_id']}").status_code == 409
    assert (
        client.post(
            "/api/scripts/batch-delete", json={"ids": [creds["script_id"]]}
        ).status_code
        == 400
    )


def test_schema_never_exposes_secret_defaults(client):
    creds = seed_via_api(client)
    script = client.get(f"/api/scripts/{creds['script_id']}").json()
    script["inputs"].append(
        {
            "name": "token",
            "type": "secret",
            "required": False,
            "default": "private-default",
        }
    )
    assert (
        client.put(f"/api/scripts/{creds['script_id']}", json=script).status_code == 200
    )
    c = client.post(
        "/api/collectors",
        json={
            "name": "secure",
            "slug": "secure",
            "script_id": creds["script_id"],
            "app_ids": [creds["app_id"]],
        },
    ).json()
    contract = client.get(f"/api/collectors/{c['id']}/contract").json()
    assert "private-default" not in str(contract)
    assert contract["input_schema"]["properties"]["token"]["writeOnly"]


def test_tasks_pagination_and_pending_csv(client):
    creds, _ = publish(client)
    first = run(client, creds).json()["execution_id"]
    second = run(client, creds).json()["execution_id"]
    data = client.get("/open/v1/tasks?skip=1&limit=1", headers=auth(creds)).json()
    assert data["total"] == 2 and data["items"][0]["execution_id"] == first
    assert (
        client.get(
            f"/open/v1/tasks/{second}/data?format=csv", headers=auth(creds)
        ).status_code
        == 409
    )
    assert client.get("/open/v1/tasks?skip=-1", headers=auth(creds)).status_code == 422


def test_remove_collector_preserves_history_and_releases_script(client):
    creds, collector = publish(client)
    execution_id = run(client, creds).json()["execution_id"]
    finish(client, execution_id)
    assert client.delete(f"/api/collectors/{collector['id']}").status_code == 204
    assert client.delete(f"/api/collectors/{collector['id']}").status_code == 204
    assert client.get("/api/collectors").json()["total"] == 0
    assert client.get("/open/v1/collectors", headers=auth(creds)).json()["total"] == 0
    assert (
        client.get("/open/v1/collectors/products", headers=auth(creds)).status_code
        == 404
    )
    assert run(client, creds).status_code == 404
    assert client.get(f"/api/collectors/{collector['id']}/contract").status_code == 404
    payload = {
        key: collector[key]
        for key in ("name", "slug", "script_id", "description", "app_ids", "enabled")
    }
    assert (
        client.put(f"/api/collectors/{collector['id']}", json=payload).status_code
        == 404
    )
    # 不能复用旧地址将历史调用方意外指向其他采集任务。
    assert client.post("/api/collectors", json=payload).status_code == 409
    assert client.delete(f"/api/scripts/{creds['script_id']}").status_code == 204
    result = client.get(f"/open/v1/tasks/{execution_id}", headers=auth(creds))
    assert result.status_code == 200 and result.json()["outputs"]["items"] == [
        {"name": "A"},
        {"name": "B"},
    ]
    assert client.get("/api/collector-tasks").json()["total"] == 1
    assert (
        client.get(f"/open/v1/tasks/{execution_id}/data", headers=auth(creds)).json()[
            "total"
        ]
        == 2
    )


def test_remove_without_tasks_and_missing_collector(client):
    creds, collector = publish(client)
    assert client.delete(f"/api/collectors/{collector['id']}").status_code == 204
    assert client.get("/api/collectors").json()["items"] == []
    assert client.get("/api/collector-tasks").json()["total"] == 0
    assert client.delete("/api/collectors/999999").status_code == 404


async def test_archive_column_migration_is_idempotent(db_engine, monkeypatch):
    import app.database as database
    from sqlalchemy import text

    async with db_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE collectors DROP COLUMN archived"))
        await conn.execute(
            text(
                "INSERT INTO collectors (slug, name, description, script_id, app_ids, enabled, created_at, updated_at) VALUES ('old-interface', '旧接口', '', 1, '[]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    monkeypatch.setattr(database, "engine", db_engine)
    await database.init_db()
    await database.init_db()
    async with db_engine.connect() as conn:
        assert (
            await conn.execute(
                text("SELECT archived FROM collectors WHERE slug='old-interface'")
            )
        ).scalar_one() == 0
