"""add connector_identities

Revision ID: a3f9c2e1b8d4
Revises: 02d48761b1bc
Create Date: 2026-05-09 14:27:47.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f9c2e1b8d4'
down_revision: str | Sequence[str] | None = '02d48761b1bc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'connector_identities',
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('external_id', sa.String(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('platform', 'external_id'),
    )
    op.create_index(
        'ix_connector_identities_session',
        'connector_identities',
        ['session_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_connector_identities_session', table_name='connector_identities')
    op.drop_table('connector_identities')
