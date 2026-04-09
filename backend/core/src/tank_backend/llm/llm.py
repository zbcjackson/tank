import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionAssistantMessageParam, ChatCompletionMessageParam

from ..core.events import UpdateType
from ..observability.langfuse_client import initialize_langfuse

logger = logging.getLogger("LLM")

MAX_TOOL_ITERATIONS = 10
MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 10.0

# Worker tool prefixes — tools matching these are candidates for concurrent execution
_CONCURRENT_PREFIXES = ("delegate_to_", "review_")


def _is_concurrent_safe(name: str) -> bool:
    """Return True if a tool is a worker delegation (candidate for concurrency)."""
    return any(name.startswith(p) for p in _CONCURRENT_PREFIXES)


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

        # Initialize Langfuse tracing if configured (patches AsyncOpenAI in-place)
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

    async def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_executor: Any = None,
    ) -> AsyncGenerator[tuple[UpdateType, str, dict[str, Any]], None]:
        """
        Stream chat completion with automatic tool call handling.
        Yields: (UpdateType, content_delta, metadata)
        """
        working_messages = messages.copy()
        turn = 0
        rejected_tools: set[str] = set()

        for _iteration in range(MAX_TOOL_ITERATIONS):
            turn += 1
            logger.debug(f"LLM Stream iteration {turn} with {len(working_messages)} messages")

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

            try:
                async for chunk in stream:
                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    # 1. Handle Reasoning (Thought) - Provider specific (e.g. DeepSeek)
                    reasoning = getattr(delta, "reasoning_content", None) or getattr(
                        delta, "reasoning", None
                    )
                    if reasoning:
                        full_reasoning += reasoning
                        yield UpdateType.THOUGHT, reasoning, {"turn": turn}

                    # 2. Handle Content (Text)
                    if delta.content:
                        full_content += delta.content
                        yield UpdateType.TEXT, delta.content, {"turn": turn}

                    # 3. Handle Tool Calls Delta
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_calls_data:
                                tool_calls_data[idx] = {"id": None, "name": "", "arguments": ""}

                            if tc_delta.id:
                                tool_calls_data[idx]["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    tool_calls_data[idx]["name"] += tc_delta.function.name
                                if tc_delta.function.arguments:
                                    tool_calls_data[idx]["arguments"] += tc_delta.function.arguments

                            # Yield unified tool step update for UI
                            yield (
                                UpdateType.TOOL,
                                "",
                                {
                                    "index": idx,
                                    "name": tool_calls_data[idx]["name"],
                                    "arguments": tool_calls_data[idx]["arguments"],
                                    "status": "calling",
                                    "turn": turn,
                                },
                            )
            finally:
                # Explicitly close the stream's internal resources.
                # Use .close() which works on both native AsyncStream and
                # Langfuse's LangfuseResponseGeneratorAsync wrapper.
                if hasattr(stream, "close"):
                    await stream.close()
                elif hasattr(stream, "response"):
                    await stream.response.aclose()

            # ... (Prepare assistant message)
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": full_content}
            if tool_calls_data:
                # Convert accumulated tool calls to OpenAI format
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

            # If there are tool calls, execute them and continue the loop
            if tool_calls_data and tool_executor:
                from openai.types.chat.chat_completion_message_tool_call import (
                    ChatCompletionMessageToolCall,
                    Function,
                )

                sorted_indices = sorted(tool_calls_data.keys())

                # Split into concurrent-safe (worker) and sequential tools
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
                        "Running %d worker tools concurrently: %s",
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
                                    "status": "error", "turn": turn,
                                },
                            )
                            working_messages.append({
                                "role": "tool", "tool_call_id": tc["id"],
                                "name": tc["name"],
                                "content": f"Error: {result!s}",
                            })
                        else:
                            is_error = (
                                isinstance(result, dict) and "error" in result
                            )
                            if is_error:
                                rejected_tools.add(tc["name"])
                            result_str = str(result)
                            summary = (
                                (result_str[:200] + "...")
                                if len(result_str) > 200 else result_str
                            )
                            yield (
                                UpdateType.TOOL, summary,
                                {
                                    "index": idx, "name": tc["name"],
                                    "status": "error" if is_error else "success",
                                    "turn": turn,
                                },
                            )
                            working_messages.append({
                                "role": "tool", "tool_call_id": tc["id"],
                                "name": tc["name"], "content": result_str,
                            })

                elif len(concurrent_items) == 1:
                    # Single worker tool — run sequentially (no gather overhead)
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

                        result_str = str(result)
                        summary = (
                            (result_str[:200] + "...")
                            if len(result_str) > 200 else result_str
                        )

                        yield (
                            UpdateType.TOOL, summary,
                            {
                                "index": idx, "name": tc["name"],
                                "status": "error" if is_error else "success",
                                "turn": turn,
                            },
                        )

                        working_messages.append({
                            "role": "tool", "tool_call_id": tc["id"],
                            "name": tc["name"], "content": result_str,
                        })
                    except Exception as e:
                        yield (
                            UpdateType.TOOL, f"Error: {e!s}",
                            {
                                "index": idx, "name": tc["name"],
                                "status": "error", "turn": turn,
                            },
                        )
                        working_messages.append({
                            "role": "tool", "tool_call_id": tc["id"],
                            "name": tc["name"], "content": f"Error: {e!s}",
                        })
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

    async def chat_completion_async(
        self,
        messages: list[ChatCompletionMessageParam],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_executor=None,
    ) -> dict[str, Any]:
        """
        Chat completion with automatic tool call handling.

        Args:
            messages: List of ChatCompletionMessageParam objects
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            tools: Available tools for the model to use
            tool_executor: Object that can execute tool calls
                (must have execute_openai_tool_call method)
        """
        try:
            # Create a working copy of messages to avoid modifying the original
            working_messages: list[ChatCompletionMessageParam] = messages.copy()
            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            for iterations in range(1, MAX_TOOL_ITERATIONS + 1):
                logger.debug(f"LLM iteration {iterations} with {len(working_messages)} messages")

                # Prepare kwargs for the API call
                api_kwargs = {
                    "model": self.model,
                    "messages": working_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": stream,
                }

                if tools:
                    api_kwargs["tools"] = tools
                if self.extra_body:
                    api_kwargs["extra_body"] = self.extra_body

                # Make the API call
                response = await self._create_with_retry(**api_kwargs)

                # Accumulate usage statistics
                if response.usage:
                    total_usage["prompt_tokens"] += response.usage.prompt_tokens or 0
                    total_usage["completion_tokens"] += response.usage.completion_tokens or 0
                    total_usage["total_tokens"] += response.usage.total_tokens or 0

                # Get the assistant's message
                choice = response.choices[0]
                assistant_message = choice.message

                # Add the assistant's message to working messages
                assistant_msg: ChatCompletionAssistantMessageParam = {
                    "role": "assistant",
                    "content": assistant_message.content,
                }

                # Add tool calls if they exist
                if hasattr(assistant_message, "tool_calls") and assistant_message.tool_calls:
                    assistant_msg["tool_calls"] = assistant_message.tool_calls

                working_messages.append(assistant_msg)

                # Check if there are tool calls
                if (
                    hasattr(assistant_message, "tool_calls")
                    and assistant_message.tool_calls
                    and tool_executor
                ):
                    logger.info(f"Processing {len(assistant_message.tool_calls)} tool calls")

                    # Execute each tool call and add results as tool messages
                    for tool_call in assistant_message.tool_calls:
                        try:
                            # Execute the tool call
                            tool_result = await tool_executor.execute_openai_tool_call(tool_call)

                            # Convert tool result to string
                            if isinstance(tool_result, dict):
                                if "error" in tool_result:
                                    result_content = f"Error: {tool_result['error']}"
                                elif "message" in tool_result:
                                    result_content = tool_result["message"]
                                else:
                                    result_content = str(tool_result)
                            else:
                                result_content = str(tool_result)

                            # Add tool response as a tool message
                            working_messages.append(
                                {
                                    "role": "tool",
                                    "content": result_content,
                                    "tool_call_id": tool_call.id,
                                    "name": tool_call.function.name,
                                }
                            )

                            logger.debug(f"Tool {tool_call.function.name} executed successfully")

                        except Exception as e:
                            logger.error(f"Error executing tool {tool_call.function.name}: {e}")
                            # Add error message as tool response
                            working_messages.append(
                                {
                                    "role": "tool",
                                    "content": (
                                f"Error executing {tool_call.function.name}: "
                                f"{str(e)}"
                            ),
                                    "tool_call_id": tool_call.id,
                                    "name": tool_call.function.name,
                                }
                            )
                else:
                    # No more tool calls, return the final response
                    result = {
                        "choices": [
                            {
                                "message": {
                                    "role": assistant_message.role,
                                    "content": assistant_message.content,
                                },
                                "finish_reason": choice.finish_reason,
                            }
                        ],
                        "usage": total_usage,
                        "model": response.model,
                        "id": response.id,
                        "tool_iterations": iterations,
                    }

                    # Add tool calls if present (for debugging/logging purposes)
                    if hasattr(assistant_message, "tool_calls") and assistant_message.tool_calls:
                        result["choices"][0]["message"]["tool_calls"] = assistant_message.tool_calls

                    return result
            else:
                logger.warning(
                    "chat_completion_async hit MAX_TOOL_ITERATIONS (%d) — stopping tool loop",
                    MAX_TOOL_ITERATIONS,
                )
                # Return last assistant message as final response
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": assistant_message.content,
                            },
                            "finish_reason": "max_tool_iterations",
                        }
                    ],
                    "usage": total_usage,
                    "model": response.model,
                    "id": response.id,
                    "tool_iterations": iterations,
                }

        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise

    async def check_connection(self) -> bool:
        try:
            test_messages = [{"role": "user", "content": "Hello, can you hear me?"}]
            await self.chat_completion_async(test_messages, max_tokens=16)
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False
