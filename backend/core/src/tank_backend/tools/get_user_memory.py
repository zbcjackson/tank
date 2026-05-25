"""GetUserMemoryTool — surface stored user memory to the LLM via tool call."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..users import is_guest
from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

if TYPE_CHECKING:
    from ..context.manager import ContextManager


class GetUserMemoryTool(BaseTool):
    """Return everything Tank remembers about the current user.

    Wraps :meth:`ContextManager.gather_memory_snapshot` so the assistant
    can answer "what do you remember about me?" via a tool call instead
    of regex matching. ``user`` is auto-filled by the agent from the
    conversation context (the same pattern preference_tool /
    remember tools use).
    """

    def __init__(self, context_manager: ContextManager) -> None:
        self._context = context_manager

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="get_user_memory",
            description=(
                "Get everything Tank remembers about the current user: "
                "pinned facts, learned preferences, and stored mem0 facts. "
                "Call this when the user asks what you remember about "
                "them, what facts/preferences you have, or 你记得我什么 / "
                "你了解我多少 / 列出你记得的."
            ),
            parameters=[
                ToolParameter(
                    name="user",
                    type="string",
                    description=(
                        "User name (auto-filled from conversation context)"
                    ),
                    required=False,
                    default="",
                ),
            ],
        )

    async def execute(self, user: str = "", **_: object) -> ToolResult:
        if is_guest(user):
            return ToolResult(
                content=json.dumps(
                    {"error": "no stored memory for guest users"},
                    ensure_ascii=False,
                ),
                display="No stored memory for guest users",
                error=True,
            )

        pinned, learned, facts = await self._context.gather_memory_snapshot(user)

        payload = {
            "user": user,
            "pinned": pinned,
            "learned": learned,
            "facts": facts,
        }

        total = len(pinned) + len(learned) + len(facts)
        if total == 0:
            display = f"No stored memory for {user}"
        else:
            parts: list[str] = []
            if pinned:
                parts.append(f"{len(pinned)} pinned")
            if learned:
                parts.append(f"{len(learned)} learned")
            if facts:
                parts.append(f"{len(facts)} facts")
            display = f"{user}: " + ", ".join(parts)

        return ToolResult(
            content=json.dumps(payload, ensure_ascii=False),
            display=display,
        )
