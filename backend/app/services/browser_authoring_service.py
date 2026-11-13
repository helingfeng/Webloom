"""有界、可连续操作的页面探索会话；与脚本执行分离。"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.engine.browser import BrowserResource, launch_browser
from app.config import settings
from app.engine.collection import CollectionRuntime, create_collection_context

from app.database import AsyncSessionLocal
from app.services import global_variable_service
from app.services.browser_setting_service import get_browser_options


@dataclass
class BrowserSession:
    playwright: object
    browser: object
    page: object
    credentials_applied: bool
    engine: str = "playwright"
    touched: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    resource: BrowserResource | None = None
    collection: CollectionRuntime | None = None


class BrowserSessions:
    def __init__(self):
        self.sessions: dict[str, BrowserSession] = {}
        self.lock = asyncio.Lock()

    async def reap(self):
        for key, session in list(self.sessions.items()):
            if time.monotonic() - session.touched > 600 and not session.lock.locked():
                await self.close(key)

    async def close(self, key: str):
        session = self.sessions.pop(key, None)
        if session:
            async with session.lock:
                if session.resource is not None:
                    await session.resource.close()
                else:
                    try:
                        await session.browser.close()
                    finally:
                        await session.playwright.stop()

    async def sweep(self):
        while True:
            await asyncio.sleep(30)
            await self.reap()

    async def close_all(self):
        for key in list(self.sessions):
            await self.close(key)

    async def open(self, url: str, inherit_global: bool, max_chars: int):
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("url 必须是完整的 http 或 https 地址")
        async with self.lock:
            await self.reap()
            if len(self.sessions) >= 4:
                raise ValueError("探索会话已达 4 个，请先 close_page")
            headers, storage, cookies = {}, {}, []
            if inherit_global:
                async with AsyncSessionLocal() as db:
                    headers, _, storage, cookies = (
                        await global_variable_service.get_active_globals_grouped(
                            db, url
                        )
                    )
            resource = await launch_browser(await get_browser_options(), headless=True)
            p = resource
            browser = None
            try:
                browser = resource.browser
                context, collection = await create_collection_context(
                    browser, settings.collection_policy(), headers=headers,
                    cookies=cookies, local_storage=storage, start_url=url, timeout=10000,
                )
                page = await context.new_page()
                page.set_default_timeout(10000)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                key = uuid.uuid4().hex
                session = BrowserSession(
                    p,
                    browser,
                    page,
                    bool(headers or storage or cookies),
                    engine=resource.engine,
                    resource=resource,
                    collection=collection,
                )
                result = await self.snapshot(session, max_chars)
                self.sessions[key] = session
                return {"session_id": key, **result}
            except BaseException:
                await resource.close()
                raise

    async def snapshot(self, session: BrowserSession, max_chars: int):
        if session.collection:
            await session.collection.check(session.page)
        limit = min(max(max_chars, 1000), 20000)
        data = await session.page.evaluate(SNAPSHOT, limit)
        return {
            "url": session.page.url,
            "title": await session.page.title(),
            "credentials_applied": session.credentials_applied,
            "browser_engine": session.engine,
            **data,
        }

    async def act(
        self, key: str, action: str, selector: str, value: str, max_chars: int
    ):
        await self.reap()
        session = self.sessions.get(key)
        if not session:
            raise ValueError("探索会话不存在或已过期，请重新 open_page")
        async with session.lock:
            session.touched = time.monotonic()
            page = session.page
            if session.collection:
                await session.collection.check(page)
                if action in ("click", "press", "scroll"):
                    await session.collection.before_action(page)
            locator = page.locator(selector) if selector else None
            if (
                action in ("click", "fill", "select", "press", "wait", "html")
                and locator is None
            ):
                raise ValueError("该操作需要 selector")
            if action == "click":
                await locator.click()
            elif action == "fill":
                await locator.fill(value)
            elif action == "select":
                await locator.select_option(value)
            elif action == "press":
                await locator.press(value)
            elif action == "wait":
                await locator.wait_for(state="visible")
            elif action == "scroll":
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
            elif action == "html":
                html = await locator.evaluate(
                    'el => { const c=el.cloneNode(true); c.querySelectorAll("input,textarea").forEach(e => { e.removeAttribute("value"); e.textContent=""; }); if(c.matches("input,textarea")){c.removeAttribute("value");c.textContent="";} return c.outerHTML; }'
                )
                return {
                    "html": html[: min(max(max_chars, 1000), 20000)],
                    "url": page.url,
                }
            elif action != "snapshot":
                raise ValueError("不支持的页面操作")
            return await self.snapshot(session, max_chars)


browser_sessions = BrowserSessions()

SNAPSHOT = """(LIMIT) => {
                        const clean = value => (value || '').replace(/\\s+/g, ' ').trim();
                        const nodes = selector => [...document.querySelectorAll(selector)];
                        return {
                            text: clean(document.body?.innerText).slice(0, LIMIT),
                            headings: nodes('h1,h2,h3').slice(0, 50).map(el => ({
                                level: el.tagName.toLowerCase(), text: clean(el.innerText)
                            })),
                            links: nodes('a[href]').slice(0, 100).map(a => ({
                                text: clean(a.innerText || a.getAttribute('aria-label')),
                                href: a.href,
                                testId: a.getAttribute('data-testid'),
                                className: typeof a.className === 'string' ? a.className : ''
                            })),
                            tables: nodes('table').slice(0, 20).map(table =>
                                [...table.querySelectorAll('tr')].slice(0, 20).map(row =>
                                    [...row.querySelectorAll('th,td')].map(cell => clean(cell.innerText))
                                )
                            ),
                            forms: nodes('form').slice(0, 30).map(form => ({
                                action: form.action,
                                method: (form.method || 'get').toUpperCase(),
                                fields: [...form.querySelectorAll('input,select,textarea')].slice(0, 30).map(el => ({
                                    tag: el.tagName.toLowerCase(), type: el.type || '',
                                    name: el.name || '', id: el.id || '',
                                    placeholder: el.getAttribute('placeholder') || '',
                                    label: el.labels?.[0]?.innerText?.trim() || ''
                                }))
                            })),
                            sample_elements: nodes('article,li,[data-testid],[role=row]')
                                .filter(el => el.getClientRects().length)
                                .slice(0, 80).map(el => ({
                                    tag: el.tagName.toLowerCase(),
                                    id: el.id || '',
                                    testId: el.getAttribute('data-testid') || '',
                                    className: typeof el.className === 'string' ? el.className : '',
                                    text: clean(el.innerText).slice(0, 400)
                                })),
                            controls: nodes('button,[role=button],[role=tab],[role=link]')
                                .filter(el => el.getClientRects().length)
                                .slice(0, 100).map(el => ({
                                    tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '',
                                    text: clean(el.innerText || el.getAttribute('aria-label')),
                                    ariaLabel: el.getAttribute('aria-label') || '',
                                    title: el.getAttribute('title') || '',
                                    id: el.id || '',
                                    testId: el.getAttribute('data-testid') || ''
                                }))
                        };
                    }"""
