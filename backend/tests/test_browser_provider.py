"""浏览器提供方边界：配置隔离、无交互授权、无静默降级和资源清理。"""

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.engine.browser import (
    BrowserOptions,
    BrowserLaunchError,
    launch_browser,
    managed_browser,
)


def install_fake_cloak(monkeypatch, launcher, resolver):
    monkeypatch.setitem(
        sys.modules, "cloakbrowser", SimpleNamespace(launch_async=launcher)
    )
    monkeypatch.setitem(
        sys.modules,
        "cloakbrowser.license",
        SimpleNamespace(resolve_license_key=resolver),
    )


async def test_cloak_receives_scoped_options_and_closes_once(monkeypatch):
    browser = SimpleNamespace(close=AsyncMock())
    launch = AsyncMock(return_value=browser)
    install_fake_cloak(monkeypatch, launch, lambda key: key)
    options = BrowserOptions(
        engine="cloakbrowser",
        license_key="test-license",
        proxy_url="http://user:pass@proxy.test:8080",
    )
    async with managed_browser(options, headless=False) as actual:
        assert actual is browser
    assert launch.call_args.kwargs["humanize"] is True
    assert launch.call_args.kwargs["headless"] is False
    assert launch.call_args.kwargs["license_key"] == "test-license"
    browser.close.assert_awaited_once()


async def test_missing_license_fails_before_any_download_or_launch(monkeypatch):
    launch = AsyncMock()
    install_fake_cloak(monkeypatch, launch, lambda key: None)
    with pytest.raises(BrowserLaunchError, match="缺少许可证"):
        await launch_browser(BrowserOptions(engine="cloakbrowser"))
    launch.assert_not_awaited()


async def test_cloak_failure_redacts_secrets_without_fallback(monkeypatch):
    launch = AsyncMock(
        side_effect=RuntimeError("denied test-license at http://user:pass@proxy.test")
    )
    install_fake_cloak(monkeypatch, launch, lambda key: key)
    with pytest.raises(BrowserLaunchError) as error:
        await launch_browser(
            BrowserOptions(
                engine="cloakbrowser",
                license_key="test-license",
                proxy_url="http://user:pass@proxy.test",
            )
        )
    assert "test-license" not in str(error.value) and "user:pass" not in str(
        error.value
    )
    launch.assert_awaited_once()


async def test_playwright_cleanup_on_launch_failure(monkeypatch):
    import playwright.async_api

    owner = SimpleNamespace(
        chromium=SimpleNamespace(
            launch=AsyncMock(side_effect=RuntimeError("launch failed"))
        ),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(
        playwright.async_api,
        "async_playwright",
        lambda: SimpleNamespace(start=AsyncMock(return_value=owner)),
    )
    with pytest.raises(RuntimeError, match="launch failed"):
        await launch_browser(BrowserOptions())
    owner.stop.assert_awaited_once()


def test_child_configuration_roundtrip_and_secret_free_status(monkeypatch):
    options = BrowserOptions(
        engine="cloakbrowser",
        license_key="test-license",
        proxy_url="http://user:pass@proxy.test",
    )
    for key, value in options.to_subprocess_env().items():
        monkeypatch.setenv(key, value)
    assert BrowserOptions.from_subprocess_env() == options
    assert "test-license" not in repr(options) and "user:pass" not in repr(options)
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    status = options.public_status()
    assert status["ready"] and status["license_configured"]
    assert "test-license" not in str(status) and "user:pass" not in str(status)


async def test_context_exception_still_closes_stock_browser(monkeypatch):
    import playwright.async_api

    browser = SimpleNamespace(close=AsyncMock())
    owner = SimpleNamespace(
        chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)),
        stop=AsyncMock(),
    )
    monkeypatch.setattr(
        playwright.async_api,
        "async_playwright",
        lambda: SimpleNamespace(start=AsyncMock(return_value=owner)),
    )
    with pytest.raises(ValueError):
        async with managed_browser(BrowserOptions()):
            raise ValueError("script failed")
    browser.close.assert_awaited_once()
    owner.stop.assert_awaited_once()


async def test_recorder_uses_shared_engine_and_current_protocol(monkeypatch, tmp_path):
    from contextlib import asynccontextmanager
    from app.config import settings
    from app.engine import browser as provider
    from app.services.recording_service import RecordingSession, _run_recorder

    channel = SimpleNamespace(send=AsyncMock())
    page = SimpleNamespace(goto=AsyncMock())
    context = SimpleNamespace(
        _impl_obj=SimpleNamespace(_channel=channel),
        new_page=AsyncMock(return_value=page),
        add_init_script=AsyncMock(),
        pages=[],
        on=lambda *args: None,
        set_default_timeout=lambda value: None,
    )
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context))
    seen = {}

    @asynccontextmanager
    async def managed(options, *, headless):
        seen["engine"], seen["headless"] = options.engine, headless
        try:
            yield browser
        finally:
            seen["closed"] = True

    monkeypatch.setattr(provider, "managed_browser", managed)
    monkeypatch.setattr(
        "app.services.recording_service.get_browser_options",
        AsyncMock(return_value=settings.browser_options()),
    )
    session = RecordingSession(1, "https://example.test", tmp_path / "record.py")
    await _run_recorder(session, {}, {"token": "test"}, [])
    assert seen == {
        "engine": settings.browser_engine,
        "headless": False,
        "closed": True,
    }
    assert channel.send.call_args.args[0:2] == ("enableRecorder", None)
    assert channel.send.call_args.args[2]["language"] == "python-async"
    context.add_init_script.assert_awaited_once()
    page.goto.assert_awaited_once()
