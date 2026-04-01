"""Tests for bounded tool iteration guards in LLM."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.llm.llm import LLM, MAX_TOOL_ITERATIONS

MODULE = "tank_backend.llm.llm"


def _make_tool_call(call_id="call_1", name="calculator", arguments='{"expr":"1+1"}'):
    """Build a mock tool call object."""
    tc = MagicMock()
    tc.id = call_id
    tc.type = "function"
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _make_completion_with_tool_calls():
    """Build a mock ChatCompletion that always requests a tool call."""
    choice = MagicMock()
    choice.message.content = None
    choice.message.role = "assistant"
    choice.message.tool_calls = [_make_tool_call()]
    choice.finish_reason = "tool_calls"
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    completion.model = "test-model"
    completion.id = "test-id"
    return completion


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


class TestChatCompletionAsyncBounded:
    async def test_stops_after_max_iterations(self, llm):
        """LLM that always returns tool calls should stop after MAX_TOOL_ITERATIONS."""
        llm.client.chat.completions.create = AsyncMock(
            return_value=_make_completion_with_tool_calls()
        )
        executor = _make_tool_executor()

        tools = [{"type": "function", "function": {"name": "calculator"}}]
        result = await llm.chat_completion_async(
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
            tool_executor=executor,
        )

        assert result["tool_iterations"] == MAX_TOOL_ITERATIONS
        assert result["choices"][0]["finish_reason"] == "max_tool_iterations"
        assert llm.client.chat.completions.create.call_count == MAX_TOOL_ITERATIONS

    async def test_normal_completion_exits_early(self, llm):
        """LLM that returns text without tool calls should exit on first iteration."""
        choice = MagicMock()
        choice.message.content = "Hello!"
        choice.message.role = "assistant"
        choice.message.tool_calls = None
        choice.finish_reason = "stop"
        completion = MagicMock()
        completion.choices = [choice]
        completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        completion.model = "test-model"
        completion.id = "test-id"

        llm.client.chat.completions.create = AsyncMock(return_value=completion)

        result = await llm.chat_completion_async(
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result["tool_iterations"] == 1
        assert result["choices"][0]["finish_reason"] == "stop"
        assert llm.client.chat.completions.create.call_count == 1


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
