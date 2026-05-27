"""ConversationMessagesStore — denormalised per-message rows + FTS5 search.

The canonical conversation storage stays in ``conversations.messages``
(JSON blob). This store mirrors that JSON one row per message so we can
attach an FTS5 virtual table for keyword/CJK search without parsing
JSON every time.

Public API:
- ``replace_for_conversation(conv_id, messages)`` — wipe and re-insert
  every message for the conversation. Called by ``ContextManager`` on
  every persist (per-turn writes go through ``ConversationStore.save``,
  which we hook from the ``ContextManager`` side).
- ``search(query, *, limit, conversation_id?)`` — FTS5 MATCH query.
  Returns hits ranked by FTS5's built-in BM25 score.

Why ``replace`` over ``append``: per-turn ``ContextManager`` flow
already mutates ``conv.messages`` and re-saves the JSON blob. Mirroring
that with a wholesale replace is simpler than incremental sync, and the
volume is tiny (one conversation's worth of rows per turn).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, text

from .database import Database
from .models import ConversationMessageRow

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationMessageHit:
    """One FTS5 search hit."""

    conversation_id: str
    seq: int
    role: str
    content: str
    created_at: datetime
    rank: float


class ConversationMessagesStore:
    """ORM + FTS5 store for per-message rows."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def replace_for_conversation(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
        *,
        timestamp: float | None = None,
    ) -> None:
        """Wipe and re-insert all rows for this conversation.

        The FTS5 virtual table is kept in sync via SQLite triggers.
        Rows with empty/non-string content are skipped — there's
        nothing to index.
        """
        ts = timestamp or _now_epoch()
        with self._db.session() as s:
            s.execute(
                delete(ConversationMessageRow).where(
                    ConversationMessageRow.conversation_id == conversation_id
                )
            )
            for seq, msg in enumerate(messages):
                role = msg.get("role")
                content = _coerce_content(msg.get("content"))
                if not isinstance(role, str) or not role or not content:
                    continue
                s.add(ConversationMessageRow(
                    conversation_id=conversation_id,
                    seq=seq,
                    role=role,
                    content=content,
                    created_at=ts,
                ))

    def delete_for_conversation(self, conversation_id: str) -> None:
        with self._db.session() as s:
            s.execute(
                delete(ConversationMessageRow).where(
                    ConversationMessageRow.conversation_id == conversation_id
                )
            )

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        conversation_id: str | None = None,
    ) -> list[ConversationMessageHit]:
        """Run an FTS5 MATCH query.

        ``query`` is passed to FTS5 as-is; the trigram tokenizer handles
        both Latin and CJK input. Bad query syntax (unbalanced quotes,
        FTS-reserved punctuation) returns an empty list rather than
        500-ing the caller — this surface is reachable from user input.
        """
        if not query.strip():
            return []
        sql = (
            "SELECT m.conversation_id, m.seq, m.role, m.content, "
            "m.created_at, fts.rank "
            "FROM conversation_messages m "
            "JOIN conversation_messages_fts fts ON m.id = fts.rowid "
            "WHERE conversation_messages_fts MATCH :q "
        )
        params: dict[str, Any] = {"q": _safe_query(query), "limit": limit}
        if conversation_id is not None:
            sql += "AND m.conversation_id = :cid "
            params["cid"] = conversation_id
        sql += "ORDER BY fts.rank LIMIT :limit"

        try:
            with self._db.session() as s:
                rows = s.execute(text(sql), params).all()
        except Exception:
            logger.debug("FTS query failed for %r", query, exc_info=True)
            return []

        return [
            ConversationMessageHit(
                conversation_id=row[0],
                seq=row[1],
                role=row[2],
                content=row[3],
                created_at=datetime.fromtimestamp(row[4], tz=timezone.utc),
                rank=float(row[5]),
            )
            for row in rows
        ]


def _coerce_content(content: object) -> str:
    """Pull a flat string out of OpenAI-shaped message content."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text_val = part.get("text")
                if isinstance(text_val, str):
                    parts.append(text_val)
        return " ".join(parts).strip()
    return ""


def _safe_query(query: str) -> str:
    """Sanitise an FTS5 MATCH expression.

    User input may carry quotes / parens that break FTS5. Wrap the whole
    thing in double quotes and escape embedded ones — turns the query
    into a phrase match, which is what most callers want anyway.
    """
    cleaned = query.strip().replace('"', '""')
    return f'"{cleaned}"'


def _now_epoch() -> float:
    import time
    return time.time()
