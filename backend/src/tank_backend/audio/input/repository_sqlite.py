"""SQLite-based speaker storage and identification."""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

import numpy as np

from .repository import Speaker, SpeakerRepository

logger = logging.getLogger("SQLiteSpeakerRepo")


class SQLiteSpeakerRepository(SpeakerRepository):
    """
    SQLite-based speaker storage.

    Stores speaker profiles and embeddings in a local SQLite database.
    Thread-safe for concurrent access.
    """

    def __init__(self, db_path: str = "data/speakers.db"):
        """
        Initialize SQLite speaker repository.

        Args:
            db_path: Path to SQLite database file
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._create_tables()
        logger.info(f"SQLite speaker repository initialized: {db_path}")

    def _create_tables(self) -> None:
        """Create database schema."""
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS speakers (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                embedding BLOB NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES speakers(user_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_embeddings_user_id
            ON embeddings(user_id)
        """)
        self._conn.commit()

    def add_speaker(self, user_id: str, name: str, embedding: np.ndarray) -> None:
        """
        Add a new speaker or append embedding to existing speaker.

        Args:
            user_id: Unique user identifier
            name: Display name
            embedding: Speaker embedding vector
        """
        cursor = self._conn.cursor()
        now = time.time()

        # Insert or update speaker
        cursor.execute(
            """
            INSERT INTO speakers (user_id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                updated_at = excluded.updated_at
        """,
            (user_id, name, now, now),
        )

        # Insert embedding
        embedding_blob = embedding.astype(np.float32).tobytes()
        cursor.execute(
            """
            INSERT INTO embeddings (user_id, embedding, created_at)
            VALUES (?, ?, ?)
        """,
            (user_id, embedding_blob, now),
        )

        self._conn.commit()
        logger.info(f"Added embedding for speaker: {user_id} ({name})")

    def get_speaker(self, user_id: str) -> Speaker | None:
        """
        Retrieve speaker by user_id.

        Args:
            user_id: User identifier

        Returns:
            Speaker object or None if not found
        """
        cursor = self._conn.cursor()

        # Get speaker info
        cursor.execute(
            """
            SELECT name, created_at, updated_at
            FROM speakers
            WHERE user_id = ?
        """,
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        name, created_at, updated_at = row

        # Get embeddings
        cursor.execute(
            """
            SELECT embedding
            FROM embeddings
            WHERE user_id = ?
        """,
            (user_id,),
        )
        embeddings = [np.frombuffer(row[0], dtype=np.float32) for row in cursor.fetchall()]

        return Speaker(
            user_id=user_id,
            name=name,
            embeddings=embeddings,
            created_at=created_at,
            updated_at=updated_at,
        )

    def list_speakers(self) -> list[Speaker]:
        """
        List all registered speakers.

        Returns:
            List of all speakers
        """
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT s.user_id, s.name, s.created_at, s.updated_at, e.embedding
            FROM speakers s
            LEFT JOIN embeddings e ON s.user_id = e.user_id
            ORDER BY s.user_id
        """)

        speakers_map: dict[str, Speaker] = {}
        for row in cursor.fetchall():
            uid, name, created_at, updated_at, emb_blob = row
            if uid not in speakers_map:
                speakers_map[uid] = Speaker(
                    user_id=uid,
                    name=name,
                    embeddings=[],
                    created_at=created_at,
                    updated_at=updated_at,
                )
            if emb_blob is not None:
                speakers_map[uid].embeddings.append(
                    np.frombuffer(emb_blob, dtype=np.float32)
                )

        return list(speakers_map.values())

    def delete_speaker(self, user_id: str) -> bool:
        """
        Delete a speaker.

        Args:
            user_id: User identifier

        Returns:
            True if deleted, False if not found
        """
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM speakers WHERE user_id = ?", (user_id,))
        self._conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deleted speaker: {user_id}")
        return deleted

    def identify(self, embedding: np.ndarray, threshold: float = 0.6) -> str | None:
        """
        Identify speaker from embedding using cosine similarity.

        Args:
            embedding: Query embedding
            threshold: Minimum cosine similarity (0.0-1.0)

        Returns:
            user_id of best match, or None if no match above threshold
        """
        speakers = self.list_speakers()
        if not speakers:
            return None

        best_score = -1.0
        best_user_id = None

        for speaker in speakers:
            for stored_embedding in speaker.embeddings:
                score = self._cosine_similarity(embedding, stored_embedding)
                if score > best_score:
                    best_score = score
                    best_user_id = speaker.user_id

        if best_score >= threshold:
            logger.debug(f"Identified speaker: {best_user_id} (score={best_score:.3f})")
            return best_user_id

        logger.debug(f"No match above threshold (best={best_score:.3f})")
        return None

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            a: First vector
            b: Second vector

        Returns:
            Cosine similarity (0.0-1.0)
        """
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    def close(self) -> None:
        """Close database connection."""
        self._conn.close()
        logger.info("SQLite speaker repository closed")
