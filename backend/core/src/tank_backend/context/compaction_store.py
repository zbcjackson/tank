"""CompactionStore — ORM-backed persistence for the compaction lineage."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select

from ..persistence import Database
from ..persistence.models import CompactionRow
from .compactions import CompactionRecord

logger = logging.getLogger(__name__)


class CompactionStore:
    """Persist :class:`CompactionRecord` rows in the unified Tank database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def save(self, record: CompactionRecord) -> None:
        with self._db.session() as s:
            s.add(CompactionRow(
                id=record.id,
                conversation_id=record.conversation_id,
                parent_id=record.parent_id,
                created_at=record.created_at.timestamp(),
                focus=record.focus,
                tokens_before=record.tokens_before,
                tokens_after=record.tokens_after,
                compacted_count=record.compacted_count,
                summary_text=record.summary_text,
                pre_compaction_messages=json.dumps(
                    record.pre_compaction_messages, ensure_ascii=False,
                ),
            ))

    def get(self, record_id: str) -> CompactionRecord | None:
        with self._db.session() as s:
            row = s.get(CompactionRow, record_id)
            if row is None:
                return None
            return _row_to_record(row)

    def list_for_conversation(self, conversation_id: str) -> list[CompactionRecord]:
        with self._db.session() as s:
            rows = s.execute(
                select(CompactionRow)
                .where(CompactionRow.conversation_id == conversation_id)
                .order_by(CompactionRow.created_at.desc())
            ).scalars().all()
        return [_row_to_record(r) for r in rows]

    def latest_for_conversation(
        self, conversation_id: str,
    ) -> CompactionRecord | None:
        with self._db.session() as s:
            row = s.execute(
                select(CompactionRow)
                .where(CompactionRow.conversation_id == conversation_id)
                .order_by(CompactionRow.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            return _row_to_record(row)

    def delete(self, record_id: str) -> None:
        with self._db.session() as s:
            s.execute(delete(CompactionRow).where(CompactionRow.id == record_id))

    def delete_descendants(self, record_id: str) -> int:
        """Delete ``record_id`` and every record whose ``parent_id`` chain
        leads back to it. Returns the number of rows removed.

        Used by ``/restore`` — once you re-inflate a snapshot, all later
        snapshots that were derived from the post-compaction view are no
        longer valid history.
        """
        with self._db.session() as s:
            # Collect the descendant set in Python; SQLite doesn't have
            # recursive CTE convenience here and the chain is short.
            all_rows = s.execute(
                select(CompactionRow.id, CompactionRow.parent_id)
            ).all()
        existing = {rid for rid, _ in all_rows}
        if record_id not in existing:
            return 0
        children: dict[str | None, list[str]] = {}
        for rid, pid in all_rows:
            children.setdefault(pid, []).append(rid)
        to_delete: list[str] = []
        stack = [record_id]
        while stack:
            current = stack.pop()
            to_delete.append(current)
            stack.extend(children.get(current, []))
        with self._db.session() as s:
            s.execute(
                delete(CompactionRow).where(CompactionRow.id.in_(to_delete))
            )
        return len(to_delete)

    def delete_for_conversation(self, conversation_id: str) -> None:
        with self._db.session() as s:
            s.execute(
                delete(CompactionRow).where(
                    CompactionRow.conversation_id == conversation_id
                )
            )


def _row_to_record(row: CompactionRow) -> CompactionRecord:
    return CompactionRecord(
        id=row.id,
        conversation_id=row.conversation_id,
        parent_id=row.parent_id,
        created_at=datetime.fromtimestamp(row.created_at, tz=timezone.utc),
        focus=row.focus,
        tokens_before=row.tokens_before,
        tokens_after=row.tokens_after,
        compacted_count=row.compacted_count,
        summary_text=row.summary_text,
        pre_compaction_messages=json.loads(row.pre_compaction_messages),
    )
