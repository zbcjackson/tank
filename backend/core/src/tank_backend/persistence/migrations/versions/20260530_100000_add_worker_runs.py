"""add worker_runs table

Phase 2 of the workflow & orchestration roadmap (see
``backend/ORCHESTRATION.md``). One row per ``agent`` tool dispatch —
foreground and background share this table.

Revision ID: b7e4a9f1c8d3
Revises: a1f3d2b5e6c7
Create Date: 2026-05-30 10:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e4a9f1c8d3'
down_revision: str | Sequence[str] | None = 'a1f3d2b5e6c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'worker_runs',
        sa.Column('task_id', sa.String(), primary_key=True),
        sa.Column('agent_def', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=False, server_default=''),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('parent_task_id', sa.String(), nullable=True),
        sa.Column('originating_conversation_id', sa.String(), nullable=True),
        sa.Column('originating_channel', sa.String(), nullable=True),
        sa.Column('parent_msg_id', sa.String(), nullable=True),
        sa.Column('background', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.String(), nullable=False),
        sa.Column('completed_at', sa.String(), nullable=True),
        sa.Column('output', sa.Text(), nullable=False, server_default=''),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('messages_json', sa.Text(), nullable=True),
    )
    op.create_index(
        'ix_worker_runs_status', 'worker_runs', ['status'],
    )
    op.create_index(
        'ix_worker_runs_parent_task_id', 'worker_runs', ['parent_task_id'],
    )
    op.create_index(
        'ix_worker_runs_originating_conversation_id',
        'worker_runs', ['originating_conversation_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_worker_runs_originating_conversation_id', table_name='worker_runs')
    op.drop_index('ix_worker_runs_parent_task_id', table_name='worker_runs')
    op.drop_index('ix_worker_runs_status', table_name='worker_runs')
    op.drop_table('worker_runs')
