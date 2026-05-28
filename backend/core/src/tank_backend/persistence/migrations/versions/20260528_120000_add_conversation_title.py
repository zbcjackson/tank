"""add conversation title column

Adds a nullable ``title`` column to the ``conversations`` table so each
conversation can carry a short human-readable label. Title generation
is LLM-driven on the first assistant turn; existing rows stay NULL
until the user opens the rename modal and clicks Regenerate.

Revision ID: a1f3d2b5e6c7
Revises: f9c3b1e7d2a4
Create Date: 2026-05-28 12:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1f3d2b5e6c7'
down_revision: str | Sequence[str] | None = 'f9c3b1e7d2a4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('title', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('conversations', 'title')
