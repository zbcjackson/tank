"""LLM client — streaming chat with tool execution and simple completion.

``chat_stream`` is the primary method for agent conversations (streaming +
tool loop).  ``complete`` is for simple one-shot calls (summarization,
connection checks).  Both share ``_create_with_retry`` for consistent
retry behavior.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam

from ..core.events import UpdateType
from ..observability.langfuse_client import initialize_langfuse

logger = logging.getLogger("LLM")

MAX_TOOL_ITERATIONS = 100
MAX_RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 8.0

_CONCURRENT_SAFE_TOOLS = frozenset({"agent"})


def _is_concurrent_safe(name: str) -> bool:
    """Return True if a tool can safely run in parallel with others."""
    return name in _CONCURRENT_SAFE_TOOLS


class LLM:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        temperature: float = 0.7,
        max_tokens: int = 10000,
        extra_headers: dict[str, str] | None = None,
        stream_options: bool = True,
        extra_body: dict[str, Any] | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream_options = stream_options
        self.extra_body = extra_body or {}

        initialize_langfuse()

        # Initialize OpenAI client with custom base URL and headers
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=extra_headers or {},
        )

    _RETRYABLE_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)

    async def _create_with_retry(self, **api_kwargs: Any) -> Any:
        """Call chat.completions.create with exponential backoff on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                return await self.client.chat.completions.create(**api_kwargs)
            except self._RETRYABLE_ERRORS as exc:
                last_exc = exc
                if attempt == MAX_RETRY_ATTEMPTS:
                    break
                delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
                logger.warning(
                    "LLM request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    MAX_RETRY_ATTEMPTS,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Streaming chat with tool execution (used by LLMAgent)
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Any = None,
        trace_metadata: dict[str, Any] | None = None,
        system_prompt_fn: Callable[[], str | None] | None = None,
    ) -> AsyncGenerator[tuple[UpdateType, str, dict[str, Any]], None]:
        """Stream chat completion with automatic tool call handling.

        Yields: (UpdateType, content_delta, metadata)

        Args:
            trace_metadata: Optional Langfuse trace metadata. Keys like
                ``trace_name``, ``metadata`` are passed as top-level
                kwargs for per-call tracing.
        """
        working_messages = messages.copy()
        turn = 0
        rejected_tools: set[str] = set()

        for _iteration in range(MAX_TOOL_ITERATIONS):
            turn += 1
            logger.debug(f"LLM Stream iteration {turn} with {len(working_messages)} messages")

            # Refresh system prompt if callback provided and rebuild needed
            if system_prompt_fn is not None:
                refreshed = system_prompt_fn()
                if refreshed is not None:
                    working_messages[0] = {"role": "system", "content": refreshed}

            api_kwargs = {
                "model": self.model,
                "messages": working_messages,
                "temperature": temperature if temperature is not None else self.temperature,
                "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
                "stream": True,
            }
            if self.stream_options:
                api_kwargs["stream_options"] = {"include_usage": True}
            if self.extra_body:
                api_kwargs["extra_body"] = self.extra_body
            # Langfuse v4: trace metadata as top-level kwargs.
            # Only pass keys that OpenAiArgsExtractor explicitly
            # extracts (name, metadata, trace_id, parent_observation_id).
            # Other keys (tags, session_id) leak through to the OpenAI
            # API and cause "unexpected keyword argument" errors.
            if trace_metadata:
                if "trace_name" in trace_metadata:
                    api_kwargs["name"] = trace_metadata["trace_name"]
                if "metadata" in trace_metadata:
                    api_kwargs["metadata"] = trace_metadata["metadata"]
                if "trace_id" in trace_metadata:
                    api_kwargs["trace_id"] = trace_metadata["trace_id"]
            if tools:
                # Remove rejected tools so the LLM cannot retry them
                effective_tools = [
                    t for t in tools
                    if t.get("function", {}).get("name") not in rejected_tools
                ] if rejected_tools else tools
                if effective_tools:
                    api_kwargs["tools"] = effective_tools

            full_content = ""
            full_reasoning = ""
            tool_calls_data = {}  # index -> {id, name, arguments}

            stream = await self._create_with_retry(**api_kwargs)

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Handle reasoning/thinking content
                if hasattr(delta, "reasoning") and delta.reasoning:
                    full_reasoning += delta.reasoning
                    yield (
                        UpdateType.THOUGHT, delta.reasoning,
                        {"turn": turn},
                    )

                # Handle regular content
                if delta.content:
                    full_content += delta.content
                    yield (
                        UpdateType.TEXT, delta.content,
                        {"turn": turn},
                    )

                # Handle tool calls
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {
                                "id": tc_delta.id or "",
                                "name": (
                                    tc_delta.function.name
                                    if tc_delta.function and tc_delta.function.name
                                    else ""
                                ),
                                "arguments": "",
                            }
                        else:
                            if tc_delta.id:
                                tool_calls_data[idx]["id"] = tc_delta.id
                            if tc_delta.function and tc_delta.function.name:
                                tool_calls_data[idx]["name"] = tc_delta.function.name

                        if tc_delta.function and tc_delta.function.arguments:
                            tool_calls_data[idx]["arguments"] += tc_delta.function.arguments

                        yield (
                            UpdateType.TOOL, "",
                            {
                                "index": idx,
                                "name": tool_calls_data[idx]["name"],
                                "arguments": tool_calls_data[idx]["arguments"],
                                "status": "calling", "turn": turn,
                            },
                        )

            # Build assistant message for history
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": full_content or None,
            }
            if tool_calls_data:
                formatted_tool_calls = []
                for idx in sorted(tool_calls_data.keys()):
                    formatted_tool_calls.append(
                        {
                            "id": tool_calls_data[idx]["id"],
                            "type": "function",
                            "function": {
                                "name": tool_calls_data[idx]["name"],
                                "arguments": tool_calls_data[idx]["arguments"],
                            },
                        }
                    )
                assistant_msg["tool_calls"] = formatted_tool_calls

            working_messages.append(assistant_msg)
            yield (UpdateType.MESSAGE, "", {"message": assistant_msg})
            if tool_calls_data and tool_executor:
                from openai.types.chat.chat_completion_message_tool_call import (
                    ChatCompletionMessageToolCall,
                    Function,
                )

                sorted_indices = sorted(tool_calls_data.keys())

                # Split into concurrent-safe and sequential tools
                concurrent_items = [
                    (idx, tool_calls_data[idx])
                    for idx in sorted_indices
                    if _is_concurrent_safe(tool_calls_data[idx]["name"])
                ]
                sequential_items = [
                    (idx, tool_calls_data[idx])
                    for idx in sorted_indices
                    if not _is_concurrent_safe(tool_calls_data[idx]["name"])
                ]

                # --- Run concurrent-safe tools in parallel ---
                if len(concurrent_items) > 1:
                    logger.info(
                        "Running %d tools concurrently: %s",
                        len(concurrent_items),
                        [tc["name"] for _, tc in concurrent_items],
                    )

                    # Emit all "executing" statuses first
                    for idx, tc in concurrent_items:
                        yield (
                            UpdateType.TOOL, "",
                            {
                                "index": idx, "name": tc["name"],
                                "arguments": tc["arguments"],
                                "status": "executing", "turn": turn,
                            },
                        )

                    # Build coroutines and gather
                    async def _exec_one(tc_item: dict[str, Any]) -> Any:
                        obj = ChatCompletionMessageToolCall(
                            id=tc_item["id"], type="function",
                            function=Function(
                                name=tc_item["name"],
                                arguments=tc_item["arguments"],
                            ),
                        )
                        return await tool_executor.execute_openai_tool_call(obj)

                    results = await asyncio.gather(
                        *(_exec_one(tc) for _, tc in concurrent_items),
                        return_exceptions=True,
                    )

                    # Process results
                    for (idx, tc), result in zip(
                        concurrent_items, results, strict=True,
                    ):
                        if isinstance(result, Exception):
                            yield (
                                UpdateType.TOOL, f"Error: {result!s}",
                                {
                                    "index": idx, "name": tc["name"],
                                    "arguments": tc["arguments"],
                                    "status": "error", "turn": turn,
                                },
                            )
                            working_messages.append({
                                "role": "tool", "tool_call_id": tc["id"],
                                "name": tc["name"],
                                "content": f"Error: {result!s}",
                            })
                            yield (UpdateType.MESSAGE, "", {"message": working_messages[-1]})
                            is_error = (
                                isinstance(result, dict) and "error" in result
                            )
                            if is_error:
                                rejected_tools.add(tc["name"])
                            if isinstance(result, dict) and "message" in result:
                                result_str = result["message"]
                            elif isinstance(result, dict):
                                result_str = json.dumps(result, ensure_ascii=False)
                            else:
                                result_str = str(result)
                            summary = (
                                (result_str[:200] + "...")
                                if len(result_str) > 200 else result_str
                            )
                            yield (
                                UpdateType.TOOL, summary,
                                {
                                    "index": idx, "name": tc["name"],
                                    "arguments": tc["arguments"],
                                    "status": "error" if is_error else "success",
                                    "turn": turn,
                                },
                            )
                            working_messages.append({
                                "role": "tool", "tool_call_id": tc["id"],
                                "name": tc["name"], "content": result_str,
                            })
                            yield (UpdateType.MESSAGE, "", {"message": working_messages[-1]})

                elif len(concurrent_items) == 1:
                    # Single concurrent tool — run sequentially (no gather overhead)
                    sequential_items = concurrent_items + sequential_items
                    concurrent_items = []

                # --- Run remaining tools sequentially ---
                for idx, tc in sequential_items:
                    try:
                        yield (
                            UpdateType.TOOL, "",
                            {
                                "index": idx, "name": tc["name"],
                                "arguments": tc["arguments"],
                                "status": "executing", "turn": turn,
                            },
                        )

                        tool_call_obj = ChatCompletionMessageToolCall(
                            id=tc["id"], type="function",
                            function=Function(
                                name=tc["name"], arguments=tc["arguments"],
                            ),
                        )

                        result = await tool_executor.execute_openai_tool_call(
                            tool_call_obj,
                        )

                        is_error = (
                            isinstance(result, dict) and "error" in result
                        )
                        if is_error:
                            rejected_tools.add(tc["name"])

                        # Use "message" field for tool result content when
                        # available — gives tools control over what the LLM
                        # sees (e.g. skill instructions).  Fall back to
                        # json for dicts, str() for everything else.
                        if isinstance(result, dict) and "message" in result:
                            result_str = result["message"]
                        elif isinstance(result, dict):
                            result_str = json.dumps(result, ensure_ascii=False)
                        else:
                            result_str = str(result)

                        summary = (
                            (result_str[:200] + "...")
                            if len(result_str) > 200 else result_str
                        )

                        yield (
                            UpdateType.TOOL, summary,
                            {
                                "index": idx, "name": tc["name"],
                                "arguments": tc["arguments"],
                                "status": "error" if is_error else "success",
                                "turn": turn,
                            },
                        )

                        working_messages.append({
                            "role": "tool", "tool_call_id": tc["id"],
                            "name": tc["name"], "content": result_str,
                        })
                        yield (UpdateType.MESSAGE, "", {"message": working_messages[-1]})

                    except Exception as e:
                        yield (
                            UpdateType.TOOL, f"Error: {e!s}",
                            {
                                "index": idx, "name": tc["name"],
                                "arguments": tc["arguments"],
                                "status": "error", "turn": turn,
                            },
                        )
                        working_messages.append({
                            "role": "tool", "tool_call_id": tc["id"],
                            "name": tc["name"], "content": f"Error: {e!s}",
                        })
                        yield (UpdateType.MESSAGE, "", {"message": working_messages[-1]})
                # Continue loop to get next response after tools
                continue
            else:
                # No tool calls, we are done
                break
        else:
            logger.warning(
                "chat_stream hit MAX_TOOL_ITERATIONS (%d) — stopping tool loop",
                MAX_TOOL_ITERATIONS,
            )

    # ------------------------------------------------------------------
    # Simple completion (used by summarization, connection checks)
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float | None = None,
        max_tokens: int | None = None,
        trace_metadata: dict[str, Any] | None = None,
    ) -> str:
        """Simple non-streaming LLM call. Returns the response text.

        No tool loop — just a single request/response.  Shares
        ``_create_with_retry`` with ``chat_stream`` for consistent
        retry behavior.
        """
        api_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "stream": False,
        }
        if self.extra_body:
            api_kwargs["extra_body"] = self.extra_body
        if trace_metadata:
            if "trace_name" in trace_metadata:
                api_kwargs["name"] = trace_metadata["trace_name"]
            if "metadata" in trace_metadata:
                api_kwargs["metadata"] = trace_metadata["metadata"]

        response = await self._create_with_retry(**api_kwargs)
        return response.choices[0].message.content or ""

    async def chat_completion_async(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        """Deprecated — use ``complete()`` instead."""
        content = await self.complete(
            messages, temperature=temperature, max_tokens=max_tokens,
        )
        return {
            "choices": [{"message": {"role": "assistant", "content": content}}],
        }

    async def check_connection(self) -> bool:
        try:
            test_messages: list[ChatCompletionMessageParam] = [
                {"role": "user", "content": "Hello, can you hear me?"},
            ]
            await self.complete(test_messages, max_tokens=16)
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False
