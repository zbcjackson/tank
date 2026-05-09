"""ChannelRow + ChannelReadStateRow — ORM models for channel metadata."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ChannelRow(Base):
    """One row per channel. Messages live in the conversation it references."""

    __tablename__ = "channels"

    slug:            Mapped[str] = mapped_column(String, primary_key=True)
    name:            Mapped[str] = mapped_column(String, nullable=False)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    description:     Mapped[str] = mapped_column(String, nullable=False, default="")
    auto_created:    Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at:      Mapped[str] = mapped_column(String, nullable=False)
    updated_at:      Mapped[str] = mapped_column(String, nullable=False)


class ChannelReadStateRow(Base):
    """Per-channel last-read marker. 1:1 with channels, cascades on delete."""

    __tablename__ = "channel_read_state"

    slug: Mapped[str] = mapped_column(
        String,
        ForeignKey("channels.slug", ondelete="CASCADE"),
        primary_key=True,
    )
    last_read_message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
