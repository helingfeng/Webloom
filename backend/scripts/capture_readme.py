"""使用真实前端与隔离演示响应生成 README 截图，不写入平台或读取业务数据。

先启动前端，再在项目根目录运行：
backend/venv/bin/python backend/scripts/capture_readme.py
"""

import argparse
import asyncio
from pathlib import Path
import sys
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.mcp import mcp

ROOT = Path(__file__).resolve().parents[2]
STAMP = "2026-11-13T10:00:00"
BOOKS_URL = "https://books.toscrape.com/"
SCRIPT = {
    "id": 1, "workspace_id": 1, "name": "图书目录采集", "start_url": BOOKS_URL,
    "description": "批量采集当前页的图书名称、价格、库存状态与详情链接。",
    "inputs": [
        {"name": "url", "type": "string", "description": "图书列表页地址", "default": BOOKS_URL, "required": True},
        {"name": "limit", "type": "number", "description": "最多采集条数", "default": 20, "required": False},
    ],
    "outputs": [{"name": "items", "description": "图书名称、价格、库存状态与详情链接列表"}],
    "inherit_global": True, "headless": True, "run_mode": "manual",
    "created_at": STAMP, "updated_at": STAMP,
    "code": '''# 复用平台浏览器，按当前页批量读取，避免逐条访问详情。
await page.goto(START_URL, wait_until="domcontentloaded")
await page.locator("article.product_pod").first.wait_for()

limit = max(1, min(int(INPUTS.get("limit", 20)), 20))
OUTPUTS["items"] = await page.locator("article.product_pod").evaluate_all(
    """(cards, limit) => cards.slice(0, limit).map(card => ({
        title: card.querySelector("h3 a").title,
        price: card.querySelector(".price_color").textContent.trim(),
        availability: card.querySelector(".availability").textContent.trim(),
        url: card.querySelector("h3 a").href
    }))""",
    limit,
)
OUTPUTS["items"] = list({item["url"]: item for item in OUTPUTS["items"]}.values())
print(f"已采集 {len(OUTPUTS['items'])} 条图书数据")''',
}
COLLECTOR = {
    "id": 1, "name": "图书目录采集", "slug": "book-catalog", "script_id": 1,
    "description": SCRIPT["description"], "app_ids": [1], "enabled": True,
    "created_at": STAMP, "updated_at": STAMP,
}
CONTRACT = {
    "id": 1, "name": COLLECTOR["name"], "slug": "book-catalog",
    "description": SCRIPT["description"], "path": "/open/v1/collectors/book-catalog/runs",
    "input_schema": {"properties": {
        "url": {"type": "string", "description": "图书列表页地址", "default": BOOKS_URL},
        "limit": {"type": "number", "description": "最多采集条数", "default": 20},
    }, "required": ["url"]},
    "outputs": SCRIPT["outputs"], "example": {"inputs": {"url": BOOKS_URL, "limit": 20}, "wait_seconds": 0},
    "auth": "Bearer <APP_KEY>.<APP_SECRET>",
}
ROWS = [
    {"title": title, "price": price, "availability": "In stock", "url": f"https://example.com/books/{index}"}
    for index, (title, price) in enumerate([
        ("向数据出发", "£18.00"), ("网页采集实践", "£24.50"),
        ("异步 Python 入门", "£32.00"), ("结构化数据之美", "£21.80"),
        ("从提示词到 API", "£28.60"), ("可复用的采集脚本", "£19.90"),
    ], start=1)
]
TASK = {
    "task_id": 1, "execution_id": 1001, "collector_id": 1,
    "collector_name": COLLECTOR["name"], "app_id": 1, "status": "success", "finished": True,
    "error": None, "created_at": STAMP, "finished_at": "2026-11-13T10:00:08",
    "result_url": "/open/v1/tasks/1001", "data_url": "/open/v1/tasks/1001/data",
    "inputs": CONTRACT["example"]["inputs"], "outputs": {"items": ROWS},
    "logs": "[browser] playwright\n已打开图书列表页\n已采集 6 条图书数据\n[collection] completed: 1/50 次主动操作\n",
}


