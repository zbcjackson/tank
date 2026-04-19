"""REST API routes for skill management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .manager import ConnectionManager

logger = logging.getLogger("SkillRoutes")

router = APIRouter(prefix="/api/skills", tags=["skills"])

_connection_manager: ConnectionManager | None = None


def set_connection_manager(manager: ConnectionManager) -> None:
    """Set the shared connection manager reference."""
    global _connection_manager  # noqa: PLW0603
    _connection_manager = manager


@router.post("/reload")
async def reload_skills():
    """Rescan skill directories across all active sessions.

    Returns a per-session diff of added/removed/updated skills.
    """
    if _connection_manager is None:
        raise HTTPException(503, "Service not initialized")

    results: dict[str, dict[str, list[str]]] = {}
    for session_id, assistant in _connection_manager.iter_sessions():
        results[session_id] = assistant.reload_skills()

    # Aggregate across sessions (all sessions share the same skill dirs,
    # so diffs should be identical — pick the first non-empty one for summary)
    summary = {"added": [], "removed": [], "updated": []}
    for diff in results.values():
        if any(diff[k] for k in ("added", "removed", "updated")):
            summary = diff
            break

    return {
        "status": "ok",
        "sessions_reloaded": len(results),
        "summary": summary,
        "per_session": results,
    }
