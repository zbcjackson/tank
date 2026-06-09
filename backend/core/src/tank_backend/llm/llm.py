"""LLM client — streaming chat with tool execution and simple completion.

``chat_stream`` is the primary method for agent conversations (streaming +
tool loop).  ``complete`` is for simple one-shot calls (summarization,
connection checks).  Both share ``_create_with_retry`` for consistent
retry behavior.
"""

from __future__ import annotations

import asyncio
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

from ..core.content import (
    ContentBlock,
    ContentBlocks,
    TextBlock,
    blocks_to_text,
)
from ..core.events import UpdateType
from ..observability.langfuse_client import initialize_langfuse
from ..tools.base import ToolResult

logger = logging.getLogger("LLM")

MAX_TOOL_ITERATIONS = 100
MAX_RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 8.0

# Tools that are safe to run in parallel when the LLM emits multiple tool
# calls in one assistant turn. Read-only / pure-query tools belong here;
# anything that mutates filesystem, shell state, memory, channels, or the
# approval queue stays sequential.
_CONCURRENT_SAFE_TOOLS = frozenset({
    "agent",
    "file_read", "file_list", "file_search",
    "web_search", "web_fetch",
    "get_weather", "get_time", "calculate",
    "get_user_memory", "get_context_usage",
})

# Stub inserted into the ``tool`` role message when the tool returned
# non-text blocks. OpenAI's tool role requires string content, so the
# actual image/document data rides in an immediately-following user
# message (see _build_follow_up_user_message).
_TOOL_FOLLOW_UP_STUB = "[See attached content in the next message.]"


def _is_concurrent_safe(name: str) -> bool:
    """Return True if a tool can safely run in parallel with others."""
    return name in _CONCURRENT_SAFE_TOOLS


def _block_to_openai_part(block: ContentBlock) -> dict[str, Any] | None:
    """Convert a ContentBlock to an OpenAI content part.

    Returns ``None`` when the block type has no direct OpenAI wire
    representation and must be described textually instead
    (documents without extracted text, audio without transcript, etc.).
    Only ``text`` and ``image`` have lossless wire forms today.
    """
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "image":
        return {
            "type": "image_url",
            "image_url": {"url": block.source, "detail": block.detail},
        }
    return None


def _blocks_to_openai_parts(blocks: ContentBlocks) -> list[dict[str, Any]]:
    """Convert a block list to OpenAI content parts.

    Blocks without a direct wire form (DocumentBlock, AudioBlock) are
    flattened to TextBlock via :func:`blocks_to_text` first so no
    information is silently dropped.
    """
    parts: list[dict[str, Any]] = []
    textual_pending: list[TextBlock] = []

    def _flush_textual() -> None:
        if not textual_pending:
            return
        merged = "\n".join(tb.text for tb in textual_pending)
        parts.append({"type": "text", "text": merged})
        textual_pending.clear()

    for block in blocks:
        part = _block_to_openai_part(block)
        if part is not None and block.type == "image":
            _flush_textual()
            parts.append(part)
        elif part is not None and block.type == "text":
            textual_pending.append(block)  # type: ignore[arg-type]
        else:
            # Document/audio without a lossless wire form: fall back to
            # a textual description so the LLM still sees something.
            textual_pending.append(TextBlock(text=blocks_to_text([block])))

    _flush_textual()
    return parts


def _tool_result_to_llm(
    result: Any,
) -> tuple[str, str, ContentBlocks]:
    """Convert a tool return value into LLM transport pieces.

    Returns:
        (tool_role_content, ui_display, follow_up_blocks)

        - ``tool_role_content``: string to place in the ``tool`` role
          message (OpenAI spec requires string). When the tool returned
          non-text blocks, this is a stub that points to the follow-up.
        - ``ui_display``: human-friendly summary for the UI layer.
        - ``follow_up_blocks``: non-empty when the tool returned
          non-text content. Caller must append a follow-up ``user``
          role message carrying the rendered OpenAI parts.
    """
    if isinstance(result, ToolResult):
        blocks = result.to_blocks()
        text_only = all(b.type == "text" for b in blocks)

        if text_only:
            llm_content = blocks_to_text(blocks)
            display = result.display or (
                llm_content[:200] + "..." if len(llm_content) > 200 else llm_content
            )
            return llm_content, display, []

        # Multi-modal: emit stub in tool message, carry blocks in follow-up.
        # ui_display falls back to a short description of what came back.
        display = result.display or blocks_to_text(blocks)[:200]
        if len(display) > 200:
            display = display[:200] + "..."
        return _TOOL_FOLLOW_UP_STUB, display, list(blocks)

    if isinstance(result, str):
        display = (result[:200] + "...") if len(result) > 200 else result
        return result, display, []

    # Should not happen — tools should return ToolResult or str
    logger.warning("Tool returned unexpected type %s, converting to string", type(result))
    content = str(result)
    display = (content[:200] + "...") if len(content) > 200 else content
    return content, display, []


