"""Conversation data model and protocols for context management."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


def generate_conversation_id() -> str:
    """Generate a unique conversation ID (UUID hex)."""
    return uuid.uuid4().hex


def conversation_filename(start_time: datetime) -> str:
    """Generate filename from start time: ``20260414_173440.json``."""
    return start_time.strftime("%Y%m%d_%H%M%S") + ".json"


@dataclass
class ConversationData:
    """Persisted state of a single conversation."""

    id: str
    start_time: datetime
    pid: int
    messages: list[dict[str, Any]]

    @staticmethod
    def new(system_prompt: str) -> ConversationData:
        """Create a fresh conversation with a system prompt as the first message."""
        return ConversationData(
            id=generate_conversation_id(),
            start_time=datetime.now(timezone.utc),
            pid=os.getpid(),
            messages=[{"role": "system", "content": system_prompt}],
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "id": self.id,
            "start_time": self.start_time.isoformat(),
            "pid": self.pid,
            "messages": self.messages,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ConversationData:
        """Deserialize from JSON-compatible dict."""
        return ConversationData(
            id=data["id"],
            start_time=datetime.fromisoformat(data["start_time"]),
            pid=data["pid"],
            messages=data["messages"],
        )


@dataclass(frozen=True)
class ConversationSummary:
    """Lightweight conversation metadata (no messages)."""

    id: str
    start_time: datetime
    message_count: int
    preview: str = ""


@runtime_checkable
class Summarizer(Protocol):
    """Protocol for conversation summarization."""

    async def summarize(self, messages: list[dict[str, Any]]) -> str: ...
