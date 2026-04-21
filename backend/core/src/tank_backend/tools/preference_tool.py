"""PreferenceTool — save, remove, or list user preferences."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

if TYPE_CHECKING:
    from ..preferences.store import PreferenceStore


class PreferenceTool(BaseTool):
    """Manage per-user learned preferences.

    The ``user`` parameter is auto-filled by the agent from conversation
    context (``AgentState.metadata["user"]``).
    """

    def __init__(self, store: PreferenceStore) -> None:
        self._store = store

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="manage_preference",
            description=(
                "Save, remove, or list user preferences. "
                "Use 'save' when the user states a preference. "
                "Use 'remove' to delete a preference. "
                "Use 'list' to show all preferences."
            ),
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action to perform: 'save', 'remove', or 'list'",
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Preference text (required for save/remove)",
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
        self, action: str = "", content: str = "", user: str = "", **_: object
    ) -> ToolResult:
        user = user or "_default"

        if action == "save":
            if not content:
                return ToolResult(
                    content=json.dumps({"error": "content is required for save"}),
                    display="Error: content is required",
                    error=True,
                )
            added = self._store.add_if_new(user, content, source="explicit")
            return ToolResult(
                content=json.dumps({"added": added, "preference": content}),
                display=f"Saved: {content}" if added else f"Already exists: {content}",
            )

        if action == "remove":
            if not content:
                return ToolResult(
                    content=json.dumps({"error": "content is required for remove"}),
                    display="Error: content is required",
                    error=True,
                )
            removed = self._store.remove(user, content)
            return ToolResult(
                content=json.dumps({"removed": removed}),
                display=f"Removed: {content}" if removed else f"Not found: {content}",
            )

        if action == "list":
            prefs = self._store.list_for_user(user)
            return ToolResult(
                content=json.dumps({"preferences": prefs, "count": len(prefs)}),
                display="\n".join(f"- {p}" for p in prefs) if prefs else "No preferences",
            )

        return ToolResult(
            content=json.dumps({"error": f"Unknown action: {action}"}),
            display=f"Error: unknown action '{action}' (use save/remove/list)",
            error=True,
        )
