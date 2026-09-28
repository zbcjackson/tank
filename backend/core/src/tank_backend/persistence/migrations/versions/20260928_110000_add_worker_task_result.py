"""Persist versioned task outcomes separately from execution errors."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f2b8d5c9e3a7"
down_revision: str = "e1a9c4b7d2f6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("worker_runs", sa.Column("task_result_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("worker_runs", "task_result_json")
