"""WorkerRunRow — ORM model for agent worker runs (Phase 2 of orchestration).

One row per ``agent`` tool dispatch. Foreground and background dispatches
share the same row shape; the ``background`` flag distinguishes them.

See ``backend/ORCHESTRATION.md`` (Phase 2) for the surrounding design.
"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class WorkerRunRow(Base):
    """One row per agent dispatch — foreground and background."""

    __tablename__ = "worker_runs"

    task_id:                     Mapped[str] = mapped_column(String, primary_key=True)
    agent_def:                   Mapped[str] = mapped_column(String, nullable=False)
    description:                 Mapped[str] = mapped_column(String, nullable=False, default="")
    prompt:                      Mapped[str] = mapped_column(Text, nullable=False)

    # "running" | "completed" | "failed" | "cancelled" | "timeout"
    status:                      Mapped[str] = mapped_column(String, nullable=False, index=True)

    parent_task_id:              Mapped[str | None] = mapped_column(
        String, nullable=True, index=True,
    )
    originating_conversation_id: Mapped[str | None] = mapped_column(
        String, nullable=True, index=True,
    )
    # Examples: "voice:<session>", "channel:<slug>", "telegram:<chat_id>".
    originating_channel:         Mapped[str | None] = mapped_column(String, nullable=True)
    parent_msg_id:               Mapped[str | None] = mapped_column(String, nullable=True)

    background:                  Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at:                  Mapped[str] = mapped_column(String, nullable=False)
    completed_at:                Mapped[str | None] = mapped_column(String, nullable=True)

    output:                      Mapped[str] = mapped_column(Text, nullable=False, default="")
    error:                       Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON-encoded list of OpenAI messages; populated for resumable runs.
    messages_json:               Mapped[str | None] = mapped_column(Text, nullable=True)
