from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.module import Module
from app.models.test_case import TestCase
from app.schemas.module import ModuleCreate, ModuleUpdate
from app.services import requirement_service


async def get_modules(db: AsyncSession, requirement_id: int | None = None) -> list[Module]:
    stmt = select(Module).order_by(Module.id)
    if requirement_id is not None:
        stmt = stmt.where(Module.requirement_id == requirement_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_module(db: AsyncSession, module_id: int) -> Module | None:
    result = await db.execute(select(Module).where(Module.id == module_id))
    return result.scalar_one_or_none()


async def create_module(db: AsyncSession, module_in: ModuleCreate) -> Module:
    req = await requirement_service.get_requirement(db, module_in.requirement_id)
    if not req:
        raise ValueError(f"需求 {module_in.requirement_id} 不存在")
    module = Module(**module_in.model_dump())
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


async def update_module(db: AsyncSession, module: Module, module_in: ModuleUpdate) -> Module:
    req = await requirement_service.get_requirement(db, module_in.requirement_id)
    if not req:
        raise ValueError(f"需求 {module_in.requirement_id} 不存在")
    for key, value in module_in.model_dump().items():
        setattr(module, key, value)
    await db.commit()
    await db.refresh(module)
    return module


async def delete_module(db: AsyncSession, module: Module) -> None:
    """删除前校验：其下有用例则拒绝（提示先清空）"""
    case_count = await db.scalar(
        select(func.count()).select_from(TestCase).where(TestCase.module_id == module.id)
    )
    if case_count:
        raise ValueError(f"该模块下仍有 {case_count} 个测试用例，请先删除或移动")
    await db.delete(module)
    await db.commit()
