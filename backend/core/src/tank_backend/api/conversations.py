"""Conversations REST API — list and load persisted conversations."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from ..context.store import ConversationStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"], redirect_slashes=False)

_store: ConversationStore | None = None


def set_store(store: ConversationStore | None) -> None:
    """Set the conversation store for the REST API (called from server.py)."""
    global _store  # noqa: PLW0603
    _store = store


def _get_store() -> ConversationStore:
    if _store is None:
        raise HTTPException(503, "Conversation store not initialized")
    return _store


@router.get("")
async def list_conversations() -> list[dict[str, Any]]:
    """List all conversations, most recent first."""
    store = _get_store()
    conversations = store.list_conversations()
    return [
        {
            "id": s.id,
            "start_time": s.start_time.isoformat(),
            "message_count": s.message_count,
            "preview": s.preview,
        }
        for s in conversations
    ]


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str) -> dict[str, Any]:
    """Get full conversation with messages (excluding system messages)."""
    store = _get_store()
    conversation = store.load(conversation_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return {
        "id": conversation.id,
        "start_time": conversation.start_time.isoformat(),
        "messages": _format_messages(conversation.messages),
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
