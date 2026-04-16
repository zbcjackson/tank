"""Sessions REST API — list and load persisted conversation sessions."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from ..context.file_store import FileSessionStore
from ..context.sqlite_store import SqliteSessionStore
from ..context.store import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"], redirect_slashes=False)

_store: SessionStore | None = None


def init_session_store(store_type: str, store_path: str) -> None:
    """Initialize the session store for the REST API (called from server.py)."""
    global _store  # noqa: PLW0603
    if store_type == "file":
        _store = FileSessionStore(store_path)
    elif store_type == "sqlite":
        _store = SqliteSessionStore(store_path)
    else:
        logger.warning("Unknown store_type %r — sessions API disabled", store_type)


def _get_store() -> SessionStore:
    if _store is None:
        raise HTTPException(503, "Session store not initialized")
    return _store


@router.get("")
async def list_sessions() -> list[dict[str, Any]]:
    """List all sessions, most recent first."""
    store = _get_store()
    sessions = store.list_sessions()
    return [
        {
            "id": s.id,
            "start_time": s.start_time.isoformat(),
            "message_count": s.message_count,
            "preview": s.preview,
        }
        for s in sessions
    ]


@router.get("/{session_id}/messages")
async def get_session_messages(session_id: str) -> dict[str, Any]:
    """Get full session with messages (excluding system messages)."""
    store = _get_store()
    session = store.load(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return {
        "id": session.id,
        "start_time": session.start_time.isoformat(),
        "messages": _format_messages(session.messages),
    }


def _format_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert internal messages to frontend-friendly format.

    Skips system messages. Each message gets a stable ``msg_id``.
    """
    result: list[dict[str, Any]] = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            continue
        entry: dict[str, Any] = {
            "role": msg["role"],
            "content": msg.get("content", ""),
            "msg_id": f"history_{i}",
        }
        name = msg.get("name")
        if name:
            entry["name"] = name
        result.append(entry)
    return result
