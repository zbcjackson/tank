"""Tests for bounded tool iteration guards in LLM."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.llm.llm import LLM, MAX_TOOL_ITERATIONS

MODULE = "tank_backend.llm.llm"


def _make_stream_chunk_with_tool_call():
    """Build a mock streaming chunk that contains a tool call delta."""
    chunk = MagicMock()
    delta = MagicMock()
    delta.content = None
    delta.tool_calls = [MagicMock()]
    delta.tool_calls[0].index = 0
    delta.tool_calls[0].id = "call_1"
    delta.tool_calls[0].function = MagicMock()
    delta.tool_calls[0].function.name = "calculator"
    delta.tool_calls[0].function.arguments = '{"expr":"1+1"}'
    # No reasoning attributes
    type(delta).reasoning_content = None
    type(delta).reasoning = None
    chunk.choices = [MagicMock(delta=delta)]
    return chunk


def _make_tool_executor():
    """Build a mock tool executor."""
    executor = AsyncMock()
    executor.execute_openai_tool_call = AsyncMock(return_value="2")
    return executor


@pytest.fixture
def llm():
    with patch(f"{MODULE}.AsyncOpenAI"):
        return LLM(
            api_key="test-key",
            model="test-model",
            base_url="https://test.example.com",
            stream_options=False,
        )


class AsyncIterator:
    """Helper to create an async iterator from a list."""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


class TestChatStreamBounded:
    async def test_stops_after_max_iterations(self, llm):
        """Streaming LLM that always returns tool calls should stop after MAX_TOOL_ITERATIONS."""

        def _make_fresh_stream():
            chunk = _make_stream_chunk_with_tool_call()
            mock_stream = MagicMock()
            mock_stream.__aiter__ = MagicMock(return_value=AsyncIterator([chunk]))
            mock_stream.close = AsyncMock()
            mock_stream.response = AsyncMock()
            mock_stream.response.aclose = AsyncMock()
            return mock_stream

        llm.client.chat.completions.create = AsyncMock(
            side_effect=lambda **kw: _make_fresh_stream()
        )
        executor = _make_tool_executor()

        tools = [{"type": "function", "function": {"name": "calculator"}}]
        updates = []
        async for update_type, content, metadata in llm.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
            tool_executor=executor,
        ):
            updates.append((update_type, content, metadata))

        # Should have been called MAX_TOOL_ITERATIONS times
        assert llm.client.chat.completions.create.call_count == MAX_TOOL_ITERATIONS


class TestComplete:
    async def test_returns_text(self, llm):
        """complete() should return the response text directly."""
        choice = MagicMock()
        choice.message.content = "Hello!"
        completion = MagicMock()
        completion.choices = [choice]

        llm.client.chat.completions.create = AsyncMock(return_value=completion)

        result = await llm.complete(
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result == "Hello!"
        assert llm.client.chat.completions.create.call_count == 1

    async def test_returns_empty_on_none(self, llm):
        """complete() should return empty string when content is None."""
        choice = MagicMock()
        choice.message.content = None
        completion = MagicMock()
        completion.choices = [choice]

        llm.client.chat.completions.create = AsyncMock(return_value=completion)

        result = await llm.complete(
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result == ""

    async def test_chat_completion_async_compat(self, llm):
        """chat_completion_async wraps complete() with old dict format."""
        choice = MagicMock()
        choice.message.content = "Hello!"
        completion = MagicMock()
        completion.choices = [choice]

        llm.client.chat.completions.create = AsyncMock(return_value=completion)

        result = await llm.chat_completion_async(
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result["choices"][0]["message"]["content"] == "Hello!"



async def test_reasoning_content_kept_in_assistant_history(llm):
    """DeepSeek thinking mode 400s unless reasoning_content is passed
    back with the assistant message (observed live in the notification
    turn, 2026-09-16). Round 1 streams reasoning + a tool call; the
    SECOND request must carry the assistant message with reasoning."""

    def stream_round(tool_round: bool):
        chunks = []
        if tool_round:
            r = MagicMock()
            r.content = None
            r.tool_calls = None
            type(r).reasoning = "thinking hard"
            type(r).reasoning_content = None
            chunks.append(MagicMock(choices=[MagicMock(delta=r)]))
            chunks.append(_make_stream_chunk_with_tool_call())
        else:
            plain = MagicMock()
            plain.content = "done"
            plain.tool_calls = None
            type(plain).reasoning = None
            type(plain).reasoning_content = None
            chunks.append(MagicMock(choices=[MagicMock(delta=plain)]))
        s = MagicMock()
        s.__aiter__ = MagicMock(return_value=AsyncIterator(chunks))
        s.close = AsyncMock()
        s.response = AsyncMock()
        s.response.aclose = AsyncMock()
        return s

    captured: list[list[dict]] = []

    def fake_create(**kwargs):
        captured.append(list(kwargs["messages"]))
        return stream_round(tool_round=len(captured) == 1)

    llm.client.chat.completions.create = AsyncMock(side_effect=fake_create)

    async for _ in llm.chat_stream(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "calculator"}}],
        tool_executor=_make_tool_executor(),
    ):
        pass

    assert len(captured) >= 2
    second = captured[1]
    assistant = [m for m in second if m.get("role") == "assistant"]
    assert any(m.get("reasoning_content") == "thinking hard" for m in assistant)
