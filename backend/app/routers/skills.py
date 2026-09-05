from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.skill import Skill
from app.schemas.skill import SkillOut, SkillCloneResponse
from app.services import skill_service

router = APIRouter()


async def _get_skill_or_404(db: AsyncSession, skill_id: int) -> Skill:
    skill = await skill_service.get_skill(db, skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.get("", response_model=list[SkillOut])
async def list_skills(db: AsyncSession = Depends(get_db)) -> Any:
    await skill_service.ensure_default_skills(db)
    return await skill_service.get_skills(db)


@router.get("/{skill_id}", response_model=SkillOut)
async def get_skill(skill_id: int, db: AsyncSession = Depends(get_db)) -> Any:
    return await _get_skill_or_404(db, skill_id)


@router.post("/{skill_id}/clone", response_model=SkillCloneResponse)
async def clone_skill(skill_id: int, db: AsyncSession = Depends(get_db)) -> Any:
    skill = await _get_skill_or_404(db, skill_id)
    return SkillCloneResponse(
        prompt_template=skill.prompt_template,
        example_code=skill.example_code,
        example_inputs=skill.example_inputs,
        example_outputs=skill.example_outputs,
    )
