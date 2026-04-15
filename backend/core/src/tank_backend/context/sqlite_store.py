"""SqliteSessionStore — SQLite-based session persistence."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from .session import SessionData, SessionSummary
from .store import SessionStore

logger = logging.getLogger(__name__)


class SqliteSessionStore(SessionStore):
    """Persist sessions in a SQLite database.

    Uses WAL mode for concurrent reads and INSERT OR REPLACE for upserts.
    """

    def __init__(self, db_path: str | Path = "~/.tank/sessions.db") -> None:
        resolved = Path(db_path).expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(resolved)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                start_time TEXT NOT NULL,
                pid INTEGER NOT NULL,
                messages TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def save(self, session: SessionData) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO sessions (session_id, start_time, pid, messages, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session.id,
                session.start_time.isoformat(),
                session.pid,
                json.dumps(session.messages, ensure_ascii=False),
                time.time(),
            ),
        )
        self._conn.commit()

    def load(self, session_id: str) -> SessionData | None:
        row = self._conn.execute(
            "SELECT session_id, start_time, pid, messages FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return SessionData(
            id=row[0],
            start_time=datetime.fromisoformat(row[1]),
            pid=row[2],
            messages=json.loads(row[3]),
        )

    def list_sessions(self) -> list[SessionSummary]:
        rows = self._conn.execute(
            "SELECT session_id, start_time, messages FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        results: list[SessionSummary] = []
        for row in rows:
            messages = json.loads(row[2])
            results.append(
                SessionSummary(
                    id=row[0],
                    start_time=datetime.fromisoformat(row[1]),
                    message_count=len(messages),
                )
            )
        return results

    def delete(self, session_id: str) -> None:
        self._conn.execute(
            "DELETE FROM sessions WHERE session_id = ?", (session_id,)
        )
        self._conn.commit()

    def find_latest(self) -> SessionData | None:
        row = self._conn.execute(
            "SELECT session_id, start_time, pid, messages FROM sessions "
            "ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return SessionData(
            id=row[0],
            start_time=datetime.fromisoformat(row[1]),
            pid=row[2],
            messages=json.loads(row[3]),
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]
