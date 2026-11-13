import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp import mcp
from app.config import settings
from app.database import get_db
from app.schemas.browser_setting import BrowserSettingOut, BrowserSettingUpdate
from app.services import browser_setting_service

router = APIRouter()


@router.get("/browser-settings", response_model=BrowserSettingOut)
async def browser_settings(db: AsyncSession = Depends(get_db)):
    return await browser_setting_service.get_browser_setting(db)


@router.put("/browser-settings", response_model=BrowserSettingOut)
async def update_browser_settings(
    payload: BrowserSettingUpdate, db: AsyncSession = Depends(get_db)
):
    try:
        return await browser_setting_service.update_browser_setting(
            db, payload.cloakbrowser_enabled
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status")
async def mcp_status(request: Request) -> Any:
    """MCP 服务状态：端点、协议、工具列表（取自真实注册）、客户端配置。"""
    tools = await mcp.list_tools()
    direct = str(request.base_url).rstrip("/") + "/mcp"
    parts = urlsplit(direct)
    proxied = urlunsplit(
        ("http", f"{parts.hostname or '127.0.0.1'}:5173", "/mcp", "", "")
    )
    return {
        "server_name": mcp.name,
        "browser": (await browser_setting_service.get_browser_options()).public_status(),
        "collection_policy": settings.collection_policy().public_status(),
        "transport": "streamable-http",
        "endpoint": {"direct": direct, "proxied": proxied},
        "tool_count": len(tools),
        "tools": [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema,
            }
            for t in tools
        ],
        "client_config": {
            "mcp_servers_json": {"mcpServers": {mcp.name: {"url": direct}}},
            "claude_cli_command": f"claude mcp add --transport http {mcp.name} {direct}",
            "trae_cli_command": (
                f"trae-cli mcp add-json {mcp.name} "
                f"'{json.dumps({"type": "http", "url": direct}, separators=(",", ":"))}'"
            ),
        },
    }
