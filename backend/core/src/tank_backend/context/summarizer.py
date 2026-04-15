"""LLMSummarizer — Summarizer implementation using an LLM."""

from __future__ import annotations

import logging
from typing import Any

from .config import ContextConfig

logger = logging.getLogger(__name__)


class LLMSummarizer:
    """Summarize conversation history using an LLM.

    Implements the :class:`~.session.Summarizer` protocol.
    """

    def __init__(self, llm: Any, config: ContextConfig) -> None:
        self._llm = llm
        self._config = config

    async def summarize(self, messages: list[dict[str, Any]]) -> str:
        """Summarize a list of conversation messages into a concise paragraph."""
        prompt = (
            "Summarize the following conversation concisely. "
            "Preserve key facts, decisions, and action items.\n\n"
        )
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            name = msg.get("name")
            speaker = f"{role}({name})" if name else role
            prompt += f"{speaker}: {content}\n\n"

        response = await self._llm.chat_completion_async(
            messages=[
                {
                    "role": "system",
                    "content": "You summarize conversations concisely.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=self._config.summary_temperature,
            max_tokens=self._config.summary_max_tokens,
        )
        return response["choices"][0]["message"]["content"]
