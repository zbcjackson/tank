"""Append-only task call audit rows, independent of lossy telemetry."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class WorkerAuditRow(Base):
    __tablename__ = "worker_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("worker_runs.task_id"), index=True)
    call_id: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[str] = mapped_column(String, nullable=False)
    record_json: Mapped[str] = mapped_column(Text, nullable=False)
