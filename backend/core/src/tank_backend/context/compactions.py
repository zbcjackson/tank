"""CompactionRecord — domain dataclass describing one compaction event."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CompactionRecord:
    """One destructive-compaction snapshot for a conversation.

    Created in :meth:`ContextManager.compact` *before* ``conv.messages`` is
    mutated. ``pre_compaction_messages`` holds the messages that the
    summarizer replaced; restoring this record re-inflates them.
    """

    id: str
    conversation_id: str
    parent_id: str | None
    created_at: datetime
    focus: str | None
    tokens_before: int
    tokens_after: int
    compacted_count: int
    summary_text: str
    pre_compaction_messages: list[dict[str, Any]]
