"""Tests for WorkerInboxObserver — surfaces background completions to a conversation.

Phase 2 step 4. The observer subscribes to ``BusMessage(type="worker")``,
queues terminal completions per ``originating_conversation_id``, and
exposes ``drain`` for Brain to call at the start of a turn.
"""

from __future__ import annotations

from tank_backend.agents.worker_inbox import WorkerInboxObserver
from tank_backend.pipeline.bus import Bus, BusMessage


def _post(bus: Bus, **payload) -> None:
    """Post a worker bus event and immediately dispatch."""
    bus.post(BusMessage(
        type="worker",
        source="worker_supervisor",
        payload=payload,
    ))
    bus.poll()


def test_terminal_event_queued_under_conversation_id():
    bus = Bus()
    inbox = WorkerInboxObserver(bus)
    _post(
        bus,
        event="completed",
        task_id="t_1",
        agent_def="coder",
        description="research X",
        originating_conversation_id="conv_a",
        originating_channel="voice:s1",
        status="completed",
        output="found three options",
    )

    pending = inbox.drain("conv_a")
    assert len(pending) == 1
    completion = pending[0]
    assert completion.task_id == "t_1"
    assert completion.agent_def == "coder"
    assert completion.description == "research X"
    assert completion.status == "completed"
    assert completion.output == "found three options"


def test_drain_is_destructive_per_conversation():
    bus = Bus()
    inbox = WorkerInboxObserver(bus)
    _post(
        bus, event="completed", task_id="t_1", agent_def="x",
        description="d", originating_conversation_id="conv_a",
        status="completed", output="o",
    )
    assert inbox.drain("conv_a")
    # Second drain returns empty — first call removed the items.
    assert inbox.drain("conv_a") == []


def test_non_terminal_events_are_ignored():
    bus = Bus()
    inbox = WorkerInboxObserver(bus)
    _post(
        bus, event="started", task_id="t_1", agent_def="x",
        description="d", originating_conversation_id="conv_a",
    )
    assert inbox.drain("conv_a") == []


def test_events_without_conversation_id_are_dropped():
    bus = Bus()
    inbox = WorkerInboxObserver(bus)
    _post(
        bus, event="completed", task_id="t_1", agent_def="x",
        description="d", status="completed", output="o",
    )
    # No conversation id was attached — nothing to surface.
    assert not inbox.has_pending("conv_a")


def test_multiple_completions_preserve_order_per_conversation():
    bus = Bus()
    inbox = WorkerInboxObserver(bus)
    for i in range(3):
        _post(
            bus, event="completed", task_id=f"t_{i}", agent_def="x",
            description=f"d{i}", originating_conversation_id="conv_a",
            status="completed", output=f"o{i}",
        )
    pending = inbox.drain("conv_a")
    assert [c.task_id for c in pending] == ["t_0", "t_1", "t_2"]


def test_render_failed_completion_includes_error():
    bus = Bus()
    inbox = WorkerInboxObserver(bus)
    _post(
        bus, event="failed", task_id="t_1", agent_def="x",
        description="research", originating_conversation_id="conv_a",
        status="failed", output="partial...", error="kaboom",
    )
    completion = inbox.drain("conv_a")[0]
    rendered = completion.to_system_message()
    assert "research" in rendered
    assert "failed" in rendered
    assert "kaboom" in rendered


def test_render_completed_uses_output_body():
    bus = Bus()
    inbox = WorkerInboxObserver(bus)
    _post(
        bus, event="completed", task_id="t_1", agent_def="coder",
        description="trip plan", originating_conversation_id="conv_a",
        status="completed", output="paris in june",
    )
    completion = inbox.drain("conv_a")[0]
    rendered = completion.to_system_message()
    assert "trip plan" in rendered
    assert "completed" in rendered
    assert "paris in june" in rendered
