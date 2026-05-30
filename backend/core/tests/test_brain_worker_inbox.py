"""Brain integration test for the worker inbox flow.

Phase 2 step 6 of the workflow & orchestration roadmap. Pins the
contract that terminal background-worker completions get surfaced
into the conversation as synthetic ``system`` messages right before
the next user turn.

This is the integration test the inbox observer's unit tests
*don't* cover: that Brain actually calls ``inbox.drain`` and feeds
the result through ``ContextManager.add_message`` so the LLM sees
the worker output in context.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest
from brain_test_helpers import make_brain, make_mock_context

from tank_backend.agents.worker_inbox import WorkerCompletion, WorkerInboxObserver
from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import BrainConfig


async def _collect(processor, item):
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


@pytest.fixture
def bus():
    return Bus()


@pytest.fixture
def mock_context():
    ctx = make_mock_context()
    ctx.conversation_id = "conv_a"
    return ctx


@pytest.fixture
def brain(bus, mock_context):
    return make_brain(
        llm=MagicMock(),
        tool_manager=MagicMock(),
        config=BrainConfig(),
        bus=bus,
        interrupt_event=threading.Event(),
        context=mock_context,
    )


class TestBrainSurfacesWorkerInbox:
    async def test_no_inbox_wired_is_noop(self, brain, mock_context):
        # ``_worker_inbox`` defaults to None when no WorkerStore is
        # injected. Brain must still process turns normally.
        event = BrainInputEvent(
            type=InputType.TEXT, text="hi", user="u",
            language="en", confidence=None,
        )
        brain._tool_manager.get_openai_tools.return_value = []
        await _collect(brain, event)
        # No system message should have been injected.
        for call in mock_context.add_message.call_args_list:
            assert call.args[0] != "system"

    async def test_drains_inbox_and_injects_system_messages(
        self, brain, mock_context,
    ):
        # Wire a real inbox and pre-load it.
        inbox = WorkerInboxObserver(bus=None)
        brain._worker_inbox = inbox
        completion = WorkerCompletion(
            task_id="t_1",
            agent_def="coder",
            description="trip plan",
            status="completed",
            output="paris in june",
            error=None,
            originating_channel=None,
        )
        # Manually queue (bypasses bus to keep the test focused on the
        # drain path).
        with inbox._lock:  # noqa: SLF001
            inbox._inbox["conv_a"] = [completion]  # noqa: SLF001

        brain._tool_manager.get_openai_tools.return_value = []
        event = BrainInputEvent(
            type=InputType.TEXT, text="ok", user="u",
            language="en", confidence=None,
        )
        await _collect(brain, event)

        # Brain should have surfaced the completion as a system msg
        # BEFORE prepare_turn was called for the user turn.
        system_calls = [
            c for c in mock_context.add_message.call_args_list
            if c.args[0] == "system"
        ]
        assert len(system_calls) == 1
        body = system_calls[0].args[1]
        assert "trip plan" in body
        assert "paris in june" in body

        # Inbox should now be empty (drain is destructive).
        assert inbox.peek("conv_a") == []

    async def test_drain_only_pulls_for_active_conversation(
        self, brain, mock_context,
    ):
        inbox = WorkerInboxObserver(bus=None)
        brain._worker_inbox = inbox
        # Queue under a different conversation id.
        with inbox._lock:  # noqa: SLF001
            inbox._inbox["conv_b"] = [  # noqa: SLF001
                WorkerCompletion(
                    task_id="t_x", agent_def="coder",
                    description="x", status="completed",
                    output="x", error=None, originating_channel=None,
                ),
            ]
        brain._tool_manager.get_openai_tools.return_value = []
        event = BrainInputEvent(
            type=InputType.TEXT, text="ok", user="u",
            language="en", confidence=None,
        )
        await _collect(brain, event)

        # No system message injected — the conv_b entry stays queued.
        for call in mock_context.add_message.call_args_list:
            assert call.args[0] != "system"
        assert len(inbox.peek("conv_b")) == 1
