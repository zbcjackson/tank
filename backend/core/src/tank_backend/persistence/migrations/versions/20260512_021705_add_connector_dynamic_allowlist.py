"""add connector_dynamic_allowlist

Phase 10 persists admin-granted connector allowlist entries. Separate
from the static, config-declared rules — these are written at runtime
by the :class:`ApprovalBroker` when an admin clicks **Allow forever**
on an approval prompt.

Composite primary key ``(instance_name, platform, external_id)`` makes
``grant()`` idempotent at the DB layer: repeated inserts of the same
triple are rejected with an IntegrityError that the store catches and
treats as a successful no-op.

Revision ID: c8a5d1e9f4b2
Revises: 7f3b1d9c5a04
Create Date: 2026-05-12 02:17:05.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8a5d1e9f4b2'
down_revision: str | Sequence[str] | None = '7f3b1d9c5a04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'connector_dynamic_allowlist',
        sa.Column('instance_name', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('external_id', sa.String(), nullable=False),
        sa.Column('granted_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint(
            'instance_name', 'platform', 'external_id',
            name='pk_connector_dynamic_allowlist',
        ),
    )
    op.create_index(
        'ix_connector_dynamic_allowlist_instance_platform',
        'connector_dynamic_allowlist',
        ['instance_name', 'platform'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_connector_dynamic_allowlist_instance_platform',
        table_name='connector_dynamic_allowlist',
    )
    op.drop_table('connector_dynamic_allowlist')
