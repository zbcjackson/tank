"""add compactions table

Phase B / IMP-7 — compaction lineage. Records the messages that were
summarized away during a destructive compaction so a user can list and
restore previous revisions of a conversation.

``parent_id`` chains successive compactions on the same conversation;
``ON DELETE CASCADE`` against ``conversations`` ensures rows go away when
the underlying conversation is deleted.

Revision ID: e4b2a8d3f1c0
Revises: c8a5d1e9f4b2
Create Date: 2026-05-26 03:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4b2a8d3f1c0'
down_revision: str | Sequence[str] | None = 'c8a5d1e9f4b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'compactions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('conversation_id', sa.String(), nullable=False),
        sa.Column('parent_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('focus', sa.String(), nullable=True),
        sa.Column('tokens_before', sa.Integer(), nullable=False),
        sa.Column('tokens_after', sa.Integer(), nullable=False),
        sa.Column('compacted_count', sa.Integer(), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=False),
        sa.Column('pre_compaction_messages', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'], ['conversations.conversation_id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['parent_id'], ['compactions.id'], ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_compactions_conversation_id',
        'compactions',
        ['conversation_id'],
        unique=False,
    )
    op.create_index(
        'ix_compactions_conversation_created',
        'compactions',
        ['conversation_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_compactions_conversation_created', table_name='compactions',
    )
    op.drop_index(
        'ix_compactions_conversation_id', table_name='compactions',
    )
    op.drop_table('compactions')
