"""Checkpointer — persist conversation history to SQLite."""

import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("Checkpointer")


class Checkpointer:
    """Persist conversation history to SQLite so sessions survive restarts.

    Uses WAL mode for concurrent reads and INSERT OR REPLACE for idempotent saves.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                history TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def save(self, session_id: str, history: list[dict]) -> None:
        """Save conversation history for a session (upsert)."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO sessions (session_id, history, updated_at)
            VALUES (?, ?, ?)
            """,
            (session_id, json.dumps(history, ensure_ascii=False), time.time()),
        )
        self._conn.commit()

    def load(self, session_id: str) -> list[dict] | None:
        """Load conversation history for a session, or None if not found."""
        row = self._conn.execute(
            "SELECT history FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def list_sessions(self) -> list[dict]:
        """List all sessions with their session_id and updated_at."""
        rows = self._conn.execute(
            "SELECT session_id, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [{"session_id": r[0], "updated_at": r[1]} for r in rows]

    def delete(self, session_id: str) -> None:
        """Delete a session."""
        self._conn.execute(
            "DELETE FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
