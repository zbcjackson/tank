"""add question column to worker_runs

Revision ID: c9d2e8f4a1b6
Revises: b7e4a9f1c8d3
Create Date: 2026-06-05 10:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c9d2e8f4a1b6'
down_revision: str | Sequence[str] | None = 'b7e4a9f1c8d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'worker_runs',
        sa.Column('question', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('worker_runs', 'question')
