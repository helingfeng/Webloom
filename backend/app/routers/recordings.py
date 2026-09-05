from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services import recording_service
from app.services.recording_service import RecordingSession

router = APIRouter()


class RecordingStartRequest(BaseModel):
    start_url: str = ""


def _session_out(session: RecordingSession) -> dict:
    return {
        "recording_id": session.id,
        "status": session.status,
        "start_url": session.start_url,
        "raw_code": session.raw_code,
        "code": session.code,
        "detected_start_url": session.detected_start_url,
        "error": session.error,
        "applied_globals": session.applied_globals,
    }


@router.post("/start")
async def start_recording(request: RecordingStartRequest) -> Any:
    session = await recording_service.start_recording(request.start_url)
    return _session_out(session)


@router.get("/{recording_id}")
async def get_recording(recording_id: int) -> Any:
    session = await recording_service.get_recording(recording_id)
    if not session:
        raise HTTPException(status_code=404, detail="Recording not found")
    return _session_out(session)


@router.post("/{recording_id}/stop")
async def stop_recording(recording_id: int) -> Any:
    session = await recording_service.get_recording(recording_id)
    if not session:
        raise HTTPException(status_code=404, detail="Recording not found")
    session = await recording_service.stop_recording(session)
    return _session_out(session)
