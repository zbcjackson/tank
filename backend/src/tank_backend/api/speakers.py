"""REST API routes for speaker management (enrollment, listing, deletion)."""

from __future__ import annotations

import logging
import uuid

import numpy as np
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from .manager import SessionManager

logger = logging.getLogger("SpeakerRoutes")

router = APIRouter(prefix="/api/speakers", tags=["speakers"])

# Will be set by server.py when registering routes
_session_manager: SessionManager | None = None


def set_session_manager(manager: SessionManager) -> None:
    """Set the shared session manager reference."""
    global _session_manager  # noqa: PLW0603
    _session_manager = manager


def _get_recognizer():
    if _session_manager is None:
        raise HTTPException(503, "Speaker service not initialized")
    recognizer = _session_manager.get_voiceprint_recognizer()
    if recognizer is None:
        raise HTTPException(503, "Speaker identification is disabled")
    return recognizer


def _get_repository():
    recognizer = _get_recognizer()
    if recognizer._repository is None:
        raise HTTPException(503, "Speaker identification is disabled")
    return recognizer._repository


class SpeakerInfo(BaseModel):
    user_id: str
    name: str
    sample_count: int


@router.get("/", response_model=list[SpeakerInfo])
async def list_speakers():
    """List all enrolled speakers."""
    repo = _get_repository()
    speakers = repo.list_speakers()
    return [
        SpeakerInfo(user_id=s.user_id, name=s.name, sample_count=len(s.embeddings))
        for s in speakers
    ]


@router.post("/enroll")
async def enroll_speaker(name: str, audio: UploadFile, user_id: str | None = None):
    """
    Enroll a speaker from audio file.

    Expects raw PCM audio: 16-bit signed integer, 16kHz, mono.
    """
    recognizer = _get_recognizer()

    audio_bytes = await audio.read()
    if len(audio_bytes) < 3200:  # Less than 0.1s of audio
        raise HTTPException(400, "Audio too short for enrollment")

    audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    resolved_id = user_id or uuid.uuid4().hex[:12]
    try:
        recognizer.enroll(resolved_id, name, audio_data, 16000)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e

    logger.info(f"Enrolled speaker: {resolved_id} ({name})")
    return {"status": "enrolled", "user_id": resolved_id, "name": name}


@router.delete("/{user_id}")
async def delete_speaker(user_id: str):
    """Delete a speaker by user_id."""
    repo = _get_repository()
    deleted = repo.delete_speaker(user_id)
    if not deleted:
        raise HTTPException(404, "Speaker not found")
    return {"status": "deleted", "user_id": user_id}
