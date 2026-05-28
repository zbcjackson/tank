"""SqliteConversationStore — ORM-backed conversation persistence."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import delete, select

from ..persistence import Database
from ..persistence.models import ConversationRow
from .conversation import ConversationData, ConversationSummary
from .store import ConversationStore

logger = logging.getLogger(__name__)


class SqliteConversationStore(ConversationStore):
    """Persist conversations in the unified Tank database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, conversation: ConversationData) -> None:
        now = time.time()
        payload = json.dumps(conversation.messages, ensure_ascii=False)
        with self._db.session() as s:
            row = s.get(ConversationRow, conversation.id)
            if row is None:
                s.add(ConversationRow(
                    conversation_id=conversation.id,
                    start_time=conversation.start_time.isoformat(),
                    pid=conversation.pid,
                    messages=payload,
                    updated_at=now,
                    title=conversation.title,
                ))
            else:
                row.start_time = conversation.start_time.isoformat()
                row.pid = conversation.pid
                row.messages = payload
                row.updated_at = now
                row.title = conversation.title

    def load(self, conversation_id: str) -> ConversationData | None:
        with self._db.session() as s:
            row = s.get(ConversationRow, conversation_id)
            if row is None:
                return None
            return ConversationData(
                id=row.conversation_id,
                start_time=datetime.fromisoformat(row.start_time),
                pid=row.pid,
                messages=json.loads(row.messages),
                title=row.title,
            )

    def list_conversations(self) -> list[ConversationSummary]:
        with self._db.session() as s:
            rows = s.execute(
                select(
                    ConversationRow.conversation_id,
                    ConversationRow.start_time,
                    ConversationRow.messages,
                    ConversationRow.updated_at,
                    ConversationRow.title,
                ).order_by(ConversationRow.updated_at.desc())
            ).all()
        return [
            ConversationSummary(
                id=row[0],
                start_time=datetime.fromisoformat(row[1]),
                message_count=len(json.loads(row[2])),
                updated_at=datetime.fromtimestamp(row[3], tz=timezone.utc),
                title=row[4],
            )
            for row in rows
        ]

    def delete(self, conversation_id: str) -> None:
        with self._db.session() as s:
            s.execute(
                delete(ConversationRow).where(
                    ConversationRow.conversation_id == conversation_id
                )
            )

    def find_latest(self) -> ConversationData | None:
        with self._db.session() as s:
            row = s.execute(
                select(ConversationRow).order_by(ConversationRow.updated_at.desc()).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            return ConversationData(
                id=row.conversation_id,
                start_time=datetime.fromisoformat(row.start_time),
                pid=row.pid,
                messages=json.loads(row.messages),
                title=row.title,
            )

    def close(self) -> None:
        """No-op: the Database owns the engine lifecycle."""
        return
