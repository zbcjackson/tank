"""Metrics API — exposes pipeline metrics collected by MetricsCollector."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from . import deps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/{session_id}")
async def get_session_metrics(session_id: str) -> dict[str, Any]:
    """Return pipeline metrics for a specific session."""
    mgr = deps.connection_manager()
    assistant = mgr.get_assistant(session_id)
    if assistant is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    snapshot = assistant.metrics
    snapshot["session_id"] = session_id
    return snapshot


@router.get("")
async def get_all_metrics() -> dict[str, Any]:
    """Return aggregated metrics across all active sessions."""
    mgr = deps.connection_manager()

    sessions: dict[str, Any] = {}
    for session_id, assistant in mgr.iter_sessions():
        snapshot = assistant.metrics
        snapshot["session_id"] = session_id
        sessions[session_id] = snapshot

    return {
        "active_sessions": len(sessions),
        "sessions": sessions,
    }
