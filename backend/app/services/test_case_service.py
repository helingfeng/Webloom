from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.requirement import Requirement
from app.models.module import Module
from app.models.test_case import TestCase
from app.schemas.test_case import (
    TestCaseCreate,
    TestCaseImportIn,
    TestCaseUpdate,
)
from app.services import module_service, requirement_service, workspace_service


async def _validate_belong(
    db: AsyncSession, requirement_id: int, module_id: int | None
) -> None:
    req = await requirement_service.get_requirement(db, requirement_id)
    if not req:
        raise ValueError(f"需求 {requirement_id} 不存在")
    if module_id is not None:
        module = await module_service.get_module(db, module_id)
        if not module:
            raise ValueError(f"模块 {module_id} 不存在")
        if module.requirement_id != requirement_id:
            raise ValueError("模块不属于该需求")


async def get_test_cases(
    db: AsyncSession,
    workspace_id: int | None = None,
    requirement_id: int | None = None,
    module_id: int | None = None,
    status: str | None = None,
) -> list[TestCase]:
    stmt = select(TestCase).order_by(TestCase.id)
    if requirement_id is not None:
        stmt = stmt.where(TestCase.requirement_id == requirement_id)
    elif workspace_id is not None:
        req_ids = await db.execute(
            select(Requirement.id).where(Requirement.workspace_id == workspace_id)
        )
        stmt = stmt.where(TestCase.requirement_id.in_(req_ids.scalars().all()))
    if module_id is not None:
        stmt = stmt.where(TestCase.module_id == module_id)
    if status is not None:
        stmt = stmt.where(TestCase.status == status)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_test_case(db: AsyncSession, case_id: int) -> TestCase | None:
    result = await db.execute(select(TestCase).where(TestCase.id == case_id))
    return result.scalar_one_or_none()


async def create_test_case(db: AsyncSession, case_in: TestCaseCreate) -> TestCase:
    await _validate_belong(db, case_in.requirement_id, case_in.module_id)
    case = TestCase(**case_in.model_dump())
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return case


async def update_test_case(
    db: AsyncSession, case: TestCase, case_in: TestCaseUpdate
) -> TestCase:
    await _validate_belong(db, case_in.requirement_id, case_in.module_id)
    for key, value in case_in.model_dump().items():
        setattr(case, key, value)
    await db.commit()
    await db.refresh(case)
    return case


async def delete_test_case(db: AsyncSession, case: TestCase) -> None:
    await db.delete(case)
    await db.commit()


async def update_status(db: AsyncSession, case: TestCase, status: str) -> TestCase:
    case.status = status
    await db.commit()
    await db.refresh(case)
    return case


async def batch_update_status(db: AsyncSession, ids: list[int], status: str) -> int:
    """批量更新状态：id 有缺失则整体拒绝"""
    result = await db.execute(select(TestCase.id).where(TestCase.id.in_(ids)))
    existing = set(result.scalars().all())
    missing = [i for i in ids if i not in existing]
    if missing:
        raise ValueError(f"测试用例不存在：{', '.join(str(i) for i in missing)}")
    await db.execute(update(TestCase).where(TestCase.id.in_(ids)).values(status=status))
    await db.commit()
    return len(set(ids))


async def batch_delete(db: AsyncSession, ids: list[int]) -> int:
    """批量删除：id 有缺失则整体拒绝"""
    result = await db.execute(select(TestCase.id).where(TestCase.id.in_(ids)))
    existing = set(result.scalars().all())
    missing = [i for i in ids if i not in existing]
    if missing:
        raise ValueError(f"测试用例不存在：{', '.join(str(i) for i in missing)}")
    unique_ids = list(existing)
    await db.execute(delete(TestCase).where(TestCase.id.in_(unique_ids)))
    await db.commit()
    return len(unique_ids)


async def import_test_cases(db: AsyncSession, payload: TestCaseImportIn) -> dict:
    """从 MD 解析结果导入：模块按名复用，用例追加；整体一次提交"""
    ws = await workspace_service.get_workspace(db, payload.workspace_id)
    if not ws:
        raise ValueError(f"项目空间 {payload.workspace_id} 不存在")

    total_cases = len(payload.cases) + sum(len(m.cases) for m in payload.modules)
    if total_cases == 0:
        raise ValueError("导入内容为空：未解析到任何测试用例")

    if payload.requirement_id is not None:
        req = await requirement_service.get_requirement(db, payload.requirement_id)
        if not req:
            raise ValueError(f"需求 {payload.requirement_id} 不存在")
    else:
        name = payload.requirement_name.strip()
        if not name:
            raise ValueError("未指定需求时，必须提供需求名称")
        req = Requirement(workspace_id=payload.workspace_id, name=name)
        db.add(req)
        await db.flush()

    module_count = 0
    for module_in in payload.modules:
        result = await db.execute(
            select(Module).where(
                Module.requirement_id == req.id, Module.name == module_in.name
            )
        )
        module = result.scalars().first()
        if not module:
            module = Module(requirement_id=req.id, name=module_in.name)
            db.add(module)
            await db.flush()
            module_count += 1
        for case_in in module_in.cases:
            db.add(
                TestCase(
                    requirement_id=req.id,
                    module_id=module.id,
                    **case_in.model_dump(),
                )
            )

    for case_in in payload.cases:
        db.add(TestCase(requirement_id=req.id, module_id=None, **case_in.model_dump()))

    await db.commit()
    return {
        "requirement_id": req.id,
        "requirement_name": req.name,
        "module_count": module_count,
        "case_count": total_cases,
    }
