import asyncio
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, AsyncSessionLocal
from app.models.flow import Flow
from app.models.execution import Execution
from app.schemas.flow import FlowCreate, FlowOut, FlowUpdate, FlowRunRequest
from app.services import flow_service

router = APIRouter()


async def _get_flow_or_404(db: AsyncSession, flow_id: int) -> Flow:
    flow = await flow_service.get_flow(db, flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")
    return flow


@router.get("", response_model=list[FlowOut])
async def list_flows(
    skip: int = 0,
    limit: int = 100,
    workspace_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await flow_service.get_flows(
        db, skip=skip, limit=limit, workspace_id=workspace_id
    )


@router.post("", response_model=FlowOut, status_code=201)
async def create_flow(flow_in: FlowCreate, db: AsyncSession = Depends(get_db)) -> Any:
    try:
        return await flow_service.create_flow(db, flow_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{flow_id}", response_model=FlowOut)
async def get_flow(flow_id: int, db: AsyncSession = Depends(get_db)) -> Any:
    return await _get_flow_or_404(db, flow_id)


@router.put("/{flow_id}", response_model=FlowOut)
async def update_flow(
    flow_id: int, flow_in: FlowUpdate, db: AsyncSession = Depends(get_db)
) -> Any:
    flow = await _get_flow_or_404(db, flow_id)
    try:
        return await flow_service.update_flow(db, flow, flow_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{flow_id}", status_code=204)
async def delete_flow(flow_id: int, db: AsyncSession = Depends(get_db)) -> None:
    flow = await _get_flow_or_404(db, flow_id)
    await flow_service.delete_flow(db, flow)


@router.post("/{flow_id}/run")
async def run_flow_endpoint(
    flow_id: int, request: FlowRunRequest, db: AsyncSession = Depends(get_db)
) -> Any:
    flow = await _get_flow_or_404(db, flow_id)
    global_inputs = request.global_inputs or {}

    execution = Execution(
        target_type="flow",
        target_id=flow.id,
        mode=request.mode,
        inputs=global_inputs,
        status="running",
        logs="",
        outputs={},
        started_at=datetime.now(),
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    async def _run_task():
        async with AsyncSessionLocal() as session:
            task_flow = await flow_service.get_flow(session, flow_id)
            if not task_flow:
                raise ValueError(f"Flow {flow_id} not found")
            await flow_service.execute_flow(
                session, task_flow, request.mode, global_inputs, execution.id
            )

    asyncio.create_task(_run_task())
    return {
        "execution_id": execution.id,
        "status": "running",
        "outputs": {},
        "logs": "",
    }
