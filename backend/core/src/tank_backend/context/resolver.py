"""ConversationResolver — owns conversation lifecycle decisions.

Separates "which conversation to use" from "how to manage context for it."
ContextManager receives a ResolvedConversation as input; it never queries
stores or knows about channels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from .conversation import ConversationData

if TYPE_CHECKING:
    from ..channels.store import ChannelStore
    from .store import ConversationStore

logger = logging.getLogger(__name__)


class CompactionMode(Enum):
    """How context should be compacted when over token budget."""

    DESTRUCTIVE = auto()
    """Regular conversations — summarize + truncate messages in place."""

    NON_DESTRUCTIVE = auto()
    """Channel conversations — derive context at read time, preserve full history."""


@dataclass(frozen=True)
class ResolvedConversation:
    """A conversation ready to be loaded into ContextManager."""

    conversation: ConversationData
    compaction_mode: CompactionMode


class ConversationResolver:
    """Resolve which conversation to use and how to compact it.

    Owns ConversationStore and ChannelStore. Decides:
    - Whether to resume an existing conversation or create a new one
    - Whether the conversation belongs to a channel (non-destructive compaction)
    """

    def __init__(
        self,
        conversation_store: ConversationStore,
        channel_store: ChannelStore | None = None,
    ) -> None:
        self._store = conversation_store
        self._channel_store = channel_store

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def new(self, system_prompt: str) -> ResolvedConversation:
        """Create a fresh conversation. Always destructive compaction."""
        conversation = ConversationData.new(system_prompt)
        self._store.save(conversation)
        logger.info("New conversation created: %s", conversation.id)
        return ResolvedConversation(
            conversation=conversation,
            compaction_mode=CompactionMode.DESTRUCTIVE,
        )

    def resume_or_new(self, system_prompt: str) -> ResolvedConversation:
        """Resume latest same-day conversation, or create new."""
        latest = self._store.find_latest()
        if latest is not None:
            today = datetime.now(timezone.utc).date()
            if latest.start_time.date() == today:
                _update_system_prompt(latest, system_prompt)
                logger.info(
                    "Resumed conversation %s (%d messages)",
                    latest.id, len(latest.messages),
                )
                return ResolvedConversation(
                    conversation=latest,
                    compaction_mode=CompactionMode.DESTRUCTIVE,
                )
        return self.new(system_prompt)

    def resume(
        self, conversation_id: str, system_prompt: str,
    ) -> ResolvedConversation | None:
        """Resume a specific conversation by ID. Returns None if not found.

        Checks channel_store to determine compaction mode.
        """
        conv = self._store.load(conversation_id)
        if conv is None:
            return None

        _update_system_prompt(conv, system_prompt)

        mode = CompactionMode.DESTRUCTIVE
        if self._channel_store is not None:
            channel = self._channel_store.get_by_conversation_id(conversation_id)
            if channel is not None:
                mode = CompactionMode.NON_DESTRUCTIVE
                logger.info(
                    "Channel conversation detected: %s (channel=%s)",
                    conversation_id[:8], channel.slug,
                )

        return ResolvedConversation(conversation=conv, compaction_mode=mode)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, conversation: ConversationData) -> None:
        """Persist a conversation."""
        self._store.save(conversation)

    def delete(self, conversation_id: str) -> None:
        """Delete a conversation."""
        self._store.delete(conversation_id)

    def list_conversations(self) -> Any:
        """List all conversations."""
        return self._store.list_conversations()

    def close(self) -> None:
        """Release resources."""
        self._store.close()


def _update_system_prompt(conv: ConversationData, system_prompt: str) -> None:
    """Update the system prompt (first message) if present."""
    if conv.messages and conv.messages[0].get("role") == "system":
        conv.messages[0]["content"] = system_prompt
