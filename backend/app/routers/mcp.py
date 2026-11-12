import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Request

from app.mcp import mcp

router = APIRouter()


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
            "mcp_servers_json": {
                "mcpServers": {"fishcode-scripts": {"url": direct}}
            },
            "claude_cli_command": f"claude mcp add --transport http fishcode-scripts {direct}",
            "trae_cli_command": (
                "trae-cli mcp add-json fishcode-scripts "
                f"'{json.dumps({"type": "http", "url": direct}, separators=(",", ":"))}'"
            ),
        },
    }
