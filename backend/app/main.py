import asyncio
from contextlib import asynccontextmanager, suppress
from app.services.browser_authoring_service import browser_sessions
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import init_db
from app.config import settings
from app.routers import (
    scripts,
    executions,
    skills,
    global_variables,
    recordings,
    datasources,
    data_views,
    workspace,
    code,
    mcp as mcp_api,
    open_platform,
)
from app.routers.collectors import (
    admin_router as collectors_router,
    tasks_router as collector_tasks_router,
)
from app.services import log_stream_service
from app.services.browser_setting_service import get_browser_options
from app.services.datasource_query_service import connection_manager
from app.task_queue import close_pool, get_pool, queue_stats
from app.task_queue import QueueUnavailableError
from app.mcp import mcp, mount_mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 预热任务队列连接；Redis 未启动时 API 照常服务（run 接口返回 503，health 暴露状态）
    try:
        await get_pool()
    except QueueUnavailableError:
        pass
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
    await connection_manager.dispose_all()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(collectors_router, prefix="/api/collectors", tags=["collectors"])
app.include_router(
    collector_tasks_router, prefix="/api/collector-tasks", tags=["collectors"]
)

app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(executions.router, prefix="/api/executions", tags=["executions"])
app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
app.include_router(
    global_variables.router, prefix="/api/global-variables", tags=["global-variables"]
)
app.include_router(recordings.router, prefix="/api/recordings", tags=["recordings"])
app.include_router(datasources.router, prefix="/api/datasources", tags=["datasources"])
app.include_router(data_views.router, prefix="/api/data-views", tags=["data-views"])
app.include_router(data_views.public_router, prefix="/api/data", tags=["data"])
app.include_router(workspace.router, prefix="/api/workspaces", tags=["workspaces"])
app.include_router(code.router, prefix="/api/code", tags=["code"])
app.include_router(mcp_api.router, prefix="/api/mcp", tags=["mcp"])
# 开放平台：应用凭证与调用日志管理 + 外部采集端点
app.include_router(
    open_platform.open_apps_router, prefix="/api/open-apps", tags=["open"]
)
app.include_router(
    open_platform.open_logs_router, prefix="/api/open-logs", tags=["open"]
)
app.include_router(open_platform.open_router, prefix="/open", tags=["open"])

app.mount("/storage", StaticFiles(directory=settings.storage_dir), name="storage")


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "queue": await queue_stats(),
        "browser": (await get_browser_options()).public_status(),
        "collection_policy": settings.collection_policy().public_status(),
    }


@app.websocket("/api/ws/executions/{execution_id}")
async def execution_websocket(websocket: WebSocket, execution_id: int):
    await log_stream_service.stream_execution_logs(websocket, execution_id)


# MCP 端点挂载：必须在所有路由注册之后，"/" 挂载作为兜底，仅接住 /mcp
mount_mcp(app)
