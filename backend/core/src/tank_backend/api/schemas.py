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
    APPROVAL_RESPONSE = "approval_response"  # User approval/rejection of tool execution


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
