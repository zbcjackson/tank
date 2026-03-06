"""Abstract interface for speaker storage and identification."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class Speaker:
    """Speaker profile with embeddings."""

    user_id: str
    name: str
    embeddings: list[np.ndarray]  # Multiple embeddings for robustness
    created_at: float
    updated_at: float


class SpeakerRepository(ABC):
    """
    Abstract interface for speaker storage.

    Implementations can use different storage backends (SQLite, PostgreSQL, Redis, etc.)
    while maintaining a consistent interface.
    """

    @abstractmethod
    def add_speaker(self, user_id: str, name: str, embedding: np.ndarray) -> None:
        """
        Add a new speaker or append embedding to existing speaker.

        Args:
            user_id: Unique user identifier
            name: Display name
            embedding: Speaker embedding vector
        """
        pass

    @abstractmethod
    def get_speaker(self, user_id: str) -> Speaker | None:
        """
        Retrieve speaker by user_id.

        Args:
            user_id: User identifier

        Returns:
            Speaker object or None if not found
        """
        pass

    @abstractmethod
    def list_speakers(self) -> list[Speaker]:
        """
        List all registered speakers.

        Returns:
            List of all speakers
        """
        pass

    @abstractmethod
    def delete_speaker(self, user_id: str) -> bool:
        """
        Delete a speaker.

        Args:
            user_id: User identifier

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    def identify(self, embedding: np.ndarray, threshold: float = 0.6) -> str | None:
        """
        Identify speaker from embedding.

        Args:
            embedding: Query embedding
            threshold: Minimum cosine similarity (0.0-1.0)

        Returns:
            user_id of best match, or None if no match above threshold
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Release resources (database connections, etc.)."""
        pass
