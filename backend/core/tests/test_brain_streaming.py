"""Tests for Brain streaming LLM responses as a Processor."""

import threading

import pytest
from brain_test_helpers import make_brain, make_mock_context

from tank_backend.agents.base import Agent, AgentOutput, AgentOutputType
from tank_backend.agents.graph import AgentGraph
from tank_backend.core.events import (
    AudioOutputRequest,
    BrainInputEvent,
    DisplayMessage,
    InputType,
    UpdateType,
)
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processor import FlowReturn
from tank_backend.pipeline.processors.brain import BrainConfig


async def _collect(processor, item):
    results = []
    async for status, output in processor.process(item):
        results.append((status, output))
    return results


class _StreamingAgent(Agent):
    """Agent that yields TOOL_CALLING, TOOL_RESULT, then TOKEN events."""

    def __init__(self):
        super().__init__("streaming")

    async def run(self, state):
        yield AgentOutput(
            type=AgentOutputType.TOOL_CALLING, content="",
            metadata={"index": 0, "name": "get_weather", "status": "calling"},
        )
        yield AgentOutput(
            type=AgentOutputType.TOOL_RESULT, content="Sunny",
            metadata={"index": 0, "name": "get_weather", "status": "success"},
        )
        yield AgentOutput(
            type=AgentOutputType.TOKEN, content="The weather is sunny.",
            metadata={"turn": 1},
        )
        yield AgentOutput(type=AgentOutputType.DONE)


@pytest.fixture
def bus():
    return Bus()


@pytest.fixture
def brain(bus):
    agent = _StreamingAgent()
    graph = AgentGraph(agents={"streaming": agent}, default_agent="streaming")

    return make_brain(
        bus=bus,
        agent_graph=graph,
    )


async def test_brain_streaming_full_flow(brain, bus):
    event = BrainInputEvent(
        type=InputType.TEXT,
        text="What is the weather?",
        user="User",
        language="en",
        confidence=None,
        metadata={"msg_id": "test_msg_id"},
    )

    # Collect yielded outputs (AudioOutputRequest for TTS)
    results = await _collect(brain, event)

    # Collect UI messages from bus
    ui_messages = []
    bus.subscribe("ui_message", lambda m: ui_messages.append(m.payload))
    bus.poll()

    # 1. Should yield exactly one AudioOutputRequest
    assert len(results) == 1
    assert results[0][0] == FlowReturn.OK
    audio_req = results[0][1]
    assert audio_req is not None
    assert audio_req.content == "The weather is sunny."

    # 2. Assistant messages (filter out SignalMessage)
    assistant_msgs = [m for m in ui_messages if isinstance(m, DisplayMessage) and not m.is_user]
    assert any(m.update_type == UpdateType.TOOL for m in assistant_msgs)
    assert any(
        m.update_type == UpdateType.TEXT and m.text == "The weather is sunny."
        for m in assistant_msgs
    )

    # 3. Final message
    assert assistant_msgs[-1].is_final is True


async def test_interrupted_response_saved_to_context(bus):
    """When Brain is interrupted mid-stream, partial text is saved via context.finish_turn."""
    interrupt_event = threading.Event()

    class InterruptingAgent(Agent):
        def __init__(self, interrupt_event):
            super().__init__("interrupting")
            self._interrupt = interrupt_event

        async def run(self, state):
            yield AgentOutput(
                type=AgentOutputType.TOKEN, content="The weather ",
                metadata={"turn": 1},
            )
            yield AgentOutput(
                type=AgentOutputType.TOKEN, content="is sunny",
                metadata={"turn": 1},
            )
            # Simulate interrupt being set between chunks
            self._interrupt.set()
            yield AgentOutput(
                type=AgentOutputType.TOKEN, content=" today.",
                metadata={"turn": 1},
            )
            yield AgentOutput(type=AgentOutputType.DONE)

    agent = InterruptingAgent(interrupt_event)
    graph = AgentGraph(agents={"interrupting": agent}, default_agent="interrupting")

    ctx = make_mock_context()
    brain = make_brain(
        bus=bus,
        interrupt_event=interrupt_event,
        context=ctx,
        agent_graph=graph,
    )

    event = BrainInputEvent(
        type=InputType.TEXT,
        text="What is the weather?",
        user="User",
        language="en",
        confidence=None,
    )

    results = await _collect(brain, event)

    # Should yield None (interrupted, no TTS)
    assert results[0][1] is None

    # Partial response should be saved via context.finish_turn
    ctx.finish_turn.assert_called_once()
    saved_arg = ctx.finish_turn.call_args[0][0]
    # finish_turn now receives the turn_messages list
    assert isinstance(saved_arg, list)


class _TokenAgent(Agent):
    """Agent that yields the given token deltas then DONE."""

    def __init__(self, tokens, interrupt_after=None, interrupt_event=None):
        super().__init__("tokens")
        self._tokens = tokens
        self._interrupt_after = interrupt_after
        self._interrupt_event = interrupt_event

    async def run(self, state):
        for i, tok in enumerate(self._tokens):
            yield AgentOutput(type=AgentOutputType.TOKEN, content=tok,
                              metadata={"turn": 1})
            if (
                self._interrupt_after is not None
                and i == self._interrupt_after
                and self._interrupt_event is not None
            ):
                self._interrupt_event.set()
        yield AgentOutput(type=AgentOutputType.DONE)


def _make_event(text="你好", language="zh"):
    return BrainInputEvent(
        type=InputType.TEXT,
        text=text,
        user="User",
        language=language,
        confidence=None,
    )


