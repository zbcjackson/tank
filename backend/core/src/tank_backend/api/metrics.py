"""Metrics API — exposes pipeline metrics collected by MetricsCollector."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from .manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

_session_manager: SessionManager | None = None


def set_session_manager(manager: SessionManager) -> None:
    """Inject the shared SessionManager (called from server.py)."""
    global _session_manager
    _session_manager = manager


@router.get("/{session_id}")
async def get_session_metrics(session_id: str) -> dict[str, Any]:
    """Return pipeline metrics for a specific session."""
    if _session_manager is None:
        raise HTTPException(status_code=503, detail="Session manager not initialized")

    assistant = _session_manager.get_assistant(session_id)
    if assistant is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    snapshot = assistant.metrics
    snapshot["session_id"] = session_id
    return snapshot


@router.get("")
async def get_all_metrics() -> dict[str, Any]:
    """Return aggregated metrics across all active sessions."""
    if _session_manager is None:
        raise HTTPException(status_code=503, detail="Session manager not initialized")

    sessions: dict[str, Any] = {}
    for session_id, assistant in _session_manager._sessions.items():
        snapshot = assistant.metrics
        snapshot["session_id"] = session_id
        sessions[session_id] = snapshot

    return {
        "active_sessions": len(sessions),
        "sessions": sessions,
    }