def _build_follow_up_user_message(
    tool_call_id: str,
    tool_name: str,
    blocks: ContentBlocks,
) -> dict[str, Any]:
    """Build the user-role message that carries a tool's non-text blocks.

    OpenAI's ``tool`` role message must be a string. When a tool
    returns images or other rich content, we emit the tool message as
    a short stub and place the actual blocks in a user message that
    immediately follows, tagged so the frontend can group them with
    their originating tool call.
    """
    parts = _blocks_to_openai_parts(blocks)
    return {
        "role": "user",
        "content": parts,
        # Frontend grouping: these are internal hints, not part of the
        # OpenAI spec. Retained when persisted as JSON.
        "metadata": {
            "tool_follow_up": True,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
        },
    }


async def _materialize_blocks_for_llm(
    blocks: ContentBlocks,
    *,
    media_store: Any,
    session_id: str | None,
) -> ContentBlocks:
    """Resolve ``media://`` block sources into LLM-consumable URLs.

    Phase 18 surfaced this seam. ``ImageBlock`` returned by tools like
    ``render_chart`` carry ``media://session/hash.png`` URIs — those
    work for connectors (the dispatcher resolves via ``MediaStore.get``)
    and for the web UI (the WebSocket frame rewrites to
    ``/api/media/...``), but the *LLM provider* receives the raw URI
    and rejects it as

        Invalid 'input[N].content[M].image_url'. Expected a valid URL,
        but got a value with an invalid format.

    Calling :meth:`MediaStore.materialize_for_llm` on each block
    converts ``media://`` to either a data URL (small images) or a
    pre-signed http URL — both of which the LLM accepts. Blocks
    without ``media://`` sources, and the case where ``media_store``
    or ``session_id`` are missing, pass through unchanged so the
    function is a safe no-op for non-tool flows.

    Behavioural notes:

    - Materialization failures fall back to the original block. The
      LLM call may still 400 on that turn, but the user already saw
      the chart on their connector — better to log and keep going
      than to drop the assistant turn.
    - ``materialize_for_llm`` only acts on blocks whose source begins
      with ``media://``. Other shapes (``http(s)://``, ``data:``)
      pass through untouched, which matches the
      :class:`_ImageDispatcher` semantics on the connector side.
    """
    if media_store is None or not session_id:
        return blocks
    out: list[Any] = []
    for block in blocks:
        try:
            materialized = await media_store.materialize_for_llm(
                block, session_id=session_id,
            )
        except Exception:
            logger.exception(
                "Failed to materialize block for LLM (source=%s)",
                getattr(block, "source", "<unknown>"),
            )
            out.append(block)
            continue
        out.append(materialized)
    return out


