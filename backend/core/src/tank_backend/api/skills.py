"""REST API routes for skill management."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from . import deps

logger = logging.getLogger("SkillRoutes")

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.post("/reload")
async def reload_skills():
    """Rescan skill directories across all active sessions.

    Returns a per-session diff of added/removed/updated skills.
    """
    mgr = deps.connection_manager()

    results: dict[str, dict[str, list[str]]] = {}
    for session_id, assistant in mgr.iter_sessions():
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
