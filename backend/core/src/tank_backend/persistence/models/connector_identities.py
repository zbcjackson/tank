"""ConnectorIdentityRow — ORM model for (platform, external_id) → session_id."""

from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ConnectorIdentityRow(Base):
    """Maps a platform-native identity to a Tank session.

    Composite primary key ``(platform, external_id)`` guarantees a single
    row per external chat/user; attempts to re-insert are rejected at the
    DB layer, which is what the store's ``put_if_absent`` semantics rely
    on. ``session_id`` is the Tank conversation/session identifier
    returned by :class:`SessionMapper`.
    """

    __tablename__ = "connector_identities"

    platform:    Mapped[str] = mapped_column(String, primary_key=True)
    external_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id:  Mapped[str] = mapped_column(String, nullable=False)
    created_at:  Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("ix_connector_identities_session", "session_id"),
    )
