"""CompactionRow — ORM model for the per-conversation compaction lineage."""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class CompactionRow(Base):
    """One row per destructive compaction of a conversation.

    ``pre_compaction_messages`` is the JSON-encoded list of messages that
    were summarized away — keeping it lets ``/restore`` re-inflate the
    conversation. ``parent_id`` chains successive compactions on the same
    conversation so a restore can clean up descendants.
    """

    __tablename__ = "compactions"

    id:                      Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id:         Mapped[str] = mapped_column(
        String,
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id:               Mapped[str | None] = mapped_column(
        String,
        ForeignKey("compactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at:              Mapped[float] = mapped_column(Float, nullable=False)
    focus:                   Mapped[str | None] = mapped_column(String, nullable=True)
    tokens_before:           Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_after:            Mapped[int] = mapped_column(Integer, nullable=False)
    compacted_count:         Mapped[int] = mapped_column(Integer, nullable=False)
    summary_text:            Mapped[str] = mapped_column(Text, nullable=False)
    pre_compaction_messages: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index(
            "ix_compactions_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )
