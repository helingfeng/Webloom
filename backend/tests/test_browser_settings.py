"""浏览器开关：持久化、跨进程读取、先决条件、HTTP 契约与凭证隔离。"""

from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import get_db
from app.engine.browser import BrowserOptions
from app.main import app
from app.services import browser_setting_service as service


def fake_status(self):
    return {
        "engine": self.engine,
        "ready": self.engine == "playwright" or bool(self.license_key),
        "cloakbrowser_installed": True,
        "license_configured": bool(self.license_key),
        "humanize": self.engine == "cloakbrowser" and self.humanize,
        "proxy_configured": bool(self.proxy_url),
        "message": "测试浏览器配置",
    }


@pytest.fixture
def configured(monkeypatch):
    options = BrowserOptions(engine="cloakbrowser", license_key="private-test-key")
    monkeypatch.setattr(type(service.settings), "browser_options", lambda _: options)
    monkeypatch.setattr(BrowserOptions, "public_status", fake_status)
    return options


async def test_switch_persists_across_independent_sessions(db, db_engine, configured, monkeypatch):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(service, "AsyncSessionLocal", maker)
    # 首次使用环境默认值；worker/MCP 每次独立建会话读取，无进程内缓存。
    assert (await service.get_browser_options()).engine == "cloakbrowser"
    await service.update_browser_setting(db, False)
    assert (await service.get_browser_options()).engine == "playwright"
    # 环境默认值改变不会覆盖已保存的显式关闭。
    monkeypatch.setattr(type(service.settings), "browser_options", lambda _: replace(configured, humanize=False))
    assert (await service.get_browser_options()).engine == "playwright"
    async with maker() as other:
        await service.update_browser_setting(other, True)
    options = await service.get_browser_options()
    assert options.engine == "cloakbrowser" and options.license_key == "private-test-key"
    assert not options.humanize


async def test_missing_license_rejects_enable_but_allows_disable(db, monkeypatch):
    monkeypatch.setattr(type(service.settings), "browser_options", lambda _: BrowserOptions())
    monkeypatch.setattr(BrowserOptions, "public_status", fake_status)
    await service.update_browser_setting(db, False)
    with pytest.raises(ValueError, match="无法启用"):
        await service.update_browser_setting(db, True)
    assert not (await service.get_browser_setting(db)).cloakbrowser_enabled


async def test_admin_contract_and_no_credentials(db, configured):
    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            initial = await client.get("/api/mcp/browser-settings")
            assert initial.status_code == 200
            assert initial.json()["cloakbrowser_enabled"]
            response = await client.put("/api/mcp/browser-settings", json={"cloakbrowser_enabled": False})
            assert response.status_code == 200 and response.json()["engine"] == "playwright"
            assert "private-test-key" not in initial.text + response.text
            assert "license_key" not in response.json()
            for invalid in ({}, {"cloakbrowser_enabled": "false"}, {"cloakbrowser_enabled": True, "license_key": "injected"}):
                response = await client.put("/api/mcp/browser-settings", json=invalid)
                assert response.status_code == 422
            assert not (await client.get("/api/mcp/browser-settings")).json()["cloakbrowser_enabled"]
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_exploration_uses_latest_database_choice(monkeypatch):
    from app.services import browser_authoring_service as authoring

    options = BrowserOptions(engine="playwright")
    resolver = AsyncMock(return_value=options)
    launcher = AsyncMock(side_effect=RuntimeError("stop before navigation"))
    monkeypatch.setattr(authoring, "get_browser_options", resolver)
    monkeypatch.setattr(authoring, "launch_browser", launcher)
    sessions = authoring.BrowserSessions()
    for engine in ("playwright", "cloakbrowser"):
        resolver.return_value = replace(options, engine=engine)
        with pytest.raises(RuntimeError, match="stop before navigation"):
            await sessions.open("https://example.test", False, 1000)
        assert launcher.call_args.args[0].engine == engine
