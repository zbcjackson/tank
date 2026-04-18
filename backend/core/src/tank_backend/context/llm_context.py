"""LLMContext — windowed view of conversation for LLM consumption.

This is a derived, cached view that applies compaction strategies
(truncation or summarization) to fit within token budgets.

The underlying Conversation is never mutated — LLMContext is rebuilt
when the conversation grows beyond the cached state.
"""

from __future__ import annotations

import logging
from typing import Any

import tiktoken

from .config import ContextConfig

logger = logging.getLogger(__name__)


class LLMContext:
    """Windowed view of conversation messages for LLM consumption.

    Responsibilities:
    - Token counting
    - Compaction: truncation (sync, fast) and summarization (async, preserves context)
    - Caching the compacted view to avoid recomputation on every turn
    - Owning the summarizer

    Never mutates the source conversation.
    """

    def __init__(
        self,
        config: ContextConfig,
        app_config: Any = None,
    ):
        self._config = config
        self._encoder = tiktoken.get_encoding("cl100k_base")
        self._summarizer = self._create_summarizer(app_config)

        # Cache state
        self._cached_view: list[dict[str, Any]] | None = None
        self._cached_at_message_count: int = 0

    def _create_summarizer(self, app_config: Any) -> Any:
        """Create LLMSummarizer using 'summarization' profile, fallback to 'default'."""
        if app_config is None:
            return None
        from ..llm.profile import create_llm_from_profile
        from .summarizer import LLMSummarizer

        try:
            profile = app_config.get_llm_profile("summarization")
        except (KeyError, ValueError):
            try:
                profile = app_config.get_llm_profile("default")
            except (KeyError, ValueError):
                return None
        llm = create_llm_from_profile(profile)
        return LLMSummarizer(llm, self._config)

    def get_messages(
        self,
        conversation_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Get compacted view of messages for LLM.

        Returns cached view if conversation hasn't grown since last compaction.
        Otherwise, recomputes using truncation (sync).

        For summarization (async), use get_messages_async().
        """
        current_count = len(conversation_messages)

        # Return cached view if still valid
        if (
            self._cached_view is not None
            and self._cached_at_message_count == current_count
        ):
            return self._cached_view

        # Recompute view
        total = self._count_tokens(conversation_messages)
        budget = self._config.max_history_tokens

        if total <= budget:
            # Under budget — return shallow copy
            view = list(conversation_messages)
        else:
            # Over budget — truncate
            view = self._truncated_view(conversation_messages, budget)

        # Cache and return
        self._cached_view = view
        self._cached_at_message_count = current_count
        return view

    async def get_messages_async(
        self,
        conversation_messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Get compacted view with summarization (async).

        Tries summarization first (preserves context), falls back to truncation.
        Updates cache on success.
        """
        current_count = len(conversation_messages)

        # Return cached view if still valid
        if (
            self._cached_view is not None
            and self._cached_at_message_count == current_count
        ):
            return self._cached_view

        total = self._count_tokens(conversation_messages)
        budget = self._config.max_history_tokens

        if total <= budget:
            view = list(conversation_messages)
            self._cached_view = view
            self._cached_at_message_count = current_count
            return view

        # Try summarization
        system_msg = conversation_messages[0]
        rest = conversation_messages[1:]
        keep_n = self._config.keep_recent_messages

        if len(rest) > keep_n and self._summarizer is not None:
            to_summarize = rest[:-keep_n]
            to_keep = rest[-keep_n:]
            try:
                summary_text = await self._summarizer.summarize(to_summarize)
                summary_msg: dict[str, str] = {
                    "role": "system",
                    "content": f"Previous conversation summary: {summary_text}",
                }
                view = [system_msg, summary_msg] + to_keep
                logger.info(
                    "LLM context summarized: %d messages → summary + %d recent "
                    "(conversation unchanged at %d messages)",
                    len(to_summarize),
                    keep_n,
                    current_count,
                )
                self._cached_view = view
                self._cached_at_message_count = current_count
                return view
            except Exception:
                logger.warning(
                    "Summarization failed, falling back to truncation",
                    exc_info=True,
                )

        # Fallback to truncation
        view = self._truncated_view(conversation_messages, budget)
        self._cached_view = view
        self._cached_at_message_count = current_count
        return view

    def invalidate_cache(self) -> None:
        """Invalidate cached view — forces recomputation on next get_messages()."""
        self._cached_view = None
        self._cached_at_message_count = 0

    def _truncated_view(
        self,
        messages: list[dict[str, Any]],
        budget: int,
    ) -> list[dict[str, Any]]:
        """Return truncated copy that fits within token budget.

        Keeps system message + as many recent messages as fit.
        """
        system_msg = messages[0]
        rest = messages[1:]

        system_tokens = self._count_tokens([system_msg])
        remaining_budget = budget - system_tokens
        keep_from = len(rest)
        running = 0

        for i in range(len(rest) - 1, -1, -1):
            msg_tokens = self._count_tokens([rest[i]])
            if running + msg_tokens > remaining_budget:
                break
            running += msg_tokens
            keep_from = i

        view = [system_msg] + rest[keep_from:]
        logger.info(
            "LLM context truncated: %d → %d tokens (%d of %d messages)",
            self._count_tokens(messages),
            self._count_tokens(view),
            len(view),
            len(messages),
        )
        return view

    def _count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate token count for messages."""
        total = 0
        for msg in messages:
            total += 4  # ~4 tokens overhead per message
            content = msg.get("content") or ""
            if isinstance(content, str):
                total += len(self._encoder.encode(content))
        return total
