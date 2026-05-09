"""ConversationRow — ORM model matching the legacy ``conversations`` schema."""

from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ConversationRow(Base):
    """One row per persisted conversation.

    Schema mirrors the legacy ``SqliteConversationStore`` exactly so the
    lift-and-shift bootstrap can plain-copy rows. ``messages`` is a JSON
    string (``json.dumps(conversation.messages)``); decoding is the store's
    job, not the ORM's.
    """

    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String, primary_key=True)
    start_time:      Mapped[str] = mapped_column(String, nullable=False)
    pid:             Mapped[int] = mapped_column(Integer, nullable=False)
    messages:        Mapped[str] = mapped_column(Text, nullable=False)
    updated_at:      Mapped[float] = mapped_column(Float, nullable=False)
