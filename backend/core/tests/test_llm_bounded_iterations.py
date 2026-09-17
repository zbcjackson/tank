"""Tests for bounded tool iteration guards in LLM."""

import copy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai.types.chat import ChatCompletionChunk

from tank_backend.core.events import UpdateType
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



@pytest.mark.parametrize("reasoning_field", ["reasoning_content", "reasoning"])
async def test_reasoning_content_kept_in_assistant_history(llm, reasoning_field):
    """DeepSeek thinking mode 400s unless reasoning_content is passed
    back with the assistant message (observed live in the notification
    turn, 2026-09-16). Round 1 streams reasoning + a tool call; the
    SECOND request must carry the assistant message with reasoning."""

    def stream_round(tool_round: bool):
        chunks = []
        if tool_round:
            for fragment in ("thinking ", "hard"):
                chunks.append(ChatCompletionChunk.model_validate({
                    "id": "chunk", "object": "chat.completion.chunk", "created": 0,
                    "model": "deepseek-flash",
                    "choices": [{"index": 0, "finish_reason": None,
                                 "delta": {reasoning_field: fragment}}],
                }))
            chunks.append(_make_stream_chunk_with_tool_call())
        else:
            chunks.append(ChatCompletionChunk.model_validate({
                "id": "chunk", "object": "chat.completion.chunk", "created": 0,
                "model": "deepseek-flash",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "delta": {"content": "done", reasoning_field: "final reasoning"}}],
            }))
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

    history = [{"role": "user", "content": "hi"}]
    thoughts = []
    tools = [{"type": "function", "function": {"name": "calculator"}}]
    async for update, content, metadata in llm.chat_stream(
        messages=[{"role": "user", "content": "hi"}],
        tools=tools,
        tool_executor=_make_tool_executor(),
    ):
        if update == UpdateType.MESSAGE:
            history.append(metadata["message"])
        if update == UpdateType.THOUGHT:
            thoughts.append(content)

    assert len(captured) >= 2
    second = captured[1]
    assistant = [m for m in second if m.get("role") == "assistant"]
    assert any(m.get("reasoning_content") == "thinking hard" for m in assistant)
    assert thoughts == ["thinking ", "hard", "final reasoning"]
    assert history[-1]["reasoning_content"] == "final reasoning"
    history.append({"role": "system", "content": "background worker completed"})
    _ = [u async for u in llm.chat_stream(messages=history, tools=tools)]
    assistants = [m for m in captured[2] if m.get("role") == "assistant"]
    assert [m["reasoning_content"] for m in assistants] == ["thinking hard", "final reasoning"]


@pytest.mark.parametrize("model,reasoning,disabled", [
    ("deepseek-flash", None, True),
    ("deepseek-pro", None, True),
    ("deepseek-flash", "", True),
    ("deepseek-flash", "original thinking", False),
    ("test-model", None, False),
])
async def test_notification_with_incomplete_reasoning_history(llm, model, reasoning, disabled):
    llm.model = model
    llm.extra_body = {"thinking": {"type": "enabled"}, "custom_option": "retained"}
    assistant = {"role": "assistant", "content": "Task dispatched"}
    if reasoning is not None:
        assistant["reasoning_content"] = reasoning
    history = [
        {"role": "user", "content": "Use n2 to calculate 57 times 8"},
        assistant,
        {"role": "system", "content": "Background worker completed: calculator displays 456"},
    ]
    original_history = copy.deepcopy(history)
    original_config = copy.deepcopy(llm.extra_body)
    requests = []

    async def create(**kwargs):
        requests.append(copy.deepcopy(kwargs))
        # Simulate the provider's validation of the actual outbound request.
        if disabled:
            assert kwargs["extra_body"]["thinking"]["type"] == "disabled"
        chunk = ChatCompletionChunk.model_validate({
            "id": "chunk", "object": "chat.completion.chunk", "created": 0,
            "model": model, "choices": [{"index": 0, "finish_reason": "stop",
                                         "delta": {"content": "456"}}],
        })
        return AsyncIterator([chunk])

    llm.client.chat.completions.create = AsyncMock(side_effect=create)
    outputs = [u async for u in llm.chat_stream(
        messages=history, tools=[{"type": "function", "function": {"name": "agent"}}],
    )]
    assert any(update == UpdateType.TEXT and content == "456" for update, content, _ in outputs)
    assert requests[0]["extra_body"]["thinking"]["type"] == ("disabled" if disabled else "enabled")
    assert requests[0]["extra_body"]["custom_option"] == "retained"
    assert history == original_history
    assert llm.extra_body == original_config
