from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import init_db
from app.config import settings
from app.routers import (
    scripts,
    flows,
    executions,
    skills,
    global_variables,
    recordings,
    datasources,
    data_views,
    workspace,
    code,
    mcp as mcp_api,
    requirements,
    modules,
    test_cases,
)
from app.websocket import manager
from app.services.datasource_query_service import connection_manager
from app.mcp import mcp, mount_mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with mcp.session_manager.run():
        yield
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

app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(flows.router, prefix="/api/flows", tags=["flows"])
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
app.include_router(requirements.router, prefix="/api/requirements", tags=["requirements"])
app.include_router(modules.router, prefix="/api/modules", tags=["modules"])
app.include_router(test_cases.router, prefix="/api/test-cases", tags=["test-cases"])

app.mount("/storage", StaticFiles(directory=settings.storage_dir), name="storage")


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.websocket("/api/ws/executions/{execution_id}")
async def execution_websocket(websocket: WebSocket, execution_id: int):
    await manager.connect(execution_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(execution_id, websocket)


# MCP 端点挂载：必须在所有路由注册之后，"/" 挂载作为兜底，仅接住 /mcp
mount_mcp(app)
