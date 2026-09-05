"""Wire message types for the Tank client WebSocket protocol."""

from __future__ import annotations

from enum import Enum


class MessageType(str, Enum):
    """Types of messages exchanged over WebSocket."""

    SIGNAL = "signal"  # Control signals (ready, interrupt, error)
    TRANSCRIPT = "transcript"  # Real-time ASR results
    TEXT = "text"  # LLM text response deltas
    UPDATE = "update"  # UI/State updates (tool calls, etc.)
    INPUT = "input"  # Client-side text input (keyboard)
    CHANNEL_NOTIFICATION = "channel_notification"  # Real-time channel updates
    ATTACHMENT = "attachment"  # Assistant-sent media (images)
    CONVERSATION_METADATA_UPDATED = "conversation_metadata_updated"  # Title/etc.
    CONFIG = "config"  # Client session hot-config (P1-3, deep-merge)
    CONTEXT_INJECT = "context_inject"  # Context-only injection, no generation
