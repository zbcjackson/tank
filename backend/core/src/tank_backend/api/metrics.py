"""Metrics API — exposes pipeline metrics collected by MetricsCollector."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from .manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

_connection_manager: ConnectionManager | None = None


def set_connection_manager(manager: ConnectionManager) -> None:
    """Inject the shared ConnectionManager (called from server.py)."""
    global _connection_manager
    _connection_manager = manager


@router.get("/{session_id}")
async def get_session_metrics(session_id: str) -> dict[str, Any]:
    """Return pipeline metrics for a specific session."""
    if _connection_manager is None:
        raise HTTPException(status_code=503, detail="Connection manager not initialized")

    assistant = _connection_manager.get_assistant(session_id)
    if assistant is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    snapshot = assistant.metrics
    snapshot["session_id"] = session_id
    return snapshot


@router.get("")
async def get_all_metrics() -> dict[str, Any]:
    """Return aggregated metrics across all active sessions."""
    if _connection_manager is None:
        raise HTTPException(status_code=503, detail="Connection manager not initialized")

    sessions: dict[str, Any] = {}
    for session_id, assistant in _connection_manager._sessions.items():
        snapshot = assistant.metrics
        snapshot["session_id"] = session_id
        sessions[session_id] = snapshot

    return {
        "active_sessions": len(sessions),
        "sessions": sessions,
    }
