"""ConversationMessageRow — denormalised per-message rows for keyword search.

The canonical storage for conversation messages remains the ``conversations``
table's ``messages`` JSON blob. This table mirrors that JSON one row per
message so we can attach an FTS5 virtual table for keyword/CJK search
without parsing JSON on every query.

Maintained by :class:`ConversationMessagesStore`:
- ``replace_for_conversation`` is called on every persist (per-turn writes
  and post-compaction rewrites)
- the FTS5 virtual table is updated by SQLite triggers defined in the
  Alembic migration
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ConversationMessageRow(Base):
    """One row per message within a conversation."""

    __tablename__ = "conversation_messages"

    id:              Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq:             Mapped[int] = mapped_column(Integer, nullable=False)
    role:            Mapped[str] = mapped_column(String, nullable=False)
    content:         Mapped[str] = mapped_column(Text, nullable=False)
    created_at:      Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "seq", name="uq_conversation_messages_seq",
        ),
        Index(
            "ix_conversation_messages_created",
            "conversation_id", "created_at",
        ),
    )
