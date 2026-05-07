"""ConversationStore — abstract base class for conversation persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .conversation import ConversationData, ConversationSummary

if TYPE_CHECKING:
    from ..persistence import Database


class ConversationStore(ABC):
    """Abstract interface for persisting conversations.

    Only implementation: :class:`SqliteConversationStore`. The ABC is
    kept because test doubles (e.g. in-memory stores) implement it for
    integration tests.
    """

    @abstractmethod
    def save(self, conversation: ConversationData) -> None:
        """Save (upsert) a conversation."""

    @abstractmethod
    def load(self, conversation_id: str) -> ConversationData | None:
        """Load a conversation by ID, or ``None`` if not found."""

    @abstractmethod
    def list_conversations(self) -> list[ConversationSummary]:
        """List all conversations, most recent first."""

    @abstractmethod
    def delete(self, conversation_id: str) -> None:
        """Delete a conversation by ID."""

    @abstractmethod
    def find_latest(self) -> ConversationData | None:
        """Load the most recent conversation, or ``None`` if none exist."""

    def close(self) -> None:
        """Optional cleanup (e.g. close DB connection)."""
        return


def create_store(
    enabled: bool,
    db: Database,
) -> ConversationStore | None:
    """Create a SqliteConversationStore, or ``None`` if persistence is off."""
    import logging

    logger = logging.getLogger(__name__)

    if not enabled:
        logger.info("Conversation persistence disabled")
        return None

    from .sqlite_store import SqliteConversationStore
    return SqliteConversationStore(db)
