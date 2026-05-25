"""LLMSummarizer — incremental structured summaries using an LLM."""

from __future__ import annotations

import logging
from typing import Any

from ..config.models import ContextConfig

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM_PROMPT = (
    "You are a precise conversation summarizer. Your summaries preserve "
    "all factual content, decisions, and action items. "
    "You write concisely and never invent information."
)

_SUMMARY_TEMPLATE = """Summarize the conversation below into a structured summary.

## Current Task
What is the user's most recent request? (quote verbatim if possible)

## Completed Actions
List each tool call and its outcome. Format: `- <tool_name>: <brief result>`

## Active State
- Conversation topic:
- Pending questions or requests:

## Key Decisions
List any decisions made and their rationale.

## Previous Summary
{previous_section}IMPORTANT RULES:
- Preserve ALL facts, names, numbers, and technical details exactly
- Keep code snippets, file paths, and error messages unchanged
- If a Previous Summary exists, merge it with new information — never drop facts from it
- Drop completed items only if replaced by newer information
- Write in the same language as the conversation
{focus_section}
CONVERSATION TO SUMMARIZE:
{conversation}
"""

_UPDATE_TEMPLATE = """\
Update the existing summary below with new information \
from the recent conversation.

EXISTING SUMMARY:
{previous_summary}

RECENT CONVERSATION:
{conversation}

RULES:
- Preserve ALL facts from the existing summary
- Add new information from the recent conversation
- Update "Current Task" to reflect the most recent request
- Move completed items to "Completed Actions"
- Keep the same structured format
{focus_section}"""

_FOCUS_INSTRUCTION = (
    "- Prioritize preserving information related to: {focus}\n"
    "- Drop incidental details unrelated to the focus when over budget.\n"
)


class LLMSummarizer:
    """Summarize conversation history using an LLM.

    Supports incremental summaries: when a ``previous_summary`` is provided,
    the LLM updates it rather than regenerating from scratch.
    """

    def __init__(self, llm: Any, config: ContextConfig) -> None:
        self._llm = llm
        self._config = config

    async def summarize(
        self,
        messages: list[dict[str, Any]],
        previous_summary: str | None = None,
        focus: str | None = None,
    ) -> str:
        """Summarize conversation messages into a structured summary.

        Args:
            messages: Messages to summarize.
            previous_summary: Existing summary to update incrementally.
                When provided, the LLM merges new content into it.
            focus: Optional topic to bias the summary toward. When provided,
                the summarizer is instructed to prioritize information
                related to ``focus`` and drop incidental details.

        Returns:
            Structured summary text.
        """
        conversation = self._serialize_messages(messages)
        summary_budget = self._config.summary_max_tokens
        focus_section = (
            "\n" + _FOCUS_INSTRUCTION.format(focus=focus.strip()) if focus else ""
        )

        if previous_summary:
            prompt = _UPDATE_TEMPLATE.format(
                previous_summary=previous_summary,
                conversation=conversation,
                focus_section=focus_section,
            )
        else:
            previous_section = ""
            prompt = _SUMMARY_TEMPLATE.format(
                previous_section=previous_section,
                conversation=conversation,
                focus_section=focus_section,
            )

        response = await self._llm.chat_completion_async(
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=self._config.summary_temperature,
            max_tokens=summary_budget,
        )
        return response["choices"][0]["message"]["content"]

    def _serialize_messages(self, messages: list[dict[str, Any]]) -> str:
        """Serialize messages into text for the summarization prompt."""
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            name = msg.get("name")

            # Handle tool calls
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "unknown")
                    tool_args = fn.get("arguments", "")
                    parts.append(f"[tool_call:{tool_name}] {tool_args}")
                if content:
                    parts.append(f"{role}: {content}")
                continue

            # Handle tool results
            if role == "tool":
                tool_name = msg.get("name", "tool")
                # Truncate long tool results in the serialization
                truncated = content[:500] + "..." if len(content) > 500 else content
                parts.append(f"[tool_result:{tool_name}] {truncated}")
                continue

            # Regular messages
            speaker = f"{role}({name})" if name else role
            if content:
                parts.append(f"{speaker}: {content}")

        return "\n\n".join(parts)
