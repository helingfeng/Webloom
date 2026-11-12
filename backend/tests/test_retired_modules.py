"""模块移除后的边界：不注册旧接口、不创建旧表、不阻塞当前脚本空间。"""

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from app.main import app
from app.database import Base
from app.worker import WorkerSettings
from app.schemas.workspace import WorkspaceCreate
from app.schemas.script import ScriptCreate
from app.services import workspace_service, script_service


def test_retired_routes_and_models_are_removed():
    retired = ("/api/flows", "/api/test-cases", "/api/requirements", "/api/modules")
    paths = app.openapi()["paths"]
    assert not any(path.startswith(retired) for path in paths)
    client = TestClient(app)
    for path in retired:
        assert client.get(path).status_code == 404
    assert (
        not {"flows", "test_cases", "requirements", "modules"}
        & Base.metadata.tables.keys()
    )
    assert [f.name for f in WorkerSettings.functions] == ["run_script_execution"]


async def test_archived_tables_do_not_block_workspace_deletion(db):
    workspace = await workspace_service.create_workspace(
        db, WorkspaceCreate(name="归档空间")
    )
    # 模拟旧数据库中保留的归档数据；模块删除不能 DROP 或改写它们。
    await db.execute(
        text("CREATE TABLE flows (id INTEGER PRIMARY KEY, workspace_id INTEGER)")
    )
    await db.execute(
        text("INSERT INTO flows VALUES (1, :workspace_id)"),
        {"workspace_id": workspace.id},
    )
    await db.commit()
    await workspace_service.delete_workspace(db, workspace)
    assert await db.scalar(text("SELECT COUNT(*) FROM flows")) == 1


async def test_workspace_with_script_is_still_protected(db):
    workspace = await workspace_service.create_workspace(
        db, WorkspaceCreate(name="采集空间")
    )
    await script_service.create_script(
        db, ScriptCreate(workspace_id=workspace.id, name="保留的脚本", code="pass")
    )
    with pytest.raises(ValueError, match="脚本"):
        await workspace_service.delete_workspace(db, workspace)
