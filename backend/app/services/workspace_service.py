from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.workspace import Workspace
from app.models.script import Script
from app.models.flow import Flow
from app.models.requirement import Requirement
from app.schemas.workspace import WorkspaceCreate, WorkspaceUpdate


async def get_workspaces(db: AsyncSession) -> list[Workspace]:
    result = await db.execute(select(Workspace).order_by(Workspace.id))
    return result.scalars().all()


async def get_workspace(db: AsyncSession, ws_id: int) -> Workspace | None:
    result = await db.execute(select(Workspace).where(Workspace.id == ws_id))
    return result.scalar_one_or_none()


async def _validate_name(db: AsyncSession, name: str, exclude_id: int | None = None) -> None:
    result = await db.execute(select(Workspace).where(Workspace.name == name))
    existing = result.scalar_one_or_none()
    if existing is not None and existing.id != exclude_id:
        raise ValueError(f"项目空间 '{name}' 已存在")


async def create_workspace(db: AsyncSession, ws_in: WorkspaceCreate) -> Workspace:
    await _validate_name(db, ws_in.name)
    ws = Workspace(**ws_in.model_dump())
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return ws


async def update_workspace(
    db: AsyncSession, ws: Workspace, ws_in: WorkspaceUpdate
) -> Workspace:
    data = ws_in.model_dump(exclude_unset=True)
    if data.get("name") and data["name"] != ws.name:
        await _validate_name(db, data["name"], exclude_id=ws.id)
    for key, value in data.items():
        setattr(ws, key, value)
    await db.commit()
    await db.refresh(ws)
    return ws


async def delete_workspace(db: AsyncSession, ws: Workspace) -> None:
    """删除前校验：其下有脚本、流程或需求则拒绝（提示先清空）"""
    script_count = await db.scalar(
        select(func.count()).select_from(Script).where(Script.workspace_id == ws.id)
    )
    flow_count = await db.scalar(
        select(func.count()).select_from(Flow).where(Flow.workspace_id == ws.id)
    )
    req_count = await db.scalar(
        select(func.count())
        .select_from(Requirement)
        .where(Requirement.workspace_id == ws.id)
    )
    if script_count or flow_count or req_count:
        raise ValueError(
            f"该空间下仍有 {script_count} 个脚本、{flow_count} 个流程、"
            f"{req_count} 个需求，请先移动或删除"
        )
    await db.delete(ws)
    await db.commit()
