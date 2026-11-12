from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.engine.runner import (
    render_script_code,
    validate_script_code,
    ScriptExecutionError,
)
from app.mcp.server import mcp
from app.schemas.script import ScriptCreate, VariableDefinition
from app.services import authoring_service
from app.services.browser_authoring_service import BrowserSession, BrowserSessions


def test_validate_real_template():
    assert validate_script_code("await page.goto(START_URL)")["valid"]
    assert validate_script_code("print(DATA_VIEWS_ONE)")["uses_data_views"]
    assert not validate_script_code('print("DATA_VIEWS")')["uses_data_views"]
    compile(render_script_code('print({"x": "__TIMEOUT__"})'), "<test>", "exec")


@pytest.mark.parametrize("code", ["", "await page.goto(", "break"])
def test_invalid_code(code):
    with pytest.raises(ValueError):
        validate_script_code(code)


async def test_preview_defaults_and_failure(monkeypatch):
    run = AsyncMock(return_value=("hello", {"items": [1]}))
    monkeypatch.setattr(authoring_service, "execute_script_code", run)
    payload = ScriptCreate(
        workspace_id=0,
        name="draft",
        code="print(INPUTS)",
        inherit_global=False,
        inputs=[VariableDefinition(name="limit", type="number", default=10)],
    )
    result = await authoring_service.preview_script(payload, {"limit": 2})
    assert result["outputs"] == {"items": [1]}
    assert run.call_args.args[1] == {"limit": 2}
    assert run.call_args.kwargs["capture_frames"] is False
    run.side_effect = ScriptExecutionError("failed", "traceback")
    result = await authoring_service.preview_script(payload, {})
    assert result["status"] == "failed"
    assert result["logs"] == "traceback"


async def test_preview_required_input():
    payload = ScriptCreate(
        workspace_id=0,
        name="draft",
        code="print(INPUTS)",
        inherit_global=False,
        inputs=[VariableDefinition(name="url", type="string")],
    )
    with pytest.raises(ValueError, match="url"):
        await authoring_service.preview_script(payload, {})


async def test_expired_session_and_cleanup():
    sessions = BrowserSessions()
    browser, playwright = SimpleNamespace(close=AsyncMock()), SimpleNamespace(
        stop=AsyncMock()
    )
    sessions.sessions["old"] = BrowserSession(
        playwright, browser, None, False, touched=0
    )
    await sessions.reap()
    assert not sessions.sessions
    browser.close.assert_awaited_once()
    playwright.stop.assert_awaited_once()
    await sessions.close("old")
    with pytest.raises(ValueError, match="过期"):
        await sessions.act("old", "snapshot", "", "", 1000)


async def test_mcp_contract():
    tools = {t.name: t for t in await mcp.list_tools()}
    assert {
        "open_page",
        "browse_page",
        "close_page",
        "preview_script",
        "validate_script",
        "create_script",
        "update_script",
        "run_script",
        "get_execution",
    } <= tools.keys()
    assert "code" in tools["preview_script"].inputSchema["required"]


async def test_real_browser_dom_and_interaction():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(
                "<h1>目录</h1><button onclick=\"document.querySelector('h1').innerText='结果'\">加载</button><article>条目</article>"
            )
            sessions = BrowserSessions()
            sessions.sessions["live"] = BrowserSession(p, browser, page, False)
            first = await sessions.act("live", "snapshot", "", "", 1000)
            assert first["headings"][0]["text"] == "目录"
            second = await sessions.act("live", "click", "button", "", 1000)
            assert second["headings"][0]["text"] == "结果"
            assert second["sample_elements"][0]["text"] == "条目"
        finally:
            await browser.close()


async def test_real_preview_subprocess():
    payload = ScriptCreate(
        workspace_id=0,
        name="draft",
        inherit_global=False,
        code='await page.set_content("<article>真实结果</article>")\nOUTPUTS["items"] = await page.locator("article").all_inner_texts()',
    )
    result = await authoring_service.preview_script(payload, {})
    assert result["status"] == "success", result
    assert result["outputs"] == {"items": ["真实结果"]}


async def test_preview_rejects_unavailable_views():
    payload = ScriptCreate(
        workspace_id=0, name="draft", code="print(DATA_VIEWS)", inherit_global=False
    )
    with pytest.raises(ValueError, match="run_script"):
        await authoring_service.preview_script(payload, {})


async def test_mcp_save_and_retrieve(db_engine, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.mcp import server

    monkeypatch.setattr(
        server,
        "AsyncSessionLocal",
        async_sessionmaker(db_engine, expire_on_commit=False),
    )
    workspace = await server.create_workspace("采集验证")
    created = await server.create_script(
        workspace_id=workspace["id"],
        name="目录",
        code='OUTPUTS["items"] = []',
        outputs=[server.OutputDefinition(name="items")],
    )
    fetched = await server.get_script(created["id"])
    assert fetched["code"] == 'OUTPUTS["items"] = []'
    await server.update_script(created["id"], code='OUTPUTS["items"] = [1]')
    fetched = await server.get_script(created["id"])
    assert fetched["name"] == "目录"
    assert fetched["code"] == 'OUTPUTS["items"] = [1]'
    assert fetched["outputs"] == [{"name": "items", "description": ""}]


async def test_real_runner_injects_storage_before_page_scripts_and_uses_input_url():
    import uuid
    from app.models.script import Script
    from app.engine.runner import execute_script_code

    script = Script(
        start_url="https://old.test",
        code="""async def handle(route):
    OUTPUTS["authorization"] = route.request.headers.get("authorization")
    await route.fulfill(content_type="text/html", body='<script>document.title = localStorage.getItem("token") || "missing"</script>')
await context.route("**/*", handle)
await page.goto(START_URL, wait_until="domcontentloaded")
OUTPUTS["token"] = await page.title()
OUTPUTS["url"] = START_URL
OUTPUTS["cookies"] = await context.cookies(START_URL)""",
        inputs=[
            {"name": "url", "type": "string"},
            {"name": "sid", "type": "cookie"},
            {"name": "authorization", "type": "header"},
        ],
    )
    _, outputs = await execute_script_code(
        script,
        {
            "url": "https://new.test/page",
            "sid": "input-cookie",
            "authorization": "input-header",
        },
        -uuid.uuid4().int,
        global_headers={"Authorization": "global-header"},
        global_local_storage={"token": "first-load-token"},
        headless=True,
        capture_frames=False,
    )
    assert outputs["token"] == "first-load-token"
    assert outputs["url"] == "https://new.test/page"
    assert outputs["authorization"] == "input-header"
    assert outputs["cookies"][0]["domain"] == "new.test"
    assert outputs["cookies"][0]["value"] == "input-cookie"
