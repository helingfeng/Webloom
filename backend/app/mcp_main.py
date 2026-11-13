"""最小 MCP 进程：不挂载管理 REST、前端、开放平台，不连接 Redis。"""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.database import engine, init_db
from app.config import settings
from app.mcp import mcp, mount_mcp
from app.services.browser_authoring_service import browser_sessions
from app.task_queue import close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    sweeper = asyncio.create_task(browser_sessions.sweep())
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        sweeper.cancel()
        with suppress(asyncio.CancelledError):
            await sweeper
        await browser_sessions.close_all()
        await close_pool()
        await engine.dispose()


app = FastAPI(title=f"{settings.app_name} MCP", lifespan=lifespan)
mount_mcp(app)