async def _materialize_messages_for_llm(
    messages: list[Any],
    *,
    media_store: Any,
    session_id: str,
) -> list[Any]:
    """Resolve ``media://`` URIs inside OpenAI message parts.

    Phase 18 follow-up. ``_materialize_blocks_for_llm`` covers blocks
    *coming out of a tool* (still in :class:`ContentBlock` shape).
    But persisted message history is already in OpenAI parts format —
    each message has ``content`` either as a plain string (text
    messages) or as a list of parts ``[{"type": "image_url",
    "image_url": {"url": "media://..."}}]``. Replaying those
    messages on the next turn breaks the LLM call because the
    historical ``media://`` URIs were never re-resolved.

    This helper walks every message and rewrites the ``url`` field
    of any ``image_url`` part whose URL starts with ``media://``.
    Other fields, message shapes, and roles pass through unchanged
    so the function is a safe no-op for text-only history.

    Implementation notes:

    - Uses :meth:`MediaStore.get` directly rather than going through
      ``materialize_for_llm`` because we already have an
      OpenAI-parts wire shape — round-tripping through
      :class:`ContentBlock` would be theatrical.
    - Builds a small in-process cache keyed on the URI so a single
      message containing the same image twice (rare but possible)
      doesn't read from disk twice.
    - Failures fall back to leaving the URL alone. The LLM call may
      still 400 on that turn but the user already saw the chart on
      their connector. Log loud enough that operators can spot the
      cause without a full traceback per message.
    """
    cache: dict[str, str] = {}

    async def _resolve_media_url(url: str) -> str:
        if not isinstance(url, str) or not url.startswith("media://"):
            return url
        if url in cache:
            return cache[url]
        try:
            data, mime = await media_store.get(url, session_id=session_id)
        except Exception:
            logger.exception(
                "Failed to materialize message-history image %r", url,
            )
            return url
        # Encode as a data URL — small images go inline; the LLM's
        # request body can absorb tens of KB without issue. For
        # larger media the right answer is a pre-signed http URL,
        # but render_chart's PNGs sit comfortably under that.
        import base64
        encoded = base64.b64encode(data).decode("ascii")
        data_url = f"data:{mime};base64,{encoded}"
        cache[url] = data_url
        return data_url

    out: list[Any] = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            # Plain string content (the common case) — pass through.
            out.append(msg)
            continue

        new_parts: list[Any] = []
        changed = False
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                new_parts.append(part)
                continue
            image_url = part.get("image_url") or {}
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if not isinstance(url, str) or not url.startswith("media://"):
                new_parts.append(part)
                continue
            resolved = await _resolve_media_url(url)
            if resolved == url:
                new_parts.append(part)
                continue
            # Build a new part with the resolved URL; preserve any
            # ``detail`` field (low / high / auto) the original carried.
            new_image_url = dict(image_url)
            new_image_url["url"] = resolved
            new_part = dict(part)
            new_part["image_url"] = new_image_url
            new_parts.append(new_part)
            changed = True

        if changed:
            new_msg = dict(msg)
            new_msg["content"] = new_parts
            out.append(new_msg)
        else:
            out.append(msg)
    return out


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

    def _get_iteration_tokens(
        self,
        usage: Any,
        messages: list[Any],
        content: str,
        reasoning: str,
        tool_calls_data: dict[int, dict[str, str]],
    ) -> int:
        """Return total tokens for one LLM iteration.

        Uses provider-reported usage when available, falls back to
        tiktoken estimation for providers that don't support usage
        reporting in stream chunks.
        """
        if usage is not None:
            return usage.total_tokens
        # Fallback: estimate with tiktoken
        return self._estimate_tokens(messages, content, reasoning, tool_calls_data)

    def _estimate_tokens(
        self,
        messages: list[Any],
        content: str,
        reasoning: str,
        tool_calls_data: dict[int, dict[str, str]],
    ) -> int:
        """Estimate token count using tiktoken when provider doesn't report usage."""
        enc = self._get_encoder()
        total = 0
        # Input: estimate from messages
        for msg in messages:
            total += 4  # per-message overhead
            msg_content = msg.get("content") or "" if isinstance(msg, dict) else ""
            if isinstance(msg_content, str):
                total += len(enc.encode(msg_content))
            for tc in (msg.get("tool_calls", []) if isinstance(msg, dict) else []):
                fn = tc.get("function", {})
                total += len(enc.encode(fn.get("name", "")))
                total += len(enc.encode(fn.get("arguments", "")))
        # Output: content + reasoning + tool call arguments
        if content:
            total += len(enc.encode(content))
        if reasoning:
            total += len(enc.encode(reasoning))
        for tc in tool_calls_data.values():
            total += len(enc.encode(tc.get("arguments", "")))
        return total

    def _get_encoder(self) -> Any:
        """Lazy-initialize tiktoken encoder."""
        if not hasattr(self, "_encoder"):
            import tiktoken
            self._encoder = tiktoken.get_encoding("cl100k_base")
        return self._encoder

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
        media_store: Any = None,
        session_id: str | None = None,
        hook_manager: Any = None,
    ) -> AsyncGenerator[tuple[UpdateType, str, dict[str, Any]], None]:
        """Stream chat completion with automatic tool call handling.

        ``media_store`` + ``session_id`` (Phase 18) let
        :func:`_build_follow_up_user_message` resolve ``media://``
        URIs that tools return into LLM-consumable data URLs. Without
        them the LLM rejects ``image_url.url == "media://..."`` as an
        invalid value and the entire turn 400s. Both default to
        ``None`` so callers without a session-scoped MediaStore (text-
        only paths, narrow tests) keep working unchanged.

        Yields: (UpdateType, content_delta, metadata)

        Args:
            trace_metadata: Optional Langfuse trace metadata. Keys like
                ``trace_name``, ``metadata`` are passed as top-level
                kwargs for per-call tracing.
        """
        # Typed as list[Any] because we build message dicts inline for the
        # tool/assistant/user roles with shapes the OpenAI SDK TypedDicts
        # can't cleanly narrow. The dicts are still valid at the wire.
        working_messages: list[Any] = list(messages)

        # Phase 18 follow-up: walk every message and resolve any
        # ``media://session/file`` URLs embedded in ``image_url`` parts
        # to LLM-consumable URLs (typically data: URLs via
        # ``MediaStore.materialize_for_llm``). Without this, persisted
        # history from earlier turns — which stored the original
        # ``media://`` URI — breaks every subsequent LLM call with
        # ``Invalid 'input[N].content[M].image_url'``. Walks the
        # *whole* working_messages list, including the inbound
        # ``messages`` arg, so historical replays and fresh turns are
        # both safe.
        # Phase 19 follow-up: the walker MUST also run on each tool-
        # loop iteration, not just once at entry. The Phase 19
        # refactor stopped materializing follow-up blocks on the
        # outbound path (so they persist as ``media://`` URIs); but
        # tool iterations append fresh follow-ups mid-loop. Without
        # re-walking, the next iteration sends those raw URIs to the
        # LLM and Azure rejects them with ``invalid_value`` on
        # ``image_url.url``. The walker uses a per-call cache and is
        # idempotent on already-rewritten URLs, so re-walking is
        # cheap.
        turn = 0
        rejected_tools: set[str] = set()

        # Tool loop guardrails — detect repeated failures / no-progress
        from ..agents.guardrails import (
            ToolCallGuardrailController,
            ToolCallSignature,
        )

        guardrail = ToolCallGuardrailController()

        for _iteration in range(MAX_TOOL_ITERATIONS):
            turn += 1
            logger.debug(f"LLM Stream iteration {turn} with {len(working_messages)} messages")

            # Materialize ``media://`` URIs in any messages added
            # since the last iteration (or the original inbound
            # set on iteration 1). Idempotent: messages already
            # rewritten to data URLs pass through unchanged.
            if media_store is not None and session_id:
                working_messages = await _materialize_messages_for_llm(
                    working_messages,
                    media_store=media_store,
                    session_id=session_id,
                )

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
            iteration_usage = None

            stream = await self._create_with_retry(**api_kwargs)

            async for chunk in stream:
                if chunk.usage:
                    iteration_usage = chunk.usage
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

            # Yield token usage for budget enforcement
            iter_tokens = self._get_iteration_tokens(
                iteration_usage, working_messages, full_content, full_reasoning, tool_calls_data,
            )
            yield (UpdateType.USAGE, "", {
                "prompt_tokens": iteration_usage.prompt_tokens if iteration_usage else 0,
                "completion_tokens": iteration_usage.completion_tokens if iteration_usage else 0,
                "total_tokens": iter_tokens,
                "estimated": iteration_usage is None,
                "turn": turn,
            })

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
                            # Exception during tool execution
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
                        else:
                            # Successful concurrent result
                            is_error = (
                                isinstance(result, ToolResult) and result.error
                            )
                            if is_error:
                                rejected_tools.add(tc["name"])

                            llm_content, ui_display, follow_up_blocks = (
                                _tool_result_to_llm(result)
                            )

                            # --- Guardrail check (concurrent path) ---
                            sig = ToolCallSignature.from_call(tc["name"], tc["arguments"])
                            decision = guardrail.record_result(
                                sig,
                                failed=is_error,
                                result_content=llm_content if not is_error else "",
                                idempotent=tc["name"] in _CONCURRENT_SAFE_TOOLS,
                            )
                            if decision.should_block:
                                rejected_tools.add(tc["name"])
                                llm_content = f"{llm_content}\n\n[GUARDRAIL] {decision.reason}"
                            elif decision.should_warn:
                                llm_content = f"{llm_content}\n\n[GUARDRAIL] {decision.reason}"

                            yield (
                                UpdateType.TOOL, ui_display,
                                {
                                    "index": idx, "name": tc["name"],
                                    "arguments": tc["arguments"],
                                    "status": "error" if is_error else "success",
                                    "turn": turn,
                                },
                            )
                            working_messages.append({
                                "role": "tool", "tool_call_id": tc["id"],
                                "name": tc["name"], "content": llm_content,
                            })
                            yield (UpdateType.MESSAGE, "", {"message": working_messages[-1]})
                            if follow_up_blocks:
                                # Phase 19 refactor: keep ``media://``
                                # URIs *as-is* in persisted history.
                                # The inbound walker
                                # (``_materialize_messages_for_llm``)
                                # at the top of ``chat_stream``
                                # rewrites them to data URLs on every
                                # LLM call, so we don't need to do it
                                # again here. Stripping this duplicate
                                # keeps history compact AND preserves
                                # the original URI so the
                                # /api/conversations endpoint can
                                # surface chart images on resume.
                                follow_up = _build_follow_up_user_message(
                                    tool_call_id=tc["id"],
                                    tool_name=tc["name"],
                                    blocks=follow_up_blocks,
                                )
                                working_messages.append(follow_up)
                                yield (UpdateType.MESSAGE, "", {"message": follow_up})

                elif len(concurrent_items) == 1:
                    # Single concurrent tool — run sequentially (no gather overhead)
                    sequential_items = concurrent_items + sequential_items
                    concurrent_items = []

                # --- Run remaining tools sequentially ---
                for idx, tc in sequential_items:
                    try:
                        # --- Pre-tool hook ---
                        if hook_manager is not None:
                            import json as _json

                            try:
                                tc_args = _json.loads(tc["arguments"]) if tc["arguments"] else {}
                            except (ValueError, TypeError):
                                tc_args = {}
                            hook_decision = await hook_manager.run_pre_tool_call(
                                tc["name"], tc_args,
                                session_id=session_id or "",
                            )
                            if hook_decision.blocked:
                                # Hook blocked the call — return error to LLM
                                blocked_content = f"BLOCKED by hook: {hook_decision.reason}"
                                yield (
                                    UpdateType.TOOL, blocked_content,
                                    {
                                        "index": idx, "name": tc["name"],
                                        "arguments": tc["arguments"],
                                        "status": "error", "turn": turn,
                                    },
                                )
                                working_messages.append({
                                    "role": "tool", "tool_call_id": tc["id"],
                                    "name": tc["name"], "content": blocked_content,
                                })
                                yield (UpdateType.MESSAGE, "", {"message": working_messages[-1]})
                                continue

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
                            isinstance(result, ToolResult) and result.error
                        )
                        if is_error:
                            rejected_tools.add(tc["name"])

                        llm_content, ui_display, follow_up_blocks = (
                            _tool_result_to_llm(result)
                        )

                        # --- Guardrail check ---
                        sig = ToolCallSignature.from_call(tc["name"], tc["arguments"])
                        decision = guardrail.record_result(
                            sig,
                            failed=is_error,
                            result_content=llm_content if not is_error else "",
                            idempotent=tc["name"] in _CONCURRENT_SAFE_TOOLS,
                        )
                        if decision.should_block:
                            rejected_tools.add(tc["name"])
                            llm_content = f"{llm_content}\n\n[GUARDRAIL] {decision.reason}"
                        elif decision.should_warn:
                            llm_content = f"{llm_content}\n\n[GUARDRAIL] {decision.reason}"

                        yield (
                            UpdateType.TOOL, ui_display,
                            {
                                "index": idx, "name": tc["name"],
                                "arguments": tc["arguments"],
                                "status": "error" if is_error else "success",
                                "turn": turn,
                            },
                        )

                        working_messages.append({
                            "role": "tool", "tool_call_id": tc["id"],
                            "name": tc["name"], "content": llm_content,
                        })
                        yield (UpdateType.MESSAGE, "", {"message": working_messages[-1]})

                        # --- Post-tool hook ---
                        if hook_manager is not None:
                            try:
                                tc_args = _json.loads(tc["arguments"]) if tc["arguments"] else {}
                            except (ValueError, TypeError):
                                tc_args = {}
                            await hook_manager.run_post_tool_call(
                                tc["name"], tc_args,
                                result_content=llm_content,
                                error=is_error,
                                session_id=session_id or "",
                            )

                        if follow_up_blocks:
                            # Phase 19 refactor: keep ``media://``
                            # URIs as-is in persisted history; the
                            # inbound walker
                            # (``_materialize_messages_for_llm``)
                            # rewrites them on every LLM call. See
                            # the parallel branch above for the full
                            # reasoning.
                            follow_up = _build_follow_up_user_message(
                                tool_call_id=tc["id"],
                                tool_name=tc["name"],
                                blocks=follow_up_blocks,
                            )
                            working_messages.append(follow_up)
                            yield (UpdateType.MESSAGE, "", {"message": follow_up})

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
                # Break out if ask_user was called — worker pauses for user input
                if any(
                    tc["name"] == "ask_user" for tc in tool_calls_data.values()
                ):
                    break
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
