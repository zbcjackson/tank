"""SessionStore — abstract base class for session persistence."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .session import SessionData, SessionSummary


class SessionStore(ABC):
    """Abstract interface for persisting sessions.

    Implementations: :class:`FileSessionStore`, :class:`SqliteSessionStore`.
    """

    @abstractmethod
    def save(self, session: SessionData) -> None:
        """Save (upsert) a session."""

    @abstractmethod
    def load(self, session_id: str) -> SessionData | None:
        """Load a session by ID, or ``None`` if not found."""

    @abstractmethod
    def list_sessions(self) -> list[SessionSummary]:
        """List all sessions, most recent first."""

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Delete a session by ID."""

    @abstractmethod
    def find_latest(self) -> SessionData | None:
        """Load the most recent session, or ``None`` if none exist."""

    def close(self) -> None:  # noqa: B027
        """Optional cleanup (e.g. close DB connection)."""
