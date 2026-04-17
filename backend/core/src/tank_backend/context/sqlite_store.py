"""SqliteConversationStore — SQLite-based conversation persistence."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from .conversation import ConversationData, ConversationSummary
from .store import ConversationStore

logger = logging.getLogger(__name__)


class SqliteConversationStore(ConversationStore):
    """Persist conversations in a SQLite database.

    Uses WAL mode for concurrent reads and INSERT OR REPLACE for upserts.
    """

    def __init__(self, db_path: str | Path = "~/.tank/conversations.db") -> None:
        resolved = Path(db_path).expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(resolved)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                start_time TEXT NOT NULL,
                pid INTEGER NOT NULL,
                messages TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def save(self, conversation: ConversationData) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO conversations
                (conversation_id, start_time, pid, messages, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                conversation.id,
                conversation.start_time.isoformat(),
                conversation.pid,
                json.dumps(conversation.messages, ensure_ascii=False),
                time.time(),
            ),
        )
        self._conn.commit()

    def load(self, conversation_id: str) -> ConversationData | None:
        row = self._conn.execute(
            "SELECT conversation_id, start_time, pid, messages "
            "FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None
        return ConversationData(
            id=row[0],
            start_time=datetime.fromisoformat(row[1]),
            pid=row[2],
            messages=json.loads(row[3]),
        )

    def list_conversations(self) -> list[ConversationSummary]:
        rows = self._conn.execute(
            "SELECT conversation_id, start_time, messages "
            "FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        results: list[ConversationSummary] = []
        for row in rows:
            messages = json.loads(row[2])
            results.append(
                ConversationSummary(
                    id=row[0],
                    start_time=datetime.fromisoformat(row[1]),
                    message_count=len(messages),
                )
            )
        return results

    def delete(self, conversation_id: str) -> None:
        self._conn.execute(
            "DELETE FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        )
        self._conn.commit()

    def find_latest(self) -> ConversationData | None:
        row = self._conn.execute(
            "SELECT conversation_id, start_time, pid, messages "
            "FROM conversations ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return ConversationData(
            id=row[0],
            start_time=datetime.fromisoformat(row[1]),
            pid=row[2],
            messages=json.loads(row[3]),
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]
