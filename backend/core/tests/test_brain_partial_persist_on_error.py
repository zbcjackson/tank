"""Regression for the Phase 19 follow-up: partial-persist on Brain error.

The failure mode: a chart turn rendered live (user saw the image),
but the next iteration of the same ``chat_stream`` 400'd at the LLM
provider. Brain's generic ``except Exception`` handler in
``_process_via_agents`` re-raised without calling ``_finish_turn``,
which meant the tool_call, tool result, and follow-up image were
all dropped from history. Resume showed only the user's request.

The fix mirrors the ``BrainInterrupted`` branch: persist whatever
turn messages accumulated before re-raising. These tests pin both
error paths (main agent and confirmation agent) so the regression
can't recur.
"""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest
from brain_test_helpers import make_brain

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType
from tank_backend.agents.graph import AgentGraph
from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import BrainConfig


class _MidStreamFailingAgent(Agent):
    """Agent that yields a tool MESSAGE then raises before DONE.

    Simulates the chart scenario: tool ran successfully, MESSAGE event
    captured a tool_call + tool result + follow-up in
    ``state.metadata["turn_messages"]``, then the next LLM iteration
    failed (provider 400). Brain's stream loop sees the exception
    propagate up from the generator.
    """

    def __init__(self, partial_messages: list[dict]) -> None:
        super().__init__("chat")
        self._partial_messages = partial_messages

    async def run(self, state) -> AsyncIterator[AgentOutput]:
        # Populate turn_messages so Brain's error handler has
        # something concrete to persist.
        existing = state.metadata.get("turn_messages", [])
        existing.extend(self._partial_messages)
        state.metadata["turn_messages"] = existing

        # Yield a token so Brain enters the streaming branch.
        yield AgentOutput(
            type=AgentOutputType.TOKEN,
            content="partial",
            metadata={"turn": 1},
        )
        # Now raise — mimics the LLM provider rejecting the follow-up
        # message inside ``chat_stream`` and the exception bubbling up
        # through the agent.
        raise RuntimeError("synthetic LLM 400")


def _make_brain_with_failing_agent(partial_messages: list[dict]):
    bus = Bus()
    llm = MagicMock()
    tool_manager = MagicMock()
    tool_manager.get_openai_tools.return_value = []
    interrupt_event = threading.Event()
    config = BrainConfig(max_history_tokens=8000)

    failing_agent = _MidStreamFailingAgent(partial_messages)
    agent_graph = AgentGraph(
        agents={"chat": failing_agent}, default_agent="chat",
    )

    brain = make_brain(
        llm=llm,
        tool_manager=tool_manager,
        config=config,
        bus=bus,
        interrupt_event=interrupt_event,
        tts_enabled=False,
        agent_graph=agent_graph,
    )
    return brain, bus


class TestPartialPersistOnAgentError:
    """The regression: a turn that produces real tool output (tool_call,
    tool result, follow-up image) but then 400s at the next LLM
    iteration must persist what it has, not drop everything."""

    def test_chart_turn_partial_state_persists_on_llm_error(self) -> None:
        """End-to-end: a tool call + tool result + image follow-up
        accumulate in ``turn_messages`` before the LLM 400s. Brain's
        ``_finish_turn`` should still run on the error path so resume
        sees the chart that actually rendered live, not just the
        user's request."""
        partial = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "tc_1",
                    "type": "function",
                    "function": {
                        "name": "render_chart", "arguments": "{}",
                    },
                }],
            },
            {
                "role": "tool",
                "content": "[chart sent]",
                "tool_call_id": "tc_1",
                "name": "render_chart",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "media://s/x.png"},
                    },
                ],
                "metadata": {
                    "tool_follow_up": True,
                    "tool_call_id": "tc_1",
                },
            },
        ]
        brain, _bus = _make_brain_with_failing_agent(partial)

        # Drive a turn through Brain. The agent yields one token then
        # raises; ``_process_via_agents`` catches the RuntimeError,
        # calls ``_finish_turn(turn_messages)``, and re-raises;
        # ``Brain.process`` then catches the propagated error at the
        # outer ``except Exception`` and yields a user-facing error
        # message rather than raising. Both paths together implement
        # the contract: the user sees a "Sorry, an error occurred"
        # message AND history captures whatever the tool already did.
        event = BrainInputEvent(
            type=InputType.TEXT,
            text="plot Q1-Q4 revenue",
            user="Guest",
            language="en",
            confidence=1.0,
        )

        import asyncio

        async def _drain() -> None:
            async for _ in brain.process(event):
                pass

        # Brain.process swallows the inner error and yields a user
        # error message — so this should NOT raise.
        asyncio.run(_drain())

        # Verify: the partial turn messages reached _finish_turn even
        # though the agent raised. Inspect the mock context's
        # ``finish_turn`` call to confirm.
        finish_turn_mock = brain._context.finish_turn  # noqa: SLF001
        assert finish_turn_mock.called, (
            "Brain.process did not call _finish_turn — "
            "Phase 19 follow-up regression: chart turns lose history "
            "on LLM error."
        )
        persisted = finish_turn_mock.call_args.args[0]
        # The full partial state must be there: tool_call message,
        # tool result, follow-up image.
        assert len(persisted) == 3
        assert persisted[0]["role"] == "assistant"
        assert persisted[0]["tool_calls"][0]["id"] == "tc_1"
        assert persisted[1]["role"] == "tool"
        assert persisted[2]["metadata"]["tool_follow_up"] is True

    def test_partial_persist_failure_does_not_mask_original_error(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If the conversation store itself fails during the
        partial-persist, the inner ``except Exception`` logs the
        store failure and lets the original LLM error keep
        propagating up to ``Brain.process``'s outer handler. The
        user-visible behaviour is unchanged (error message rendered);
        operators see both errors in the log."""
        partial = [
            {"role": "assistant", "content": "x"},
        ]
        brain, _bus = _make_brain_with_failing_agent(partial)

        # Make _finish_turn raise so the inner try/except path fires.
        brain._context.finish_turn.side_effect = RuntimeError("disk full")  # noqa: SLF001

        event = BrainInputEvent(
            type=InputType.TEXT,
            text="hi",
            user="Guest",
            language="en",
            confidence=1.0,
        )

        import asyncio

        async def _drain() -> None:
            async for _ in brain.process(event):
                pass

        # Brain.process swallows BOTH errors and yields a user-facing
        # message. The original "synthetic LLM 400" must appear in
        # the log, and the inner "disk full" must also surface
        # (logger.exception in the inner try/except path).
        with caplog.at_level("ERROR"):
            asyncio.run(_drain())

        # Both errors visible in operator logs.
        log_text = caplog.text
        assert "synthetic LLM 400" in log_text
        assert "Failed to persist partial turn" in log_text
