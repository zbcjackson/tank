"""migrate telegram identity prefix: dm tg:chat -> tg:user

Phase 6 splits the Telegram identity space so DMs key on the user
(``tg:user:{id}``) and groups key on the chat (``tg:chat:{id}``). The
split matters for allowlists — operators want to say "allow Alice"
without enumerating every 1:1 room she happens to occupy.

Before this migration, both DMs and groups were stored as
``tg:chat:{id}``. Telegram assigns **positive** chat ids to DMs and
**negative** ids to groups / supergroups / channels, so we can
distinguish them numerically:

- ``tg:chat:42``        → DM with user 42 → rewrite to ``tg:user:42``
- ``tg:chat:-1001234567`` → supergroup → leave as-is

Only ``platform='telegram'`` rows are touched. Other platforms (Slack,
Feishu, etc.) have their own prefix conventions and aren't affected.

Reversible: ``downgrade()`` rewrites ``tg:user:*`` back to ``tg:chat:*``.
A round-trip is a no-op by construction.

Revision ID: 7f3b1d9c5a04
Revises: a3f9c2e1b8d4
Create Date: 2026-05-11 07:52:35.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7f3b1d9c5a04'
down_revision: str | Sequence[str] | None = 'a3f9c2e1b8d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rewrite DM rows: tg:chat:<positive int> -> tg:user:<positive int>.
    #
    # SQLite supports ``CAST(... AS INTEGER)`` and arithmetic comparisons
    # on text columns that happen to hold numeric strings. We match
    # "positive integer body" via ``CAST(substr(external_id, 9) AS INTEGER) > 0``
    # — position 9 is 1-indexed start of the body after the ``tg:chat:``
    # prefix (8 chars).
    op.execute(
        """
        UPDATE connector_identities
        SET external_id = 'tg:user:' || substr(external_id, 9)
        WHERE platform = 'telegram'
          AND external_id LIKE 'tg:chat:%'
          AND CAST(substr(external_id, 9) AS INTEGER) > 0
        """,
    )


def downgrade() -> None:
    # Inverse: rewrite tg:user:* back to tg:chat:* so a round-trip is
    # a no-op.
    op.execute(
        """
        UPDATE connector_identities
        SET external_id = 'tg:chat:' || substr(external_id, 9)
        WHERE platform = 'telegram'
          AND external_id LIKE 'tg:user:%'
        """,
    )
