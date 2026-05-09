"""JobRow + JobRunRow — ORM models for scheduled jobs and their run history."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class JobRow(Base):
    """One row per scheduled job. ``config_json`` holds the full JobDefinition."""

    __tablename__ = "jobs"

    id:          Mapped[str] = mapped_column(String, primary_key=True)
    name:        Mapped[str] = mapped_column(String, nullable=False, unique=True)
    prompt:      Mapped[str] = mapped_column(Text, nullable=False)
    schedule:    Mapped[str] = mapped_column(String, nullable=False)
    enabled:     Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    origin:      Mapped[str] = mapped_column(String, nullable=False, default="api")
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at:  Mapped[str] = mapped_column(String, nullable=False)
    updated_at:  Mapped[str] = mapped_column(String, nullable=False)


class JobRunRow(Base):
    """One row per job execution. Cascades when the parent job is deleted."""

    __tablename__ = "job_runs"

    id:          Mapped[str] = mapped_column(String, primary_key=True)
    job_id:      Mapped[str] = mapped_column(
        String,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status:      Mapped[str] = mapped_column(String, nullable=False)
    started_at:  Mapped[str | None] = mapped_column(String, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    output_path: Mapped[str | None] = mapped_column(String, nullable=True)
    error:       Mapped[str | None] = mapped_column(Text, nullable=True)
    stats_json:  Mapped[str | None] = mapped_column(Text, nullable=True)