class TestSentenceBatchStreaming:
    """Sentence-level streaming of AudioOutputRequests (P0-5)."""

    async def test_long_reply_streams_multiple_ordered_batches(self, bus):
        tokens = [
            "今天天气很好。", "我们去公园散步吧。", "然后一起吃午饭。",
            "下午继续工作。", "晚上看电影放松。", "最后回家休息。",
        ]
        graph = AgentGraph(
            agents={"tokens": _TokenAgent(tokens)}, default_agent="tokens",
        )
        brain = make_brain(
            bus=bus, agent_graph=graph,
            config=BrainConfig(stream_batch_sentences=2),
        )

        results = await _collect(brain, _make_event())

        requests = [out for _status, out in results if out is not None]
        assert len(requests) == 3
        assert all(isinstance(r, AudioOutputRequest) for r in requests)
        # Ordered: concatenation of batches reconstructs the full reply
        assert "".join(r.content for r in requests) == "".join(tokens)
        # Every batch belongs to the same assistant message
        msg_ids = {r.msg_id for r in requests}
        assert len(msg_ids) == 1
        assert next(iter(msg_ids)).startswith("assistant_")

    async def test_short_reply_single_request(self, bus):
        graph = AgentGraph(
            agents={"tokens": _TokenAgent(["One short sentence. and done?"])},
            default_agent="tokens",
        )
        brain = make_brain(bus=bus, agent_graph=graph)

        results = await _collect(brain, _make_event(language="en"))

        requests = [out for _status, out in results if out is not None]
        assert requests == [AudioOutputRequest(
            content="One short sentence. and done?", language="en",
            msg_id=requests[0].msg_id if requests else None,
        )]

    async def test_first_batch_decides_language_for_whole_turn(self, bus):
        tokens = [
            "今天天气很好。", "我们去公园散步吧。",          # zh → decides
            "This sentence is English. So is this one here.",  # stays zh
        ]
        graph = AgentGraph(
            agents={"tokens": _TokenAgent(tokens)}, default_agent="tokens",
        )
        brain = make_brain(
            bus=bus, agent_graph=graph,
            config=BrainConfig(stream_batch_sentences=2),
        )

        results = await _collect(brain, _make_event())

        requests = [out for _status, out in results if out is not None]
        assert len(requests) == 2
        assert requests[0].language == "zh"
        assert requests[1].language == "zh"  # decided once, reused

    async def test_user_language_used_as_fallback_prior(self, bus):
        # First batch has no alphabetic/CJK content → detection falls back
        # to the prior = event.language ("zh").
        tokens = ["……。", "Fine then. Moving right along. Ok."]
        graph = AgentGraph(
            agents={"tokens": _TokenAgent(tokens)}, default_agent="tokens",
        )
        brain = make_brain(
            bus=bus, agent_graph=graph,
            config=BrainConfig(stream_batch_sentences=1),
        )

        results = await _collect(brain, _make_event(text="嗯", language="zh"))

        requests = [out for _status, out in results if out is not None]
        assert requests[0].language == "zh"

    async def test_interrupt_stops_later_batches(self, bus):
        interrupt_event = threading.Event()
        tokens = [
            "First sentence here. ", "Second sentence now. ",
            "Third sentence follows. ", "Fourth one. ",
        ]
        graph = AgentGraph(
            agents={"tokens": _TokenAgent(
                tokens, interrupt_after=0, interrupt_event=interrupt_event,
            )},
            default_agent="tokens",
        )
        ctx = make_mock_context()
        brain = make_brain(
            bus=bus, agent_graph=graph, interrupt_event=interrupt_event,
            context=ctx, config=BrainConfig(stream_batch_sentences=1),
        )

        results = await _collect(brain, _make_event(language="en"))

        requests = [out for _status, out in results if out is not None]
        # Only the batch completed before the interrupt went out
        assert [r.content for r in requests] == ["First sentence here."]
        # Partial turn is still persisted (existing behavior)
        ctx.finish_turn.assert_called_once()

    async def test_finalize_runs_once_on_full_text(self, bus):
        tokens = [
            "第一句话在这里。", "第二句话也在这里。", "第三句话收尾。 ",
            "看这张图 ![pic](https://x.io/a.png) 好看。 ",
        ]
        graph = AgentGraph(
            agents={"tokens": _TokenAgent(tokens)}, default_agent="tokens",
        )
        ctx = make_mock_context()
        brain = make_brain(
            bus=bus, agent_graph=graph, context=ctx,
            config=BrainConfig(stream_batch_sentences=2),
        )
        voice_events = []
        bus.subscribe("outbound_voice", lambda m: voice_events.append(m.payload))

        await _collect(brain, _make_event())
        bus.poll()

        full_text = "".join(tokens)
        # Markdown image is replaced by its alt text in the finalized copy
        cleaned = full_text.replace("![pic](https://x.io/a.png)", "pic")
        # Conversation finalize sees the FULL text exactly once
        assert ctx.finish_turn.call_count == 1
        ctx.schedule_memory_store.assert_called_once_with(
            "User", "你好", cleaned,
        )
        # outbound_voice carries the full text with images stripped
        assert len(voice_events) == 1
        assert voice_events[0]["text"] == cleaned

    async def test_tts_disabled_yields_no_requests_but_finalizes(self, bus):
        tokens = ["One sentence. ", "Another sentence. ", "Third one here. "]
        graph = AgentGraph(
            agents={"tokens": _TokenAgent(tokens)}, default_agent="tokens",
        )
        ctx = make_mock_context()
        brain = make_brain(
            bus=bus, agent_graph=graph, context=ctx, tts_enabled=False,
            config=BrainConfig(stream_batch_sentences=1),
        )

        results = await _collect(brain, _make_event(language="en"))

        assert [out for _s, out in results if out is not None] == []
        ctx.finish_turn.assert_called_once()
