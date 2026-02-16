"""WebSocket message schemas for Client/Server communication."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Types of messages exchanged over WebSocket."""
    SIGNAL = "signal"       # Control signals (ready, interrupt, error)
    TRANSCRIPT = "transcript" # Real-time ASR results
    TEXT = "text"           # LLM text response deltas
    UPDATE = "update"       # UI/State updates (tool calls, etc.)
    INPUT = "input"         # Client-side text input (keyboard)


class WebsocketMessage(BaseModel):
    """Base schema for all WebSocket messages."""
    type: MessageType
    content: str = ""
    is_final: bool = False
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
