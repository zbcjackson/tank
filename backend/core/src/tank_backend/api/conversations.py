"""Conversations REST API — list and load persisted conversations."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import deps

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"], redirect_slashes=False)


_TITLE_MAX_LEN = 80


class CompactionResponse(BaseModel):
    id: str
    conversation_id: str
    parent_id: str | None
    created_at: str
    focus: str | None
    tokens_before: int
    tokens_after: int
    compacted_count: int
    summary_text: str
    pre_compaction_messages: list[dict[str, Any]] | None = None


class RestoreResponse(BaseModel):
    conversation_id: str
    restored_compaction_id: str
    messages_restored: int
    descendants_removed: int
    message_count_after: int


class TitleUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=_TITLE_MAX_LEN)


class TitleResponse(BaseModel):
    conversation_id: str
    title: str | None


@router.get("")
async def list_conversations() -> list[dict[str, Any]]:
    """List all conversations, most recent first."""
    store = deps.conversation_store()
    conversations = store.list_conversations()
    return [
        {
            "id": s.id,
            "start_time": s.start_time.isoformat(),
            "updated_at": s.updated_at.isoformat(),
            "message_count": s.message_count,
            "preview": s.preview,
            "title": s.title,
        }
        for s in conversations
    ]


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str) -> dict[str, Any]:
    """Get full conversation with messages (excluding system messages)."""
    store = deps.conversation_store()
    conversation = store.load(conversation_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    return {
        "id": conversation.id,
        "start_time": conversation.start_time.isoformat(),
        "title": conversation.title,
        "messages": _format_messages(conversation.messages),
    }


@router.patch("/{conversation_id}", response_model=TitleResponse)
async def update_conversation_title(
    conversation_id: str, body: TitleUpdateRequest,
) -> TitleResponse:
    """Rename a conversation. The user-supplied title overrides any LLM title."""
    store = deps.conversation_store()
    conversation = store.load(conversation_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Title must not be empty after trimming")
    if len(title) > _TITLE_MAX_LEN:
        raise HTTPException(400, f"Title exceeds {_TITLE_MAX_LEN} characters")
    conversation.title = title
    store.save(conversation)
    return TitleResponse(conversation_id=conversation_id, title=title)


@router.post("/{conversation_id}/title/regenerate", response_model=TitleResponse)
async def regenerate_conversation_title(conversation_id: str) -> TitleResponse:
    """Re-run the LLM title generator and persist the result.

    Returns the new title (may be ``None`` if the LLM produced empty output).
    """
    store = deps.conversation_store()
    if store.load(conversation_id) is None:
        raise HTTPException(404, "Conversation not found")
    generator = deps.title_generator()
    title = await generator.generate(conversation_id)
    return TitleResponse(conversation_id=conversation_id, title=title)


@router.get("/{conversation_id}/compactions", response_model=list[CompactionResponse])
async def list_compactions(
    conversation_id: str, include_messages: bool = False,
) -> list[CompactionResponse]:
    """List compaction lineage for a conversation, newest first.

    Pass ``?include_messages=true`` to include the full pre-compaction
    message snapshots. Off by default to keep the payload small.
    """
    store = deps.compaction_store()
    records = store.list_for_conversation(conversation_id)
    return [_record_to_response(r, include_messages) for r in records]


@router.post(
    "/{conversation_id}/compactions/{compaction_id}/restore",
    response_model=RestoreResponse,
)
async def restore_compaction(
    conversation_id: str, compaction_id: str,
) -> RestoreResponse:
    """Re-inflate a conversation to its pre-compaction state.

    Replaces the post-summary view with ``[system_msg] + pre_compaction_messages
    + current_tail`` (where current_tail is everything after the latest
    compaction summary). The restored record and any descendants are then
    deleted — they no longer describe a valid history.
    """
    compaction_store = deps.compaction_store()
    conversation_store = deps.conversation_store()

    record = compaction_store.get(compaction_id)
    if record is None or record.conversation_id != conversation_id:
        raise HTTPException(404, "Compaction record not found")

    conversation = conversation_store.load(conversation_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")

    # The current conversation looks like [system_msg, summary_msg?, ...tail].
    # We restore by replacing summary_msg (if present) with the original
    # pre_compaction_messages.
    messages = conversation.messages
    if not messages or messages[0].get("role") != "system":
        raise HTTPException(409, "Conversation has no system prompt to anchor restore")

    system_msg = messages[0]
    rest = messages[1:]
    if rest and rest[0].get("role") == "system" and \
            (rest[0].get("metadata") or {}).get("type") == "compaction_summary":
        tail = rest[1:]
    else:
        tail = rest

    conversation.messages = [system_msg] + list(record.pre_compaction_messages) + tail
    conversation_store.save(conversation)

    descendants_removed = compaction_store.delete_descendants(compaction_id)

    return RestoreResponse(
        conversation_id=conversation_id,
        restored_compaction_id=compaction_id,
        messages_restored=len(record.pre_compaction_messages),
        descendants_removed=descendants_removed,
        message_count_after=len(conversation.messages),
    )


def _record_to_response(record: Any, include_messages: bool) -> CompactionResponse:
    return CompactionResponse(
        id=record.id,
        conversation_id=record.conversation_id,
        parent_id=record.parent_id,
        created_at=record.created_at.isoformat(),
        focus=record.focus,
        tokens_before=record.tokens_before,
        tokens_after=record.tokens_after,
        compacted_count=record.compacted_count,
        summary_text=record.summary_text,
        pre_compaction_messages=record.pre_compaction_messages if include_messages else None,
    )


def _format_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert internal messages to frontend-friendly format.

    Skips system messages. Preserves tool_calls and tool results so the
    frontend can reconstruct tool cards and approval cards on resume.

    Phase 19: ``tool_follow_up`` messages (the user-role scaffolding
    the LLM loop emits to carry image blocks back into the next turn —
    see ``llm._build_follow_up_user_message``) get *transformed* into
    a frontend-friendly ``image`` shape rather than dropped.

    The transformation:

    - Each ``image_url`` part becomes one entry in ``attachments``,
      with the URL rewritten from ``media://session/file`` to
      ``/api/media/session/file`` so the browser can fetch via
      ``<img src>`` (the same rewrite the WebSocket attachment frame
      uses for live messages — keeps the live and resume paths
      visually identical).
    - ``http(s)://`` URLs and ``data:`` URLs pass through unchanged.
    - ``role`` becomes ``assistant`` so the message groups under the
      same turn as the originating tool call.
    - The ``tool_call_id`` from the message metadata flows through so
      the frontend can pair the image with its tool card if it wants.
    - ``kind: "image"`` is the discriminator the frontend's
      ``resumeConversation`` switches on; existing entries don't
      carry this field, so the change is backward-compatible.

    Defensive last-line guard: any other persisted message whose
    ``content`` is non-string also gets coerced to ``""`` so a future
    code path that stores rich content can't crash the Markdown
    renderer.
    """
    result: list[dict[str, Any]] = []
    for i, msg in enumerate(messages):
        role = msg.get("role")
        if role == "system":
            continue

        # Phase 19: surface image follow-ups via a clean image shape.
        # The original LLM-loop scaffolding (list-of-parts content)
        # would otherwise crash the Markdown renderer.
        metadata = msg.get("metadata") or {}
        if metadata.get("tool_follow_up"):
            image_msg = _follow_up_to_image_message(
                msg, metadata, msg_id=f"history_{i}",
            )
            if image_msg is not None:
                result.append(image_msg)
            # Text-only follow-ups (no images) get dropped — they were
            # always invisible to the user and the tool card already
            # represents the LLM's view of the result.
            continue

        # Defensive: coerce any non-string content to "". The
        # frontend's Markdown renderer crashes on list/dict content
        # because react-markdown expects a string. This guard keeps
        # the resume path resilient even if a future code path
        # persists multi-part content without flagging tool_follow_up.
        raw_content = msg.get("content", "")
        if not isinstance(raw_content, str):
            raw_content = ""

        entry: dict[str, Any] = {
            "role": role,
            "content": raw_content,
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


def _follow_up_to_image_message(
    msg: dict[str, Any],
    metadata: dict[str, Any],
    *,
    msg_id: str,
) -> dict[str, Any] | None:
    """Extract image attachments from a ``tool_follow_up`` message.

    Returns a frontend-shaped entry like::

        {
            "role": "assistant",
            "msg_id": "history_8",
            "kind": "image",
            "tool_call_id": "tc_42",
            "attachments": [
                {
                    "kind": "image",
                    "url": "/api/media/<session>/<file>.png",
                    "mime_type": "image/png",
                    "caption": null,
                },
                ...
            ],
        }

    Returns ``None`` if the follow-up carries no image_url parts —
    those are LLM-loop noise the user never needed to see.
    """
    content = msg.get("content")
    if not isinstance(content, list):
        return None

    attachments: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "image_url":
            continue
        image_url = part.get("image_url")
        if not isinstance(image_url, dict):
            continue
        url = image_url.get("url")
        if not isinstance(url, str) or not url:
            continue
        # Rewrite media:// → /api/media/... so the browser can fetch
        # via <img src>. Same rewrite the WebSocket attachment frame
        # does for live messages — keeps the two paths visually
        # consistent.
        if url.startswith("media://"):
            stripped = url[len("media://"):]
            url = f"/api/media/{stripped}"
        # Best-effort MIME inference — the persisted block may not
        # carry one but the wire schema requires the field. ChartTool
        # emits PNG; ``echo_image`` and future tools may emit other
        # image types but the browser sniffs from the bytes anyway.
        mime_type = "image/png"
        attachments.append({
            "kind": "image",
            "url": url,
            "mime_type": mime_type,
            "caption": None,
        })

    if not attachments:
        return None

    entry: dict[str, Any] = {
        "role": "assistant",
        "msg_id": msg_id,
        "kind": "image",
        "attachments": attachments,
    }
    tool_call_id = metadata.get("tool_call_id")
    if tool_call_id:
        entry["tool_call_id"] = tool_call_id
    return entry
