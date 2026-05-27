"""add conversation_messages + FTS5 index

Phase B / IMP-8 — hybrid memory recall. Adds a denormalised
``conversation_messages`` table mirroring each conversation's messages
list, plus an FTS5 virtual table over the ``content`` column for
keyword search (CJK-friendly via the trigram tokenizer that ships with
SQLite ≥ 3.45).

The migration:
1. Creates the ``conversation_messages`` row table.
2. Creates the ``conversation_messages_fts`` virtual table.
3. Wires SQLite triggers so future writes to the row table cascade
   into the FTS index.
4. Backfills rows from existing ``conversations.messages`` JSON.

Downgrade drops the FTS table, triggers, and row table — leaves the
``conversations`` JSON blob untouched.

Revision ID: f9c3b1e7d2a4
Revises: e4b2a8d3f1c0
Create Date: 2026-05-26 04:00:00.000000+00:00

"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f9c3b1e7d2a4'
down_revision: str | Sequence[str] | None = 'e4b2a8d3f1c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


logger = logging.getLogger("alembic")


def upgrade() -> None:
    op.create_table(
        'conversation_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.String(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'], ['conversations.conversation_id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'conversation_id', 'seq',
            name='uq_conversation_messages_seq',
        ),
    )
    op.create_index(
        'ix_conversation_messages_conversation_id',
        'conversation_messages',
        ['conversation_id'],
        unique=False,
    )
    op.create_index(
        'ix_conversation_messages_created',
        'conversation_messages',
        ['conversation_id', 'created_at'],
        unique=False,
    )

    bind = op.get_bind()

    # FTS5 virtual table — content-rowid mode means the FTS table
    # references our base table's rowid (the autoincrement ``id``).
    bind.exec_driver_sql("""
        CREATE VIRTUAL TABLE conversation_messages_fts USING fts5(
            content,
            content='conversation_messages',
            content_rowid='id',
            tokenize='trigram'
        )
    """)

    # Triggers keep the FTS table in sync with the base table.
    bind.exec_driver_sql("""
        CREATE TRIGGER conversation_messages_ai
        AFTER INSERT ON conversation_messages
        BEGIN
            INSERT INTO conversation_messages_fts(rowid, content)
            VALUES (new.id, new.content);
        END
    """)
    bind.exec_driver_sql("""
        CREATE TRIGGER conversation_messages_ad
        AFTER DELETE ON conversation_messages
        BEGIN
            INSERT INTO conversation_messages_fts(
                conversation_messages_fts, rowid, content
            ) VALUES ('delete', old.id, old.content);
        END
    """)
    bind.exec_driver_sql("""
        CREATE TRIGGER conversation_messages_au
        AFTER UPDATE ON conversation_messages
        BEGIN
            INSERT INTO conversation_messages_fts(
                conversation_messages_fts, rowid, content
            ) VALUES ('delete', old.id, old.content);
            INSERT INTO conversation_messages_fts(rowid, content)
            VALUES (new.id, new.content);
        END
    """)

    # Backfill from existing conversations. This is the only place we
    # parse the JSON column; subsequent writes flow through
    # ConversationMessagesStore.
    rows = bind.execute(sa.text(
        "SELECT conversation_id, messages, updated_at FROM conversations"
    )).fetchall()

    backfilled = 0
    for conv_id, messages_json, updated_at in rows:
        try:
            messages = json.loads(messages_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(messages, list):
            continue
        base_ts = float(updated_at) if updated_at is not None else time.time()
        for seq, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            content = msg.get("content")
            if not isinstance(role, str) or not role:
                continue
            text = _coerce_content(content)
            if not text:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO conversation_messages "
                    "(conversation_id, seq, role, content, created_at) "
                    "VALUES (:cid, :seq, :role, :content, :ts)"
                ),
                {
                    "cid": conv_id,
                    "seq": seq,
                    "role": role,
                    "content": text,
                    "ts": base_ts,
                },
            )
            backfilled += 1

    if backfilled:
        logger.info(
            "Backfilled %d message rows into conversation_messages",
            backfilled,
        )


def _coerce_content(content: object) -> str:
    """Best-effort string extraction for FTS indexing."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        # OpenAI-style content parts list. Pull text from each.
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts).strip()
    return ""


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP TRIGGER IF EXISTS conversation_messages_au")
    bind.exec_driver_sql("DROP TRIGGER IF EXISTS conversation_messages_ad")
    bind.exec_driver_sql("DROP TRIGGER IF EXISTS conversation_messages_ai")
    bind.exec_driver_sql("DROP TABLE IF EXISTS conversation_messages_fts")
    op.drop_index(
        'ix_conversation_messages_created',
        table_name='conversation_messages',
    )
    op.drop_index(
        'ix_conversation_messages_conversation_id',
        table_name='conversation_messages',
    )
    op.drop_table('conversation_messages')
