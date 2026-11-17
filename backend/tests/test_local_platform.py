"""真实独立服务 + 新建 SQLite 文件 + Chromium，Redis 指向不可用端口。"""

import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

import httpx

BACKEND = Path(__file__).resolve().parents[1]


@contextmanager
def server(folder, entrypoint="app.main:app"):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{folder / 'webloom.db'}",
        "EXECUTION_BACKEND": "local",
        "STORAGE_DIR": str(folder / "storage"),
        "SCRIPTS_DIR": str(folder / "storage/scripts"),
        "EXECUTIONS_DIR": str(folder / "runs"),
        "BROWSER_ENGINE": "playwright",
        "CLOAKBROWSER_LICENSE_KEY": "",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "MAX_CONCURRENT_EXECUTIONS": "2",
        "SCRIPT_EXECUTION_TIMEOUT": "20",
    }
    with (folder / "server.log").open("a") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                entrypoint,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=10
            ) as client:
                deadline = time.monotonic() + 15
                while True:
                    if process.poll() is not None:
                        raise AssertionError(
                            "服务启动失败：" + (folder / "server.log").read_text()
                        )
                    try:
                        client.get("/openapi.json").raise_for_status()
                        break
                    except httpx.HTTPError:
                        if time.monotonic() > deadline:
                            raise AssertionError("服务启动超时")
                        time.sleep(0.1)
                yield client
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def success(response):
    assert response.is_success, response.text
    return response.json()


def test_sqlite_local_full_platform_executes_and_persists_without_worker(tmp_path):
    with server(tmp_path) as client:
        health = success(client.get("/api/health"))
        assert health["database"] == "sqlite" and health["execution_backend"] == "local"
        assert health["queue"]["worker_alive"] and health["queue"]["available"]
        workspace = success(
            client.post("/api/workspaces", json={"name": "离线部署测试"})
        )
        success(
            client.post(
                "/api/global-variables",
                json={
                    "name": "X-Proof",
                    "type": "header",
                    "value": "demo-value",
                    "domain": "local-smoke.test",
                },
            )
        )
        script = success(
            client.post(
                "/api/scripts",
                json={
                    "workspace_id": workspace["id"],
                    "name": "离线图书目录",
                    "start_url": "https://local-smoke.test/",
                    "inputs": [
                        {
                            "name": "count",
                            "type": "number",
                            "default": 2,
                            "required": False,
                        }
                    ],
                    "outputs": [{"name": "items", "description": "图书列表"}],
                    "code": """async def handle(route):
    OUTPUTS["header_loaded"] = route.request.headers.get("x-proof") == "demo-value"
    await route.fulfill(content_type="text/html", body="<article>book-one</article><article>book-two</article>")
await context.route("**/*", handle)
await page.goto(START_URL)
print("offline-first-line")
await asyncio.sleep(2)
OUTPUTS["items"] = [{"title": value} for value in (await page.locator("article").all_inner_texts())[:int(INPUTS["count"])]]""",
                },
            )
        )
        task = success(
            client.post(
                f"/api/scripts/{script['id']}/run", json={"inputs": {"count": 1}}
            )
        )
        assert task["status"] == "pending"
        deadline, live_logs = time.monotonic() + 20, False
        while time.monotonic() < deadline:
            execution = success(client.get(f"/api/executions/{task['execution_id']}"))
            if (
                execution["status"] == "running"
                and "offline-first-line" in execution["logs"]
            ):
                live_logs = True
            if execution["status"] in ("success", "failed"):
                break
            time.sleep(0.1)
        assert execution["status"] == "success", execution["logs"]
        assert execution["outputs"] == {
            "header_loaded": True,
            "items": [{"title": "book-one"}],
        }
        assert live_logs, "日志必须在任务结束之前增量落库"

        app = success(client.post("/api/open-apps", json={"name": "离线调用应用"}))
        auth = {"Authorization": f"Bearer {app['app_key']}.{app['app_secret']}"}
        success(
            client.post(
                "/api/collectors",
                json={
                    "name": "离线图书接口",
                    "slug": "local-demo",
                    "script_id": script["id"],
                    "app_ids": [app["id"]],
                },
            )
        )
        request = {"inputs": {"count": 1}, "wait_seconds": 0}
        accepted = success(
            client.post(
                "/open/v1/collectors/local-demo/runs",
                json=request,
                headers={**auth, "Idempotency-Key": "offline-1"},
            )
        )
        same = success(
            client.post(
                "/open/v1/collectors/local-demo/runs",
                json=request,
                headers={**auth, "Idempotency-Key": "offline-1"},
            )
        )
        assert accepted["execution_id"] == same["execution_id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            detail = success(
                client.get(
                    accepted["result_url"], params={"wait_seconds": 1}, headers=auth
                )
            )
            if detail["finished"]:
                break
        assert detail["status"] == "success", detail.get("error")
        data = success(
            client.get(accepted["data_url"], params={"field": "items"}, headers=auth)
        )
        assert data["items"] == [{"title": "book-one"}]
        csv = client.get(
            accepted["data_url"],
            params={"field": "items", "format": "csv"},
            headers=auth,
        )
        assert csv.is_success and "book-one" in csv.text
        other = success(client.post("/api/open-apps", json={"name": "未授权应用"}))
        assert (
            client.get(
                accepted["result_url"],
                headers={
                    "Authorization": f"Bearer {other['app_key']}.{other['app_secret']}"
                },
            ).status_code
            == 404
        )
    with sqlite3.connect(tmp_path / "webloom.db") as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    with server(tmp_path) as client:
        assert (
            success(client.get(f"/api/scripts/{script['id']}"))["name"]
            == "离线图书目录"
        )
        assert success(client.get(accepted["result_url"], headers=auth))["outputs"][
            "items"
        ] == [{"title": "book-one"}]


def test_minimal_mcp_runs_persistent_tasks_with_sqlite_and_no_redis(tmp_path):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def verify(base):
        def client_factory(headers=None, timeout=None, auth=None):
            return httpx.AsyncClient(
                headers=headers, timeout=timeout, auth=auth, trust_env=False
            )

        async with streamablehttp_client(
            base + "/mcp", httpx_client_factory=client_factory
        ) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()

                async def call(name, args):
                    result = await session.call_tool(name, args)
                    assert not result.isError, result
                    return result.structuredContent or json.loads(
                        next(c.text for c in result.content if c.type == "text")
                    )

                workspace = await call("create_workspace", {"name": "MCP 离线空间"})
                script = await call(
                    "create_script",
                    {
                        "name": "MCP 离线脚本",
                        "workspace_id": workspace["id"],
                        "inherit_global": False,
                        "code": 'OUTPUTS["items"] = [{"value": "mcp-local"}]',
                    },
                )
                task = await call("run_script", {"script_id": script["id"]})
                async with asyncio.timeout(20):
                    while True:
                        result = await call(
                            "get_execution",
                            {"execution_id": task["execution_id"], "wait_seconds": 1},
                        )
                        if result["finished"]:
                            break
                assert result["status"] == "success", result["logs"]
                assert result["outputs"] == {"items": [{"value": "mcp-local"}]}

    with server(tmp_path, "app.mcp_main:app") as client:
        asyncio.run(verify(str(client.base_url).rstrip("/")))
