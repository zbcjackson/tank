"""Tests for agents/store.py — SQLite worker run persistence (Phase 2)."""

from __future__ import annotations

import pytest

from tank_backend.agents.store import (
    TERMINAL_STATUSES,
    WorkerRun,
    WorkerStore,
)
from tank_backend.persistence import Base, Database


@pytest.fixture()
def store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    s = WorkerStore(db)
    yield s
    db.dispose()


def _create(
    store: WorkerStore,
    *,
    task_id: str = "t_001",
    agent_def: str = "researcher",
    prompt: str = "go research X",
    description: str = "research X",
    parent_task_id: str | None = None,
    originating_conversation_id: str | None = "conv_1",
    originating_channel: str | None = "voice:sess_1",
    background: bool = False,
) -> WorkerRun:
    return store.create(
        task_id=task_id,
        agent_def=agent_def,
        prompt=prompt,
        description=description,
        parent_task_id=parent_task_id,
        originating_conversation_id=originating_conversation_id,
        originating_channel=originating_channel,
        background=background,
    )


class TestCreateAndGet:
    def test_create_round_trip(self, store: WorkerStore):
        run = _create(store)
        assert run.task_id == "t_001"
        assert run.status == "running"
        assert run.background is False
        assert run.completed_at is None
        assert run.output == ""
        assert run.messages == []

        fetched = store.get("t_001")
        assert fetched is not None
        assert fetched.agent_def == "researcher"
        assert fetched.originating_conversation_id == "conv_1"
        assert fetched.originating_channel == "voice:sess_1"

    def test_get_nonexistent(self, store: WorkerStore):
        assert store.get("nope") is None

    def test_create_background_flag_persists(self, store: WorkerStore):
        _create(store, task_id="t_bg", background=True)
        run = store.get("t_bg")
        assert run is not None
        assert run.background is True


class TestStatusTransitions:
    def test_finish_completed(self, store: WorkerStore):
        _create(store)
        ok = store.finish("t_001", status="completed", output="done")
        assert ok is True
        run = store.get("t_001")
        assert run is not None
        assert run.status == "completed"
        assert run.output == "done"
        assert run.completed_at is not None
        assert run.error is None

    def test_finish_failed_records_error(self, store: WorkerStore):
        _create(store)
        ok = store.finish(
            "t_001", status="failed", output="", error="boom",
        )
        assert ok is True
        run = store.get("t_001")
        assert run is not None
        assert run.status == "failed"
        assert run.error == "boom"

    def test_finish_idempotent(self, store: WorkerStore):
        _create(store)
        assert store.finish("t_001", status="completed") is True
        # Second finish on a terminal row is rejected.
        assert store.finish("t_001", status="cancelled") is False
        run = store.get("t_001")
        assert run is not None
        assert run.status == "completed"

    def test_finish_unknown(self, store: WorkerStore):
        assert store.finish("nope", status="completed") is False

    def test_finish_rejects_non_terminal(self, store: WorkerStore):
        _create(store)
        with pytest.raises(ValueError):
            store.finish("t_001", status="running")  # type: ignore[arg-type]

    def test_terminal_statuses_constant(self):
        assert frozenset(
            {"completed", "failed", "cancelled", "timeout"},
        ) == TERMINAL_STATUSES

    def test_finish_persists_messages(self, store: WorkerStore):
        _create(store)
        msgs = [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "ok"},
        ]
        store.finish("t_001", status="completed", output="ok", messages=msgs)
        run = store.get("t_001")
        assert run is not None
        assert run.messages == msgs


class TestAppendOutput:
    def test_append_to_running(self, store: WorkerStore):
        _create(store)
        assert store.append_output("t_001", "hello ") is True
        assert store.append_output("t_001", "world") is True
        run = store.get("t_001")
        assert run is not None
        assert run.output == "hello world"

    def test_append_to_terminal_is_rejected(self, store: WorkerStore):
        _create(store)
        store.finish("t_001", status="completed", output="final")
        assert store.append_output("t_001", "more") is False
        run = store.get("t_001")
        assert run is not None
        assert run.output == "final"

    def test_append_empty_chunk_is_noop(self, store: WorkerStore):
        _create(store)
        assert store.append_output("t_001", "") is True
        run = store.get("t_001")
        assert run is not None
        assert run.output == ""


class TestActiveQueries:
    def test_list_active_excludes_terminal(self, store: WorkerStore):
        _create(store, task_id="t_run")
        _create(store, task_id="t_done")
        store.finish("t_done", status="completed")

        active = store.list_active()
        assert [r.task_id for r in active] == ["t_run"]

    def test_count_active_filters_by_parent(self, store: WorkerStore):
        # Two runs under parent A, one under parent B, one orphan.
        _create(store, task_id="a1", parent_task_id="A")
        _create(store, task_id="a2", parent_task_id="A")
        _create(store, task_id="b1", parent_task_id="B")
        _create(store, task_id="orphan", parent_task_id=None)

        assert store.count_active() == 4
        assert store.count_active(parent_task_id="A") == 2
        assert store.count_active(parent_task_id="B") == 1
        assert store.count_active(parent_task_id=None) == 1

    def test_count_active_ignores_terminal(self, store: WorkerStore):
        _create(store, task_id="a1", parent_task_id="A")
        _create(store, task_id="a2", parent_task_id="A")
        store.finish("a1", status="completed")
        assert store.count_active(parent_task_id="A") == 1


class TestConversationQueries:
    def test_list_for_conversation(self, store: WorkerStore):
        _create(
            store, task_id="c1_old", originating_conversation_id="conv_X",
        )
        _create(
            store, task_id="c1_new", originating_conversation_id="conv_X",
        )
        _create(
            store, task_id="other", originating_conversation_id="conv_Y",
        )
        runs = store.list_for_conversation("conv_X")
        # Newest first.
        assert [r.task_id for r in runs] == ["c1_new", "c1_old"]

    def test_list_for_conversation_active_only(self, store: WorkerStore):
        _create(
            store, task_id="r1", originating_conversation_id="conv",
        )
        _create(
            store, task_id="r2", originating_conversation_id="conv",
        )
        store.finish("r1", status="completed")
        active = store.list_for_conversation("conv", include_terminal=False)
        assert [r.task_id for r in active] == ["r2"]


class TestReapRunningOnStartup:
    def test_reap_marks_running_as_cancelled(self, store: WorkerStore):
        _create(store, task_id="zombie_1")
        _create(store, task_id="zombie_2")
        _create(store, task_id="finished")
        store.finish("finished", status="completed")

        count = store.reap_running_on_startup()
        assert count == 2

        z1 = store.get("zombie_1")
        z2 = store.get("zombie_2")
        f = store.get("finished")
        assert z1 is not None and z1.status == "cancelled"
        assert z2 is not None and z2.status == "cancelled"
        # The reaper writes a non-empty error reason.
        assert z1.error
        assert f is not None and f.status == "completed"

    def test_reap_on_clean_db_returns_zero(self, store: WorkerStore):
        assert store.reap_running_on_startup() == 0
