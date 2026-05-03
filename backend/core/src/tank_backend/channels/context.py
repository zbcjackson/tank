"""ChannelContextBuilder — non-destructive context derivation for channels.

Unlike ContextManager.compact() which destructively modifies ConversationData.messages,
this builder derives an LLM-ready context from a channel's full conversation history
without ever modifying it. The derived context is cached and invalidated when new
messages arrive.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import tiktoken

logger = logging.getLogger(__name__)


class Summarizer(Protocol):
    async def summarize(self, messages: list[dict[str, Any]]) -> str: ...


class ChannelContextBuilder:
    """Derives LLM-ready context from a channel's full conversation history.

    Key properties:
    - **Non-destructive**: never mutates conversation.messages
    - **Cached**: derived context is cached by conversation_id, invalidated on change
    - **Configurable**: max_tokens and keep_recent control the compaction threshold
    """

    def __init__(
        self,
        max_tokens: int = 8000,
        keep_recent: int = 5,
        summarizer: Summarizer | None = None,
    ) -> None:
        self._max_tokens = max_tokens
        self._keep_recent = keep_recent
        self._summarizer = summarizer
        self._encoder = tiktoken.get_encoding("cl100k_base")
        # cache: conversation_id -> (derived_context, message_count_at_cache_time)
        self._cache: dict[str, tuple[list[dict[str, Any]], int]] = {}

    async def build(
        self,
        messages: list[dict[str, Any]],
        conversation_id: str,
        system_prompt: str = "",
    ) -> list[dict[str, Any]]:
        """Build derived context from full conversation history.

        Args:
            messages: Full message history from ConversationData (never modified).
            conversation_id: ID for caching.
            system_prompt: Optional system prompt to prepend.

        Returns:
            A new list of messages suitable for LLM context.
        """
        msg_count = len(messages)

        # Cache hit: same message count means no new messages
        cached = self._cache.get(conversation_id)
        if cached is not None and cached[1] == msg_count:
            return cached[0]

        # Build system message
        sys_msg = {"role": "system", "content": system_prompt} if system_prompt else None

        # If messages fit within budget, pass through as-is
        all_messages = ([sys_msg] if sys_msg else []) + messages
        if self._count_tokens(all_messages) <= self._max_tokens:
            self._cache[conversation_id] = (all_messages, msg_count)
            return all_messages

        # Need compaction: summarize old, keep recent
        non_system = messages  # conversation messages (may include its own system msg)
        # Separate existing system message from conversation
        conv_system = None
        rest = non_system
        if non_system and non_system[0].get("role") == "system":
            conv_system = non_system[0]
            rest = non_system[1:]

        if len(rest) <= self._keep_recent:
            # Not enough messages to split — truncate from the front
            ctx = ([sys_msg] if sys_msg else []) + rest[-self._keep_recent:]
            self._cache[conversation_id] = (ctx, msg_count)
            return ctx

        to_summarize = rest[: -self._keep_recent]
        to_keep = rest[-self._keep_recent :]

        # Build summary
        summary_text = await self._get_summary(to_summarize, conversation_id)
        summary_msg = {
            "role": "system",
            "content": f"Previous conversation summary: {summary_text}",
        }

        prefix: list[dict[str, Any]] = []
        if sys_msg:
            prefix.append(sys_msg)
        if conv_system:
            prefix.append(conv_system)
        prefix.append(summary_msg)

        ctx = prefix + to_keep
        self._cache[conversation_id] = (ctx, msg_count)
        logger.info(
            "Channel context built for %s: %d older → summary + %d recent",
            conversation_id[:8],
            len(to_summarize),
            len(to_keep),
        )
        return ctx

    def invalidate(self, conversation_id: str) -> None:
        """Invalidate cached context for a conversation."""
        self._cache.pop(conversation_id, None)

    def _count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate token count for messages."""
        total = 0
        for msg in messages:
            total += 4  # overhead per message
            content = msg.get("content") or ""
            if isinstance(content, str):
                total += len(self._encoder.encode(content))
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                total += len(self._encoder.encode(fn.get("name", "")))
                total += len(self._encoder.encode(fn.get("arguments", "")))
                total += 4
        return total

    async def _get_summary(
        self, messages: list[dict[str, Any]], conversation_id: str,
    ) -> str:
        """Get summary for old messages, using summarizer or fallback."""
        if self._summarizer is not None:
            try:
                return await self._summarizer.summarize(messages)
            except Exception:
                logger.warning(
                    "Summarization failed for %s, using fallback",
                    conversation_id[:8],
                    exc_info=True,
                )

        # Fallback: extract user/assistant content snippets
        snippets: list[str] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and isinstance(content, str) and content:
                snippet = content[:100].replace("\n", " ")
                snippets.append(f"{role}: {snippet}")
        if snippets:
            return " | ".join(snippets[:10])
        return f"({len(messages)} earlier messages)"
