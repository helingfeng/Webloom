"""统一浏览器适配；子进程仅接收显式浏览器配置，不读取后端 .env。"""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
import importlib.util
import json
import os
from typing import Any, Literal


class BrowserLaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserOptions:
    engine: Literal["playwright", "cloakbrowser"] = "playwright"
    humanize: bool = True
    license_key: str | None = field(default=None, repr=False)
    proxy_url: str | None = field(default=None, repr=False)
    locale: str | None = None
    timezone: str | None = None

    def to_subprocess_env(self) -> dict[str, str]:
        return {
            "ATP_BROWSER_OPTIONS": json.dumps(
                {
                    "engine": self.engine,
                    "humanize": self.humanize,
                    "proxy_url": self.proxy_url,
                    "locale": self.locale,
                    "timezone": self.timezone,
                }
            ),
            "ATP_BROWSER_LICENSE_KEY": self.license_key or "",
        }

    @classmethod
    def from_subprocess_env(cls) -> "BrowserOptions":
        data = json.loads(os.environ.get("ATP_BROWSER_OPTIONS", "{}"))
        return cls(
            **data, license_key=os.environ.get("ATP_BROWSER_LICENSE_KEY") or None
        )

    def public_status(self) -> dict:
        installed = importlib.util.find_spec("cloakbrowser") is not None
        configured = bool(self.license_key)
        if installed:
            try:
                from cloakbrowser.license import resolve_license_key

                configured = bool(resolve_license_key(self.license_key))
            except ImportError:
                installed = False
        ready = self.engine == "playwright" or installed and configured
        return {
            "engine": self.engine,
            "ready": ready,
            "cloakbrowser_installed": installed,
            "license_configured": configured,
            "humanize": self.humanize if self.engine == "cloakbrowser" else False,
            "proxy_configured": (
                bool(self.proxy_url) if self.engine == "cloakbrowser" else False
            ),
            "message": (
                "已使用标准 Playwright；可在后台启用 CloakBrowser"
                if self.engine == "playwright"
                else (
                    "CloakBrowser 启动条件已配置，实际授权及二进制可用性在启动时验证"
                    if ready
                    else "请安装 CloakBrowser 并配置 CLOAKBROWSER_LICENSE_KEY"
                )
            ),
        }


@dataclass
class BrowserResource:
    browser: Any
    engine: str
    playwright: Any = None
    _closed: bool = False

    async def stop(self) -> None:
        if self.playwright is not None:
            owner, self.playwright = self.playwright, None
            await owner.stop()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self.browser.close()
        finally:
            await self.stop()


def _redact(message: str, options: BrowserOptions) -> str:
    for secret in (options.license_key, options.proxy_url):
        if secret:
            message = message.replace(secret, "******")
    return message


async def launch_browser(
    options: BrowserOptions, *, headless: bool = True
) -> BrowserResource:
    if options.engine == "cloakbrowser":
        try:
            from cloakbrowser import launch_async
            from cloakbrowser.license import resolve_license_key
        except ImportError as exc:
            raise BrowserLaunchError(
                "CloakBrowser 未安装，请安装 backend/requirements.txt"
            ) from exc
        # 禁止在 MCP/worker 中触发邮箱注册或交互式登录。
        resolved_key = resolve_license_key(options.license_key)
        if not resolved_key:
            raise BrowserLaunchError(
                "CloakBrowser 缺少许可证：请在 backend/.env 配置 CLOAKBROWSER_LICENSE_KEY，或先运行 cloakbrowser login"
            )
        options = replace(options, license_key=resolved_key)
        try:
            browser = await launch_async(
                headless=headless,
                humanize=options.humanize,
                license_key=options.license_key,
                proxy=options.proxy_url,
                locale=options.locale,
                timezone=options.timezone,
            )
        except Exception as exc:
            raise BrowserLaunchError(
                "CloakBrowser 启动失败：" + _redact(str(exc), options)
            ) from None
        return BrowserResource(browser, "cloakbrowser")
    if options.engine != "playwright":
        raise BrowserLaunchError("未知浏览器引擎，请选择 playwright 或 cloakbrowser")
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    try:
        browser = await playwright.chromium.launch(headless=headless)
    except BaseException:
        await playwright.stop()
        raise
    return BrowserResource(browser, "playwright", playwright)


@asynccontextmanager
async def managed_browser(options: BrowserOptions, *, headless: bool = True):
    resource = await launch_browser(options, headless=headless)
    try:
        yield resource.browser
    finally:
        await resource.close()
