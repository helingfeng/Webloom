"""MCP 服务模块（脚本管理）。

FastMCP 1.x 无 mount() 方法，采用官方 FastAPI 手动集成模式：
- `streamable_http_app()` 创建子应用（同时惰性创建 session_manager），子应用内部路由为 /mcp；
- 主应用挂根路径，最终端点即 /mcp（切勿挂 /mcp，会变成 /mcp/mcp）；
- 主应用 lifespan 需包裹 `async with mcp.session_manager.run()`（见 main.py）。
"""

from fastapi import FastAPI

from app.mcp.server import mcp

# 先创建子应用：session_manager 在此惰性生成，早于 lifespan 使用
_streamable_app = mcp.streamable_http_app()


def mount_mcp(app: FastAPI) -> None:
    """把 MCP 端点挂载到 /mcp（streamable http）。需在所有路由注册之后调用。"""
    app.mount("/", _streamable_app)


__all__ = ["mcp", "mount_mcp"]