async def capture(base_url: str, output: Path):
    origin = urlsplit(base_url)
    tools = await mcp.list_tools()
    mcp_status = {
        "server_name": mcp.name, "transport": "streamable-http",
        "endpoint": {"direct": "http://127.0.0.1:8000/mcp", "proxied": "http://127.0.0.1:5173/mcp"},
        "tool_count": len(tools), "tools": [{"name": t.name, "description": t.description, "input_schema": t.inputSchema} for t in tools],
        "client_config": {
            "mcp_servers_json": {"mcpServers": {mcp.name: {"url": "http://127.0.0.1:8000/mcp"}}},
            "claude_cli_command": f"claude mcp add --transport http {mcp.name} http://127.0.0.1:8000/mcp",
            "trae_cli_command": f"trae-cli mcp add-json {mcp.name} '{{\"type\":\"http\",\"url\":\"http://127.0.0.1:8000/mcp\"}}'",
        },
        "collection_policy": {"min_interval_seconds": 2, "cooldown_seconds": 300, "max_requests": 50, "max_wait_seconds": 30},
    }
    browser_status = {
        "engine": "playwright", "cloakbrowser_enabled": False, "ready": True,
        "cloakbrowser_installed": True, "license_configured": False, "humanize": False,
        "proxy_configured": False, "message": "已使用标准 Playwright；可在后台启用 CloakBrowser",
    }
    mcp_status["browser"] = browser_status
    pages = lambda items: {"items": items, "total": len(items)}
    fixtures = {
        "/api/workspaces": [{"id": 1, "name": "演示空间", "description": "README 界面示例", "created_at": STAMP, "updated_at": STAMP}],
        "/api/scripts": [SCRIPT], "/api/scripts/1": SCRIPT,
        "/api/executions": pages([]), "/api/mcp/status": mcp_status,
        "/api/mcp/browser-settings": browser_status,
        "/api/collectors": pages([COLLECTOR]), "/api/collectors/1/contract": CONTRACT,
        "/api/collector-tasks": pages([TASK]), "/api/collector-tasks/1001": TASK,
        "/api/open-apps": pages([{"id": 1, "name": "示例调用应用", "app_key": "fk_demo", "enabled": True, "description": "演示应用", "created_at": STAMP, "updated_at": STAMP}]),
        "/open/v1/collectors": pages([CONTRACT]), "/open/v1/tasks": pages([TASK]), "/open/v1/tasks/1001": TASK,
    }
    problems = []

    async def handle(route):
        url = urlsplit(route.request.url)
        if url.scheme not in ("http", "https"):
            await route.continue_()
        elif (url.scheme, url.netloc) != (origin.scheme, origin.netloc):
            problems.append("意外的外部请求：" + url.netloc)
            await route.abort()
        elif url.path.startswith(("/api/", "/open/")):
            if route.request.method == "GET" and url.path in fixtures:
                await route.fulfill(json=fixtures[url.path])
            elif route.request.method == "POST" and url.path == "/api/code/validate":
                await route.fulfill(json={"errors": []})
            else:
                problems.append(f"未定义演示响应：{route.request.method} {url.path}")
                await route.fulfill(status=501, json={"detail": "截图模式禁止访问真实 API"})
        else:
            await route.continue_()

    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=1, locale="zh-CN", timezone_id="Asia/Shanghai", color_scheme="light", reduced_motion="reduce")
            await context.route("**/*", handle)
            page = await context.new_page()
            page.on("pageerror", lambda error: problems.append(str(error)))

            async def go(path):
                await page.goto(base_url + path, wait_until="networkidle")
                await page.evaluate("document.fonts.ready")

            async def save(name):
                await page.screenshot(path=str(output / name), animations="disabled", caret="hide")
                print(name)

            await page.set_viewport_size({"width": 1440, "height": 1120})
            await go("/mcp")
            await page.get_by_role("heading", name="MCP 服务", exact=True).wait_for()
            await page.get_by_text("webloom", exact=True).first.wait_for()
            await save("01-mcp-connection.png")

            await page.set_viewport_size({"width": 1440, "height": 960})
            await go("/scripts/1")
            await page.locator(".monaco-editor .view-lines").wait_for()
            await page.get_by_text("已采集", exact=False).first.wait_for()
            await save("02-script-editor.png")

            await go("/collectors?script_id=1")
            dialog = page.get_by_role("dialog", name="发布采集接口", exact=True)
            await dialog.wait_for()
            await dialog.locator(".el-form-item").filter(has_text="接口标识").locator("input").fill("book-catalog")
            await dialog.locator(".el-form-item").filter(has_text="接口说明").locator("textarea").fill(SCRIPT["description"])
            await dialog.locator(".el-form-item").filter(has_text="授权应用").locator(".el-select").click()
            await page.get_by_role("option", name="示例调用应用", exact=True).click()
            await dialog.get_by_text("发布采集接口", exact=True).click()
            await save("03-publish-collector.png")

            await go("/collector-tasks?execution_id=1001")
            await page.get_by_role("dialog", name="采集结果", exact=True).wait_for()
            await page.get_by_text("向数据出发", exact=True).wait_for()
            await page.get_by_text("执行日志", exact=True).click()
            await page.get_by_text("已打开图书列表页", exact=False).wait_for()
            await page.wait_for_function("""() => {
                const element = document.querySelector('.el-collapse-item.is-active .el-collapse-item__wrap');
                return element && element.getBoundingClientRect().height >= element.scrollHeight - 1;
            }""")
            await save("04-collection-results.png")

            await go("/collection-portal")
            await page.get_by_placeholder("fkxxxxxxxx.应用密钥").fill("fk_demo.demo-secret")
            await page.get_by_role("button", name="连接并查看可用接口", exact=True).click()
            await page.get_by_role("button", name="查看结果", exact=True).first.click()
            await page.get_by_text("向数据出发", exact=True).wait_for()
            await save("05-calling-portal.png")
            if problems:
                raise RuntimeError("\n".join(problems))
        finally:
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5173")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/images")
    args = parser.parse_args()
    asyncio.run(capture(args.base_url.rstrip("/"), args.output))
