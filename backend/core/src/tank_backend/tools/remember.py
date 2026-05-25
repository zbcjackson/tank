"""RememberTool — pin durable user facts in the preference store.

Pinned entries escape the 90-day staleness sweep and the 20-entry cap that
apply to learned/inferred preferences. This is the deliberate-write path
for facts the user wants the assistant to never forget (e.g. allergies,
hard preferences). Approval-gated so the LLM can't silently pin entries.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ..users import is_guest
from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

if TYPE_CHECKING:
    from ..preferences.store import PreferenceStore


_PINNED = "pinned"


class RememberTool(BaseTool):
    """Pin, unpin, or list durable user facts.

    Pinned facts live in the same per-user ``preferences.md`` as learned
    preferences but with ``source=pinned``, which makes them immune to
    the staleness sweep and the entry cap. The ``user`` parameter is
    auto-filled by the agent from conversation context.
    """

    def __init__(self, store: PreferenceStore) -> None:
        self._store = store

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="remember",
            description=(
                "Pin a durable fact about the user that should never be "
                "forgotten (allergies, hard preferences, identifying info). "
                "Use 'pin' when the user explicitly asks to remember "
                "something. Use 'unpin' to forget. Use 'list' to show "
                "pinned facts. Pinned facts are not subject to staleness "
                "decay or entry caps."
            ),
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action: 'pin', 'unpin', or 'list'",
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Fact text (required for pin/unpin)",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="user",
                    type="string",
                    description="User name (auto-filled from conversation context)",
                    required=False,
                    default="",
                ),
            ],
        )

    async def execute(
        self, action: str = "", content: str = "", user: str = "", **_: object,
    ) -> ToolResult:
        if is_guest(user):
            return ToolResult(
                content=json.dumps({"error": "no remember for guest users"}),
                display="Pinned facts are not available for guest users",
                error=True,
            )

        if action == "pin":
            if not content:
                return ToolResult(
                    content=json.dumps({"error": "content is required for pin"}),
                    display="Error: content is required",
                    error=True,
                )
            added = self._store.add_if_new(user, content, source=_PINNED)
            return ToolResult(
                content=json.dumps({"pinned": added, "fact": content}),
                display=f"Pinned: {content}" if added else f"Already pinned: {content}",
            )

        if action == "unpin":
            if not content:
                return ToolResult(
                    content=json.dumps({"error": "content is required for unpin"}),
                    display="Error: content is required",
                    error=True,
                )
            removed = self._store.remove(user, content)
            return ToolResult(
                content=json.dumps({"unpinned": removed}),
                display=f"Unpinned: {content}" if removed else f"Not found: {content}",
            )

        if action == "list":
            pinned = self._store.list_pinned(user)
            return ToolResult(
                content=json.dumps({"pinned": pinned, "count": len(pinned)}),
                display=(
                    "\n".join(f"- {p}" for p in pinned) if pinned
                    else "No pinned facts"
                ),
            )

        return ToolResult(
            content=json.dumps({"error": f"Unknown action: {action}"}),
            display=f"Error: unknown action '{action}' (use pin/unpin/list)",
            error=True,
        )
