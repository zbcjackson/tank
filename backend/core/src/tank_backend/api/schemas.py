"""WebSocket message schemas for Client/Server communication."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Types of messages exchanged over WebSocket."""

    SIGNAL = "signal"  # Control signals (ready, interrupt, error)
    TRANSCRIPT = "transcript"  # Real-time ASR results
    TEXT = "text"  # LLM text response deltas
    UPDATE = "update"  # UI/State updates (tool calls, etc.)
    INPUT = "input"  # Client-side text input (keyboard)
    CHANNEL_NOTIFICATION = "channel_notification"  # Real-time channel updates
    ATTACHMENT = "attachment"  # Phase 17: assistant-sent media (images)
    CONVERSATION_METADATA_UPDATED = "conversation_metadata_updated"  # Title/etc.


class WebsocketAttachment(BaseModel):
    """One assistant-sent media item delivered alongside a chat reply.

    Phase 17 only emits ``image`` kinds; the schema is shaped for
    future audio / document / video without needing another wire-format
    change. ``url`` is always a path the browser can fetch directly:
    ``media://`` URIs are rewritten to ``/api/media/<session>/<file>``
    server-side; ``http(s)://`` URIs (e.g. from ``echo_image``) pass
    through unchanged.
    """

    kind: str = "image"
    url: str
    mime_type: str = "image/jpeg"
    caption: str | None = None


class WebsocketMessage(BaseModel):
    """Base schema for all WebSocket messages."""

    type: MessageType
    content: str = ""
    speaker: str | None = None
    is_user: bool = False
    is_final: bool = False
    msg_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Phase 17: assistant-sent attachments. Empty for SIGNAL / TEXT /
    # TRANSCRIPT / UPDATE / INPUT / CHANNEL_NOTIFICATION frames.
    # Populated only for ATTACHMENT frames.
    attachments: list[WebsocketAttachment] = Field(default_factory=list)
