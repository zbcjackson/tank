"""add command_approvals table

Revision ID: d3f5b7a2e9c1
Revises: c9d2e8f4a1b6
Create Date: 2026-06-08 10:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd3f5b7a2e9c1'
down_revision: str | Sequence[str] | None = 'c9d2e8f4a1b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "command_approvals",
        sa.Column("command_pattern", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("command_pattern"),
    )


def downgrade() -> None:
    op.drop_table("command_approvals")
