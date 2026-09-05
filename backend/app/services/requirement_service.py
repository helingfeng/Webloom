from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.requirement import Requirement
from app.models.module import Module
from app.models.test_case import TestCase
from app.schemas.requirement import RequirementCreate, RequirementUpdate
from app.services import workspace_service


async def get_requirements(
    db: AsyncSession, workspace_id: int | None = None
) -> list[Requirement]:
    stmt = select(Requirement).order_by(Requirement.id)
    if workspace_id is not None:
        stmt = stmt.where(Requirement.workspace_id == workspace_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_requirement(db: AsyncSession, req_id: int) -> Requirement | None:
    result = await db.execute(select(Requirement).where(Requirement.id == req_id))
    return result.scalar_one_or_none()


async def create_requirement(db: AsyncSession, req_in: RequirementCreate) -> Requirement:
    ws = await workspace_service.get_workspace(db, req_in.workspace_id)
    if not ws:
        raise ValueError(f"项目空间 {req_in.workspace_id} 不存在")
    req = Requirement(**req_in.model_dump())
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


async def update_requirement(
    db: AsyncSession, req: Requirement, req_in: RequirementUpdate
) -> Requirement:
    ws = await workspace_service.get_workspace(db, req_in.workspace_id)
    if not ws:
        raise ValueError(f"项目空间 {req_in.workspace_id} 不存在")
    for key, value in req_in.model_dump().items():
        setattr(req, key, value)
    await db.commit()
    await db.refresh(req)
    return req


async def delete_requirement(db: AsyncSession, req: Requirement) -> None:
    """删除前校验：其下有模块或用例则拒绝（提示先清空）"""
    module_count = await db.scalar(
        select(func.count()).select_from(Module).where(Module.requirement_id == req.id)
    )
    case_count = await db.scalar(
        select(func.count()).select_from(TestCase).where(TestCase.requirement_id == req.id)
    )
    if module_count or case_count:
        raise ValueError(
            f"该需求下仍有 {module_count} 个模块、{case_count} 个测试用例，请先删除"
        )
    await db.delete(req)
    await db.commit()
