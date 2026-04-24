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

    Skips system messages. Preserves tool_calls and tool results so the
    frontend can reconstruct tool cards and approval cards on resume.
    """
    result: list[dict[str, Any]] = []
    for i, msg in enumerate(messages):
        role = msg.get("role")
        if role == "system":
            continue

        entry: dict[str, Any] = {
            "role": role,
            "content": msg.get("content", "") or "",
            "msg_id": f"history_{i}",
        }

        name = msg.get("name")
        if name:
            entry["name"] = name

        # Preserve tool_calls on assistant messages so the frontend
        # can render tool cards for the history.
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            entry["tool_calls"] = tool_calls

        # Mark tool-result messages so the frontend can pair them
        # with the corresponding tool_call.
        if role == "tool":
            entry["tool_call_id"] = msg.get("tool_call_id", "")

        result.append(entry)
    return result
