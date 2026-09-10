"""Trace-metadata kwargs must only reach a Langfuse-wrapped OpenAI client.

Langfuse v4 consumes ``name``/``trace_id``/``metadata`` via its
OpenAI monkey-patch. Without tracing registered, the raw OpenAI SDK
rejects ``name`` (TypeError) — this regressed the first benchmark run
on a machine without Langfuse env vars.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.llm.llm import LLM


class _FakeStream:
    """Minimal async-iterable of streaming chunks."""

    def __init__(self) -> None:
        self._chunks = self._make_chunks()

    @staticmethod
    def _make_chunks() -> list[Any]:
        def chunk(delta_content: str | None, finish: str | None) -> Any:
            delta = MagicMock()
            delta.content = delta_content
            delta.tool_calls = None
            delta.reasoning = None
            c = MagicMock()
            c.usage = None
            c.choices = [MagicMock(delta=delta, finish_reason=finish)]
            return c

        return [chunk("hi", None), chunk(None, "stop")]

    def __aiter__(self) -> Any:
        return self

    async def __anext__(self) -> Any:
        if self._chunks:
            return self._chunks.pop(0)
        raise StopAsyncIteration


@pytest.fixture
def llm() -> LLM:
    return LLM(
        api_key="test-key",
        model="test-model",
        base_url="https://test.api",
        temperature=0.7,
        max_tokens=100,
    )


async def _collect(llm: LLM, **stream_kwargs: Any) -> list[Any]:
    updates = []
    async for update in llm.chat_stream(
        [{"role": "user", "content": "hi"}], **stream_kwargs
    ):
        updates.append(update)
    return updates


TRACE_META = {
    "trace_name": "bench-trace",
    "trace_id": "trace-1",
    "metadata": {"task": "calc-open"},
}


async def test_trace_kwargs_dropped_without_langfuse(llm):
    # Patch the guard explicitly: other tests may have registered the
    # global Langfuse monkey-patch, and this case must hold regardless.
    with (
        patch(
            "tank_backend.llm.llm.is_tracing_registered", return_value=False
        ),
        patch.object(
            llm.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create,
    ):
        mock_create.return_value = _FakeStream()
        updates = await _collect(llm, trace_metadata=dict(TRACE_META))

    assert updates, "stream should produce text updates"
    kwargs = mock_create.call_args.kwargs
    assert "name" not in kwargs, "raw OpenAI SDK rejects name="
    assert "trace_id" not in kwargs
    assert "metadata" not in kwargs


async def test_trace_kwargs_kept_with_langfuse_registered(llm):
    with (
        patch(
            "tank_backend.llm.llm.is_tracing_registered", return_value=True
        ),
        patch.object(
            llm.client.chat.completions, "create", new_callable=AsyncMock
        ) as mock_create,
    ):
        mock_create.return_value = _FakeStream()
        await _collect(llm, trace_metadata=dict(TRACE_META))

    kwargs = mock_create.call_args.kwargs
    assert kwargs.get("name") == "bench-trace"
    assert kwargs.get("trace_id") == "trace-1"
    assert kwargs.get("metadata") == {"task": "calc-open"}


async def test_no_trace_metadata_no_kwargs(llm):
    with patch.object(
        llm.client.chat.completions, "create", new_callable=AsyncMock
    ) as mock_create:
        mock_create.return_value = _FakeStream()
        await _collect(llm)

    kwargs = mock_create.call_args.kwargs
    assert "name" not in kwargs and "trace_id" not in kwargs
