"""Persistent store for agent worker runs.

Phase 2 of the workflow & orchestration roadmap. Mirrors the shape of
``JobStore`` so the patterns the codebase already exercises apply
unchanged.

Workers (foreground and background ``agent`` dispatches) live in the
``worker_runs`` table. The store exposes pure data operations; the
``WorkerSupervisor`` drives the lifecycle on top.

See ``backend/ORCHESTRATION.md`` (Phase 2) for the surrounding design.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final, Literal

from sqlalchemy import CursorResult, func, select, update

from ..persistence import Database
from ..persistence.models import WorkerRunRow

logger = logging.getLogger(__name__)


WorkerStatus = Literal[
    "running", "waiting", "completed", "failed", "cancelled", "timeout",
]

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "timeout"},
)


# Sentinel for "any parent" in queries that filter by parent_task_id.
# We can't use ``None`` because that's a meaningful value (no parent).
class _Unset:
    """Singleton sentinel — distinguishes 'omitted' from 'None'."""

    _instance: _Unset | None = None

    def __new__(cls) -> _Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<UNSET>"


UNSET: Final = _Unset()


@dataclass(frozen=True)
class WorkerRun:
    """Domain dataclass; what callers see (never the ORM row directly)."""

    task_id: str
    agent_def: str
    description: str
    prompt: str
    status: str
    parent_task_id: str | None
    originating_conversation_id: str | None
    originating_channel: str | None
    parent_msg_id: str | None
    background: bool
    started_at: str
    completed_at: str | None
    output: str
    error: str | None
    question: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)


def _row_to_run(row: WorkerRunRow) -> WorkerRun:
    """Convert an ORM row to its frozen domain dataclass."""
    messages: list[dict[str, Any]] = []
    if row.messages_json:
        try:
            decoded = json.loads(row.messages_json)
            if isinstance(decoded, list):
                messages = decoded
        except json.JSONDecodeError:
            logger.warning(
                "Worker %s has invalid messages_json; treating as empty",
                row.task_id,
            )
    return WorkerRun(
        task_id=row.task_id,
        agent_def=row.agent_def,
        description=row.description,
        prompt=row.prompt,
        status=row.status,
        parent_task_id=row.parent_task_id,
        originating_conversation_id=row.originating_conversation_id,
        originating_channel=row.originating_channel,
        parent_msg_id=row.parent_msg_id,
        background=bool(row.background),
        started_at=row.started_at,
        completed_at=row.completed_at,
        output=row.output,
        error=row.error,
        question=row.question or "",
        messages=messages,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkerStore:
    """SQLite-backed store for worker run rows.

    Status transitions ``running → {completed, failed, cancelled, timeout}``
    are one-way; once terminal, a row is read-only.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        task_id: str,
        agent_def: str,
        prompt: str,
        description: str = "",
        parent_task_id: str | None = None,
        originating_conversation_id: str | None = None,
        originating_channel: str | None = None,
        parent_msg_id: str | None = None,
        background: bool = False,
    ) -> WorkerRun:
        """Insert a new ``running`` row and return its dataclass."""
        started_at = _now()
        with self._db.session() as s:
            row = WorkerRunRow(
                task_id=task_id,
                agent_def=agent_def,
                description=description,
                prompt=prompt,
                status="running",
                parent_task_id=parent_task_id,
                originating_conversation_id=originating_conversation_id,
                originating_channel=originating_channel,
                parent_msg_id=parent_msg_id,
                background=int(background),
                started_at=started_at,
                completed_at=None,
                output="",
                error=None,
                messages_json=None,
            )
            s.add(row)
        return WorkerRun(
            task_id=task_id,
            agent_def=agent_def,
            description=description,
            prompt=prompt,
            status="running",
            parent_task_id=parent_task_id,
            originating_conversation_id=originating_conversation_id,
            originating_channel=originating_channel,
            parent_msg_id=parent_msg_id,
            background=background,
            started_at=started_at,
            completed_at=None,
            output="",
            error=None,
            messages=[],
        )

    def finish(
        self,
        task_id: str,
        *,
        status: WorkerStatus,
        output: str = "",
        error: str | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Transition a row to a terminal status. Returns False if not found
        or already terminal."""
        if status not in TERMINAL_STATUSES:
            raise ValueError(
                f"finish() expects a terminal status, got {status!r}",
            )
        completed_at = _now()
        with self._db.session() as s:
            row = s.get(WorkerRunRow, task_id)
            if row is None:
                return False
            if row.status in TERMINAL_STATUSES:
                return False
            row.status = status
            row.completed_at = completed_at
            row.output = output
            row.error = error
            if messages is not None:
                row.messages_json = json.dumps(messages)
        return True

    def pause(
        self,
        task_id: str,
        *,
        output: str = "",
        question: str = "",
        messages: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Transition running → waiting. Persists accumulated output, question,
        and messages for later resumption. Returns False if not found or not running."""
        with self._db.session() as s:
            row = s.get(WorkerRunRow, task_id)
            if row is None or row.status != "running":
                return False
            row.status = "waiting"
            row.output = output
            row.question = question
            if messages is not None:
                row.messages_json = json.dumps(messages)
        return True

    def resume(self, task_id: str) -> bool:
        """Transition waiting → running. Returns False if not found or not waiting."""
        with self._db.session() as s:
            row = s.get(WorkerRunRow, task_id)
            if row is None or row.status != "waiting":
                return False
            row.status = "running"
            row.question = None
        return True

    def append_output(self, task_id: str, chunk: str) -> bool:
        """Append a chunk to ``output``. Used while a run is streaming.

        Returns False if the run is not found or already terminal.
        """
        if not chunk:
            return True
        with self._db.session() as s:
            row = s.get(WorkerRunRow, task_id)
            if row is None or row.status in TERMINAL_STATUSES:
                return False
            row.output = (row.output or "") + chunk
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, task_id: str) -> WorkerRun | None:
        with self._db.session() as s:
            row = s.get(WorkerRunRow, task_id)
            if row is None:
                return None
            return _row_to_run(row)

    def list_active(
        self, *, parent_task_id: str | None | _Unset = UNSET,
    ) -> list[WorkerRun]:
        """Return runs in ``status="running"``.

        ``parent_task_id`` filtering: pass an explicit value (including
        ``None``) to match that parent; omit to match any parent.
        """
        with self._db.session() as s:
            stmt = select(WorkerRunRow).where(WorkerRunRow.status == "running")
            if not isinstance(parent_task_id, _Unset):
                stmt = stmt.where(
                    WorkerRunRow.parent_task_id == parent_task_id,
                )
            stmt = stmt.order_by(WorkerRunRow.started_at)
            rows = s.execute(stmt).scalars().all()
            return [_row_to_run(r) for r in rows]

    def count_active(
        self, *, parent_task_id: str | None | _Unset = UNSET,
    ) -> int:
        """Count rows in ``status="running"`` for a given parent."""
        with self._db.session() as s:
            stmt = select(func.count()).select_from(WorkerRunRow).where(
                WorkerRunRow.status == "running",
            )
            if not isinstance(parent_task_id, _Unset):
                stmt = stmt.where(
                    WorkerRunRow.parent_task_id == parent_task_id,
                )
            return int(s.execute(stmt).scalar_one())

    def list_for_conversation(
        self, conversation_id: str, *, include_terminal: bool = True,
    ) -> list[WorkerRun]:
        """Return runs originating from a conversation, newest first."""
        with self._db.session() as s:
            stmt = select(WorkerRunRow).where(
                WorkerRunRow.originating_conversation_id == conversation_id,
            )
            if not include_terminal:
                stmt = stmt.where(WorkerRunRow.status == "running")
            stmt = stmt.order_by(WorkerRunRow.started_at.desc())
            rows = s.execute(stmt).scalars().all()
            return [_row_to_run(r) for r in rows]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def reap_running_on_startup(self, reason: str = "supervisor restart") -> int:
        """Reap rows left in ``running`` from a prior process.

        Called once at supervisor startup. Returns the number of rows
        marked ``cancelled``.
        """
        completed_at = _now()
        with self._db.session() as s:
            result = s.execute(
                update(WorkerRunRow)
                .where(WorkerRunRow.status == "running")
                .values(
                    status="cancelled",
                    completed_at=completed_at,
                    error=reason,
                ),
            )
            assert isinstance(result, CursorResult)  # noqa: S101
            count = int(result.rowcount or 0)
        if count:
            logger.info("Reaped %d running worker rows on startup", count)
        return count
