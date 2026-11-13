import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from email.utils import format_datetime
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.engine.collection import (
    CollectionPolicy, CollectionRuntime, CollectionStopped, TrafficGate,
    create_collection_context, retry_after_seconds,
)


def test_retry_after_handles_seconds_dates_and_invalid_values():
    now = 1800000000
    date = format_datetime(datetime.fromtimestamp(now + 720, timezone.utc), usegmt=True)
    assert retry_after_seconds("90", now) == 90
    assert retry_after_seconds(date, now) == 720
    for value in (None, "oops", "nan", "inf", "-1"):
        assert retry_after_seconds(value, now) == 0


def test_stop_reason_remains_visible_in_execution_error_summary():
    from app.engine.runner import _extract_error_line

    log = "Traceback (most recent call last):\napp.engine.collection.CollectionStopped: [collection] example.test 返回 HTTP 429，已停止采集\n"
    assert "HTTP 429" in _extract_error_line(log)


async def test_independent_gates_reserve_one_slot_atomically(tmp_path):
    policy = CollectionPolicy(str(tmp_path / "traffic.db"), min_interval_seconds=5)
    gates = [TrafficGate(policy) for _ in range(8)]
    delays = await asyncio.gather(*(asyncio.to_thread(gate._transaction, "example.test") for gate in gates))
    assert sum(delay == 0 for delay in delays) == 1
    assert all(delay == 0 or 0 < delay <= 5 for delay in delays)
    # 不同域互不阻塞，HTTP/HTTPS 同一域共享额度。
    assert gates[0]._transaction("another.test") == 0


async def test_cooldown_respects_longer_server_wait_and_does_not_leak_urls(tmp_path, monkeypatch):
    now = 1800000000
    monkeypatch.setattr("app.engine.collection.time.time", lambda: now)
    policy = CollectionPolicy(str(tmp_path / "traffic.db"), cooldown_seconds=30)
    await TrafficGate(policy).cooldown("https://example.test/private?token=hidden", "600")
    other = TrafficGate(policy)
    with pytest.raises(CollectionStopped, match="600 秒") as stopped:
        await other.wait("http://example.test/elsewhere")
    assert "hidden" not in str(stopped.value)
    # 更短的后续失败不能缩短既有冷却期。
    await other.cooldown("https://example.test", "1")
    with pytest.raises(CollectionStopped, match="600 秒"):
        await other.wait("https://example.test")


async def test_wait_has_bound_and_cancellation_does_not_reserve_future_slots(tmp_path):
    policy = CollectionPolicy(str(tmp_path / "traffic.db"), min_interval_seconds=1, max_wait_seconds=.01)
    gate = TrafficGate(policy)
    await gate.wait("https://example.test")
    with pytest.raises(CollectionStopped, match="排队超过预算"):
        await gate.wait("https://example.test")
    await gate.wait("https://another.test")
    task = asyncio.create_task(TrafficGate(replace(policy, max_wait_seconds=5)).wait("https://example.test"))
    await asyncio.sleep(.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert 0 < gate._transaction("example.test") <= 1


async def test_subprocess_cooldown_is_visible_in_parent(tmp_path):
    policy = CollectionPolicy(str(tmp_path / "traffic.db"))
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c",
        'import asyncio; from app.engine.collection import CollectionPolicy, TrafficGate; asyncio.run(TrafficGate(CollectionPolicy.from_env()).cooldown("https://example.test", "900"))',
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(Path(__file__).resolve().parents[1]), **policy.to_env()},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, error = await process.communicate()
    assert process.returncode == 0, error.decode()
    with pytest.raises(CollectionStopped, match="冷却期"):
        await TrafficGate(policy).wait("https://example.test")


def test_unique_urls_preserves_query_and_drops_fragments():
    assert CollectionRuntime.unique_urls(["/a#one", "/a#two", "/a?q=1", "javascript:bad()", "/a?q=1"], "https://example.test/list") == ["https://example.test/a", "https://example.test/a?q=1"]


@pytest_asyncio.fixture
async def runtime(tmp_path):
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context, collect = await create_collection_context(
                browser, CollectionPolicy(str(tmp_path / "traffic.db"), min_interval_seconds=.01, cooldown_seconds=30, max_requests=4),
            )
            yield browser, context, collect
        finally:
            await browser.close()


