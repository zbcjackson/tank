"""Tests for context.summarizer — LLMSummarizer focus parameter."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from tank_backend.config.models import ContextConfig
from tank_backend.context.summarizer import LLMSummarizer


def _make_summarizer() -> tuple[LLMSummarizer, AsyncMock]:
    llm = AsyncMock()
    llm.chat_completion_async.return_value = {
        "choices": [{"message": {"content": "summary text"}}]
    }
    cfg = ContextConfig(summary_max_tokens=200, summary_temperature=0.3)
    return LLMSummarizer(llm, cfg), llm


def _user_prompt(llm: AsyncMock) -> str:
    """Extract the user-message prompt from the most recent LLM call."""
    messages: list[dict[str, Any]] = (
        llm.chat_completion_async.call_args.kwargs["messages"]
    )
    user = next(m for m in messages if m["role"] == "user")
    return user["content"]


class TestFocus:
    async def test_focus_appears_in_initial_summary_prompt(self):
        summarizer, llm = _make_summarizer()
        await summarizer.summarize(
            [{"role": "user", "content": "hello"}],
            focus="API design",
        )
        prompt = _user_prompt(llm)
        assert "API design" in prompt
        assert "Prioritize preserving information" in prompt

    async def test_focus_appears_in_update_prompt(self):
        summarizer, llm = _make_summarizer()
        await summarizer.summarize(
            [{"role": "user", "content": "hello"}],
            previous_summary="Prior summary",
            focus="database schema",
        )
        prompt = _user_prompt(llm)
        assert "database schema" in prompt
        assert "Prior summary" in prompt
        assert "Prioritize preserving information" in prompt

    async def test_no_focus_omits_focus_instruction(self):
        summarizer, llm = _make_summarizer()
        await summarizer.summarize([{"role": "user", "content": "hello"}])
        prompt = _user_prompt(llm)
        assert "Prioritize preserving information" not in prompt

    async def test_blank_focus_omits_focus_instruction(self):
        summarizer, llm = _make_summarizer()
        # Empty string is falsy → treated as "no focus"
        await summarizer.summarize(
            [{"role": "user", "content": "hello"}],
            focus="",
        )
        prompt = _user_prompt(llm)
        assert "Prioritize preserving information" not in prompt
