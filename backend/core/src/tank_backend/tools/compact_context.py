"""CompactContextTool — user-triggered context compaction with optional focus."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

if TYPE_CHECKING:
    from ..context.manager import ContextManager


class CompactContextTool(BaseTool):
    """Force a context compaction on the live conversation.

    The tool wraps :meth:`ContextManager.compact` so the assistant can
    summarize-and-trim its own history when the user asks. Passing
    ``focus`` biases the resulting summary toward information related
    to that topic; anti-thrashing guards are bypassed because the user
    explicitly requested compaction.
    """

    def __init__(self, context_manager: ContextManager) -> None:
        self._context = context_manager

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="compact_context",
            description=(
                "Compact the current conversation history by summarizing "
                "older turns. Use when the user asks to /compact, free up "
                "context, or focus the conversation on a particular topic. "
                "Optional 'focus' biases the summary toward a topic so "
                "details unrelated to that topic may be dropped."
            ),
            parameters=[
                ToolParameter(
                    name="focus",
                    type="string",
                    description=(
                        "Optional topic to bias the summary toward "
                        "(e.g. 'API design', 'database schema'). "
                        "Leave empty for an unbiased compaction."
                    ),
                    required=False,
                    default="",
                ),
            ],
        )

    async def execute(self, focus: str = "", **_: object) -> ToolResult:
        focus_arg = focus.strip() or None
        tokens_before = self._context.count_tokens()
        await self._context.compact(focus=focus_arg)
        tokens_after = self._context.count_tokens()

        payload = {
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "focus": focus_arg,
        }
        if focus_arg:
            display = (
                f"Compacted with focus '{focus_arg}': "
                f"{tokens_before} → {tokens_after} tokens"
            )
        else:
            display = f"Compacted: {tokens_before} → {tokens_after} tokens"
        return ToolResult(
            content=json.dumps(payload, ensure_ascii=False),
            display=display,
        )