async def test_native_navigation_stops_on_429_and_new_context_obeys_cooldown(runtime):
    browser, context, collect = runtime
    seen = []

    async def limited(route):
        seen.append(route.request.url)
        await route.fulfill(status=429, headers={"Retry-After": "900"}, body="limited")

    await context.route("**/*", limited)
    page = await context.new_page()
    with pytest.raises(CollectionStopped, match="HTTP 429"):
        await page.goto("https://example.test/page?token=hidden")
    with pytest.raises(CollectionStopped):
        await page.reload()
    assert len(seen) == 1
    other_context, other = await create_collection_context(browser, collect.policy)
    with pytest.raises(CollectionStopped, match="冷却期"):
        await (await other_context.new_page()).goto("https://example.test/another")
    assert other.requests == 0


async def test_challenge_page_is_not_success_and_navigation_budget_is_shared(runtime):
    _, context, collect = runtime
    await context.route("**/*", lambda route: route.fulfill(content_type="text/html; charset=utf-8", body="<title>安全验证</title>"))
    with pytest.raises(CollectionStopped, match="验证/拒绝访问"):
        await (await context.new_page()).goto("https://challenge.test")
    assert collect.stopped


async def test_popup_pages_are_guarded_and_old_navigation_options_preserved(runtime):
    _, context, collect = runtime
    await context.route("**/*", lambda route: route.fulfill(content_type="text/html", body="<title>ok</title>"))
    page = await context.new_page()
    await page.goto("https://example.test", wait_until="load")
    second = await context.new_page()
    await second.goto("https://example.test/second")
    await page.reload()
    await collect.before_action(page)
    with pytest.raises(CollectionStopped, match="预算"):
        await second.goto("https://example.test/never")
    assert collect.requests == 4
    await collect.finish(second)


@pytest_asyncio.fixture
async def api_server():
    seen = []

    async def handle(reader, writer):
        try:
            raw = (await reader.readuntil(b"\r\n\r\n")).decode()
            path = raw.split(" ")[1]
            seen.append(path)
            if path == "/limited":
                status, headers, body = "429 Too Many Requests", "Retry-After: 900\r\n", b"limited"
            elif path == "/redirect":
                status, headers, body = "302 Found", "Location: /data\r\n", b""
            else:
                status, headers = "200 OK", "Content-Type: application/json\r\nSet-Cookie: server=shared; Path=/\r\n"
                body = json.dumps({"cookie_received": "sid=input" in raw, "header_received": "test-header" in raw}).encode()
            writer.write(f"HTTP/1.1 {status}\r\n{headers}Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    async with server:
        yield f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}", seen


async def test_json_get_shares_auth_has_no_redirect_or_retry_and_counts_budget(runtime, api_server):
    _, context, collect = runtime
    base, seen = api_server
    await context.add_cookies([{"name": "sid", "value": "input", "url": base}])
    await context.set_extra_http_headers({"X-Test": "test-header"})
    assert await collect.fetch_json(base + "/data") == {"cookie_received": True, "header_received": True}
    assert any(c["name"] == "server" for c in await context.cookies(base))
    with pytest.raises(CollectionStopped, match="HTTP 302"):
        await collect.fetch_json(base + "/redirect")
    assert seen == ["/data", "/redirect"]
    with pytest.raises(CollectionStopped, match="HTTP 429"):
        await collect.fetch_json(base + "/limited")
    with pytest.raises(CollectionStopped):
        await collect.fetch_json(base + "/data")
    assert seen == ["/data", "/redirect", "/limited"]


async def test_third_party_failure_does_not_stop_collection_but_same_site_xhr_does(runtime):
    _, _, collect = runtime
    await collect.before_action(url="https://example.test")
    response = SimpleNamespace(status=403, url="https://ads.test/pixel", headers={}, request=SimpleNamespace(resource_type="fetch"))
    collect._on_response(response)
    await collect.check()
    response.url = "https://example.test/api"
    collect._on_response(response)
    with pytest.raises(CollectionStopped, match="HTTP 403"):
        await collect.check()
