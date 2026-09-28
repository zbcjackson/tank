"""Persist structured plugin task input independently of chat history."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e1a9c4b7d2f6"
down_revision: str = "d3f5b7a2e9c1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("worker_runs", sa.Column("task_input_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("worker_runs", "task_input_json")
