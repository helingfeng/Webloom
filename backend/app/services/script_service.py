from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.engine.runner import validate_script_code
from app.models.script import Script
from app.models.collector import Collector
from app.schemas.script import ScriptCreate, ScriptUpdate
from app.services import workspace_service


async def get_scripts(
    db: AsyncSession, skip: int = 0, limit: int = 100, workspace_id: int | None = None
) -> list[Script]:
    stmt = select(Script)
    if workspace_id is not None:
        stmt = stmt.where(Script.workspace_id == workspace_id)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return result.scalars().all()


async def get_script(db: AsyncSession, script_id: int) -> Script | None:
    result = await db.execute(select(Script).where(Script.id == script_id))
    return result.scalar_one_or_none()


async def _validate_workspace(db: AsyncSession, workspace_id: int) -> None:
    ws = await workspace_service.get_workspace(db, workspace_id)
    if not ws:
        raise ValueError(f"项目空间 {workspace_id} 不存在")


async def create_script(db: AsyncSession, script_in: ScriptCreate) -> Script:
    if script_in.code.strip():
        validate_script_code(script_in.code)
    await _validate_workspace(db, script_in.workspace_id)
    script = Script(**script_in.model_dump())
    db.add(script)
    await db.commit()
    await db.refresh(script)
    return script


async def update_script(
    db: AsyncSession, script: Script, script_in: ScriptUpdate
) -> Script:
    if script_in.code.strip():
        validate_script_code(script_in.code)
    if script_in.workspace_id != script.workspace_id:
        await _validate_workspace(db, script_in.workspace_id)
    for key, value in script_in.model_dump().items():
        setattr(script, key, value)
    await db.commit()
    await db.refresh(script)
    return script


async def delete_script(db: AsyncSession, script: Script) -> None:
    await _ensure_not_published(db, [script.id])
    await db.delete(script)
    await db.commit()


async def batch_delete(db: AsyncSession, ids: list[int]) -> int:
    result = await db.execute(select(Script.id).where(Script.id.in_(ids)))
    existing = set(result.scalars().all())
    missing = [i for i in ids if i not in existing]
    if missing:
        raise ValueError(f"脚本不存在：{', '.join(str(i) for i in missing)}")
    await _ensure_not_published(db, list(existing))
    unique_ids = list(existing)
    await db.execute(delete(Script).where(Script.id.in_(unique_ids)))
    await db.commit()
    return len(unique_ids)


async def _ensure_not_published(db: AsyncSession, ids: list[int]) -> None:
    bound = (
        await db.execute(
            select(Collector.name)
            .where(Collector.script_id.in_(ids), Collector.archived.is_(False))
            .limit(1)
        )
    ).scalar_one_or_none()
    if bound:
        raise ValueError(f"脚本已绑定采集接口「{bound}」，请先在接口中更换脚本")
