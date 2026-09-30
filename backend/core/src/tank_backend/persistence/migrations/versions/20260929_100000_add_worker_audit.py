"""Persist append-only task call audit metadata."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a6c8e2f4b9d1"
down_revision: str = "f2b8d5c9e3a7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "worker_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("call_id", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.String(), nullable=False),
        sa.Column("record_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["worker_runs.task_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_audit_events_task_id", "worker_audit_events", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_worker_audit_events_task_id", table_name="worker_audit_events")
    op.drop_table("worker_audit_events")
