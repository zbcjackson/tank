"""GetContextUsageTool — report current context-budget usage to the LLM."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .base import BaseTool, ToolInfo, ToolMetadata, ToolResult

if TYPE_CHECKING:
    from ..context.manager import ContextManager


class GetContextUsageTool(BaseTool):
    """Report current conversation context-window fill and budget.

    Wraps :meth:`ContextManager.usage_snapshot` so the assistant can
    answer questions like "how full is your context?" or "how many
    tokens have we used?" by calling a tool instead of relying on
    regex pattern matching of the user's utterance.
    """

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(idempotent=True)

    def __init__(self, context_manager: ContextManager) -> None:
        self._context = context_manager

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="get_context_usage",
            description=(
                "Get current conversation context-window usage. "
                "Returns tokens used, budget, fill percentage, and "
                "compaction stats. Call this when the user asks how "
                "full the context is, how many tokens are used, "
                "context budget status, or 上下文用了多少 / "
                "上下文还剩多少 / 上下文状态."
            ),
            parameters=[],
        )

    async def execute(self, **_: object) -> ToolResult:
        snapshot = self._context.usage_snapshot()
        payload = {
            "tokens_used": snapshot.tokens_used,
            "budget": snapshot.budget,
            "context_window": snapshot.context_window,
            "fill_pct": round(snapshot.fill_pct, 4),
            "last_compaction_at": snapshot.last_compaction_at,
            "ineffective_count": snapshot.ineffective_count,
            "compaction_passes": snapshot.compaction_passes,
            "conversation_id": snapshot.conversation_id,
        }
        pct = round(snapshot.fill_pct * 100)
        display = (
            f"Context {pct}% full "
            f"({snapshot.tokens_used}/{snapshot.budget} tokens)"
        )
        return ToolResult(
            content=json.dumps(payload, ensure_ascii=False),
            display=display,
        )
