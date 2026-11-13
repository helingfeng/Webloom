import json
from unittest.mock import AsyncMock

from mcp.server.fastmcp.exceptions import ToolError
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.mcp import server
from app.services import global_variable_service


@pytest.fixture
def sessions(db_engine, monkeypatch):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(server, "AsyncSessionLocal", maker)
    return maker


async def test_tools_expose_management_without_plaintext_read_tool():
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}
    assert {"list_global_variables", "create_global_variable", "update_global_variable", "delete_global_variable"} <= tools.keys()
    assert "get_global_variable" not in tools
    assert "value" in tools["create_global_variable"].inputSchema["required"]
    assert tools["update_global_variable"].inputSchema["required"] == ["var_id"]


async def test_crud_preserves_secret_on_metadata_updates_and_never_returns_value(sessions):
    secret = "private-login-cookie"
    created = await server.create_global_variable("sid", secret, type="cookie", domain="HTTPS://Account.Example.TEST:8443/login")
    assert created["domain"] == "account.example.test"
    assert created["has_value"] and "value" not in created
    updated = await server.update_global_variable(created["id"], enabled=False, description="会话配置")
    assert updated["has_value"] and not updated["enabled"]
    async with sessions() as db:
        assert (await global_variable_service.get_global_variable(db, created["id"])).value == secret
    enabled = await server.update_global_variable(created["id"], enabled=True)
    listed = await server.list_global_variables(domain="account.example.test", type="cookie")
    assert listed["items"][0]["id"] == created["id"] and listed["total"] == 1
    assert secret not in json.dumps([created, updated, enabled, listed])
    cleared = await server.update_global_variable(created["id"], value="")
    assert not cleared["has_value"]
    async with sessions() as db:
        assert (await global_variable_service.get_global_variable(db, created["id"])).value == ""
    assert (await server.delete_global_variable(created["id"]))["deleted"]
    assert not (await server.delete_global_variable(created["id"]))["deleted"]
    assert (await server.list_global_variables())["total"] == 0


async def test_domain_inheritance_filters_pagination_and_case_insensitive_duplicates(sessions):
    common = await server.create_global_variable("region", "west")
    parent = await server.create_global_variable("Authorization", "private-parent", type="header", domain="example.test")
    child = await server.create_global_variable("token", "private-child", type="localStorage", domain="account.example.test", enabled=False)
    await server.create_global_variable("sid", "private-other", type="cookie", domain="other.test")
    matching = await server.list_global_variables(domain="https://ACCOUNT.example.test/path", limit=1)
    assert matching["total"] == 3 and len(matching["items"]) == 1
    all_matching = await server.list_global_variables(domain="account.example.test")
    assert {item["id"] for item in all_matching["items"]} == {common["id"], parent["id"], child["id"]}
    enabled = await server.list_global_variables(domain="account.example.test", enabled=True)
    assert {item["id"] for item in enabled["items"]} == {common["id"], parent["id"]}
    assert len((await server.list_global_variables(domain="account.example.test", skip=1))["items"]) == 2
    with pytest.raises(ToolError, match="已存在"):
        await server.create_global_variable("authorization", "private-duplicate", type="header", domain="https://EXAMPLE.test/login")


async def test_errors_do_not_repeat_credentials_and_missing_update_is_clear(sessions):
    secret = "private-invalid\r\nheader-value"
    with pytest.raises(ToolError) as error:
        await server.create_global_variable("Authorization", secret, type="header", domain="example.test")
    assert "private-invalid" not in str(error.value)
    with pytest.raises(ToolError, match="不存在"):
        await server.update_global_variable(987654, enabled=False)
    with pytest.raises(ToolError):
        await server.list_global_variables(domain="ftp://invalid.test")


async def test_mcp_saved_login_state_is_injected_into_real_preview(sessions, monkeypatch, tmp_path):
    from app.config import settings
    from app.engine.browser import BrowserOptions
    from app.engine.collection import CollectionPolicy
    from app.services import authoring_service

    monkeypatch.setattr(authoring_service, "AsyncSessionLocal", sessions)
    monkeypatch.setattr("app.services.browser_setting_service.get_browser_options", AsyncMock(return_value=BrowserOptions()))
    monkeypatch.setattr(type(settings), "collection_policy", lambda _: CollectionPolicy(str(tmp_path / "traffic.db")))
    for name, value, kind in (
        ("sid", "private-cookie", "cookie"),
        ("Authorization", "Bearer private-header", "header"),
        ("token", "private-storage", "localStorage"),
    ):
        result = await server.create_global_variable(name, value, type=kind, domain="example.test")
        assert "value" not in result and value not in json.dumps(result)
    result = await server.preview_script(
        start_url="https://account.example.test/path",
        code='''async def route_handler(route):
    OUTPUTS["header_loaded"] = route.request.headers.get("authorization") == "Bearer private-header"
    await route.fulfill(content_type="text/html", body='<script>document.title=localStorage.getItem("token") || "missing"</script>')
await context.route("**/*", route_handler)
await page.goto(START_URL)
OUTPUTS["storage_loaded_before_scripts"] = await page.title() == "private-storage"
OUTPUTS["cookie_loaded"] = any(c["name"] == "sid" and c["value"] == "private-cookie" for c in await context.cookies(START_URL))''',
    )
    assert result["status"] == "success", result
    assert result["outputs"] == {"header_loaded": True, "storage_loaded_before_scripts": True, "cookie_loaded": True}
    assert all(secret not in result["logs"] for secret in ("private-cookie", "private-header", "private-storage"))
