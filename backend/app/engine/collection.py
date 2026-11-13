"""低负载采集运行时。子进程仅接收 ATP 配置，不读取平台环境或凭证。"""

import asyncio
from contextlib import closing
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from functools import wraps
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import urldefrag, urljoin, urlsplit


class CollectionStopped(ValueError):
    """站点拒绝/限流或任务预算耗尽；不得自动重试整个脚本。"""


@dataclass(frozen=True)
class CollectionPolicy:
    state_path: str
    min_interval_seconds: float = 2
    cooldown_seconds: int = 300
    max_requests: int = 50
    max_wait_seconds: float = 30

    def to_env(self) -> dict[str, str]:
        return {"ATP_COLLECTION_POLICY": json.dumps(asdict(self))}

    @classmethod
    def from_env(cls):
        return cls(**json.loads(os.environ["ATP_COLLECTION_POLICY"]))

    def public_status(self) -> dict:
        return {key: value for key, value in asdict(self).items() if key != "state_path"}


def host_key(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""
    return parsed.hostname.lower().rstrip(".")


def retry_after_seconds(value: str | None, now: float) -> float:
    if not value:
        return 0
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = parsedate_to_datetime(value).timestamp() - now
        except (ValueError, TypeError, OverflowError):
            return 0
    return max(0, delay) if math.isfinite(delay) else 0


class TrafficGate:
    """本机 SQLite 原子协调 MCP、worker 和脚本子进程；只保存域名及时间。"""

    def __init__(self, policy: CollectionPolicy):
        self.policy = policy

    def _transaction(self, host: str, cooldown: float | None = None) -> float:
        path = Path(self.policy.state_path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with closing(sqlite3.connect(path, timeout=5)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS traffic (host TEXT PRIMARY KEY, next_at REAL NOT NULL, blocked_until REAL NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            db.execute("DELETE FROM traffic WHERE next_at < ? AND blocked_until < ?", (now - 7 * 86400, now - 7 * 86400))
            db.execute("INSERT OR IGNORE INTO traffic VALUES (?, 0, 0)", (host,))
            next_at, blocked_until = db.execute("SELECT next_at, blocked_until FROM traffic WHERE host = ?", (host,)).fetchone()
            if cooldown is not None:
                db.execute("UPDATE traffic SET blocked_until = MAX(blocked_until, ?) WHERE host = ?", (now + cooldown, host))
                return cooldown
            if blocked_until > now:
                raise CollectionStopped(f"[collection] {host} 处于站点冷却期，约 {math.ceil(blocked_until - now)} 秒后再试；请勿循环重试")
            delay = max(0, next_at - now)
            if not delay:
                db.execute("UPDATE traffic SET next_at = ? WHERE host = ?", (now + self.policy.min_interval_seconds, host))
            return delay

    async def wait(self, url: str):
        host = host_key(url)
        if not host:
            return
        deadline = time.monotonic() + self.policy.max_wait_seconds
        while True:
            delay = await asyncio.to_thread(self._transaction, host)
            if delay <= 0:
                return
            if time.monotonic() + delay > deadline:
                raise CollectionStopped(f"[collection] {host} 访问排队超过预算，请稍后提交任务")
            await asyncio.sleep(delay)

    async def cooldown(self, url: str, retry_after: str | None = None):
        if host := host_key(url):
            delay = max(self.policy.cooldown_seconds, retry_after_seconds(retry_after, time.time()))
            await asyncio.to_thread(self._transaction, host, delay)


class CollectionRuntime:
    def __init__(self, context, policy: CollectionPolicy):
        self.context = context
        self.policy = policy
        self.gate = TrafficGate(policy)
        self.requests = 0
        self.stopped: str | None = None
        self._pending: list[tuple[str, str | None]] = []
        self._watched_hosts: set[str] = set()
        self._pages = set()

    async def before_action(self, page=None, *, url: str | None = None):
        await self.check()
        if self.requests >= self.policy.max_requests:
            raise CollectionStopped(f"[collection] 已达到单次任务 {self.policy.max_requests} 次导航/API/主动翻页操作预算，请分批采集")
        target = url or (page.url if page else "")
        if host := host_key(target):
            self._watched_hosts.add(host)
        await self.gate.wait(target)
        # 等待节流时页面可能刚收到拒绝响应，发起下一个请求前再确认。
        await self.check()
        self.requests += 1

    async def check_response(self, response):
        if response is None:
            return
        status = response.status
        if status not in (401, 403, 429, 503):
            return
        host = host_key(response.url)
        message = f"[collection] {host} 返回 HTTP {status}，已停止采集；请检查登录态/站点访问限制后再试"
        self.stopped = message
        headers = response.headers
        await self.gate.cooldown(response.url, headers.get("retry-after"))
        raise CollectionStopped(message)

    def _on_response(self, response):
        if response.status not in (401, 403, 429, 503):
            return
        request = response.request
        # 不因第三方埋点/广告失败中断业务，也不拦截资源请求或关闭缓存。
        if host_key(response.url) not in self._watched_hosts or request.resource_type not in ("document", "xhr", "fetch"):
            return
        self.stopped = f"[collection] {host_key(response.url)} 返回 HTTP {response.status}，已停止采集；请检查登录态/站点访问限制后再试"

        self._pending.append((response.url, response.headers.get("retry-after")))

    async def check(self, page=None):
        if self._pending:
            pending, self._pending = self._pending, []
            for url, retry_after in pending:
                await self.gate.cooldown(url, retry_after)
        if self.stopped:
            raise CollectionStopped(self.stopped)
        if page is not None and not page.is_closed():
            title = (await page.title()).strip().lower()
            challenge_titles = ("just a moment", "verify you are human", "access denied", "人机验证", "安全验证", "访问验证")
            if any(marker in title for marker in challenge_titles):
                self.stopped = f"[collection] {host_key(page.url)} 出现验证/拒绝访问页面，已停止；请人工处理后重新采集"
                await self.gate.cooldown(page.url)
                raise CollectionStopped(self.stopped)

    def attach_page(self, page):
        if page in self._pages:
            return
        self._pages.add(page)

        def wrap(original, navigation: bool):
            @wraps(original)
            async def guarded(*args, **kwargs):
                url = (args[0] if args else kwargs.get("url", "")) if navigation else page.url
                await self.before_action(page, url=url)
                # 明确指定 load/networkidle 的老脚本保留其选择；默认不等待广告长连接。
                if kwargs.get("wait_until") is None:
                    kwargs["wait_until"] = "domcontentloaded"
                response = await original(*args, **kwargs)
                await self.check_response(response)
                await self.check(page)
                return response
            return guarded

        for name in ("goto", "reload", "go_back", "go_forward"):
            setattr(page, name, wrap(getattr(page, name), name == "goto"))

    def attach(self):
        self.context.on("page", self.attach_page)
        self.context.on("response", self._on_response)
        for page in self.context.pages:
            self.attach_page(page)

    async def fetch_json(self, url: str, *, params: dict | None = None):
        """仅 GET；沿用当前 context 的 Cookie/Headers；不重试、不自动跨站跳转。"""
        await self.before_action(url=url)
        response = await self.context.request.get(url, params=params, max_redirects=0, max_retries=0)
        try:
            await self.check_response(response)
            if not response.ok:
                raise CollectionStopped(f"[collection] API 返回 HTTP {response.status}；未自动重试")
            return await response.json()
        finally:
            await response.dispose()

    @staticmethod
    def unique_urls(urls: list[str], base_url: str) -> list[str]:
        result = dict.fromkeys(urldefrag(urljoin(base_url, url))[0] for url in urls)
        return [url for url in result if host_key(url)]

    async def finish(self, page=None):
        await self.check(page)
        print(f"[collection] completed: {self.requests}/{self.policy.max_requests} 次主动操作")


async def create_collection_context(browser, policy: CollectionPolicy, *, headers=None, cookies=None, local_storage=None, start_url="", timeout=60000):
    """探索、试跑、正式执行、录制使用同一首屏登录态初始化顺序。"""
    context = await browser.new_context(extra_http_headers=headers or None)
    try:
        if cookies:
            await context.add_cookies(cookies)
        if local_storage and host_key(start_url):
            parsed = urlsplit(start_url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            await context.add_init_script(
                "if (location.origin === " + json.dumps(origin) + ") { for (const [k,v] of Object.entries(" + json.dumps(local_storage) + ")) localStorage.setItem(k,v); }"
            )
        context.set_default_timeout(timeout)
        runtime = CollectionRuntime(context, policy)
        runtime.attach()
        return context, runtime
    except BaseException:
        await context.close()
        raise
