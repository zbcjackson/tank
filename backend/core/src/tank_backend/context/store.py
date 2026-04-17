"""ConversationStore — abstract base class for conversation persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .conversation import ConversationData, ConversationSummary


class ConversationStore(ABC):
    """Abstract interface for persisting conversations.

    Implementations: :class:`FileConversationStore`, :class:`SqliteConversationStore`.
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

    def close(self) -> None:  # noqa: B027
        """Optional cleanup (e.g. close DB connection)."""


def create_store(store_type: str, store_path: str) -> ConversationStore | None:
    """Factory: create a ConversationStore from config values.

    Returns ``None`` for unknown or disabled store types.
    """
    import logging

    logger = logging.getLogger(__name__)

    if store_type == "sqlite":
        from .sqlite_store import SqliteConversationStore

        return SqliteConversationStore(store_path)
    if store_type == "file":
        from .file_store import FileConversationStore

        return FileConversationStore(store_path)
    logger.info("Conversation persistence disabled (store_type=%s)", store_type)
    return None
