"""SpeakerRow + EmbeddingRow — ORM models for voiceprint storage.

Embeddings are stored as BLOB (``numpy.float32`` bytes). Translation between
``np.ndarray`` and bytes stays in the repository — keeping the ORM layer
dependency-free of numpy.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class SpeakerRow(Base):
    """One row per enrolled speaker."""

    __tablename__ = "speakers"

    user_id:    Mapped[str] = mapped_column(String, primary_key=True)
    name:       Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[float] = mapped_column(Float, nullable=False)


class EmbeddingRow(Base):
    """Many-to-one with speakers: each enrollment appends one embedding."""

    __tablename__ = "embeddings"

    id:         Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:    Mapped[str] = mapped_column(
        String,
        ForeignKey("speakers.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding:  Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
