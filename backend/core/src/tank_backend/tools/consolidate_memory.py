"""ConsolidateMemoryTool — manually trigger Dream Consolidation via tool call."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..users import is_guest
from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

if TYPE_CHECKING:
    from ..memory.consolidator import Consolidator


class ConsolidateMemoryTool(BaseTool):
    """Run Dream Consolidation for the current user, on demand.

    The factory builds a fresh :class:`Consolidator` per invocation (the
    LLM client and mem0 connection are cheap to wire). ``user`` is
    auto-filled by the agent from the conversation context.
    """

    def __init__(
        self,
        consolidator_factory: Callable[[], Consolidator | None],
    ) -> None:
        self._factory = consolidator_factory

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="consolidate_memory",
            description=(
                "Run Dream Consolidation now: scan stored facts and "
                "preferences, promote durable user truths to pinned, "
                "merge near-duplicates, archive stale entries, and "
                "append a dated entry to ~/.tank/DREAMS.md. Call this "
                "when the user asks to clean up memory, consolidate, "
                "or 整理一下记忆 / 巩固记忆."
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
                    {"error": "consolidation requires an identified user"},
                    ensure_ascii=False,
                ),
                display="Consolidation requires an identified user",
                error=True,
            )

        consolidator = self._factory()
        if consolidator is None:
            return ToolResult(
                content=json.dumps(
                    {"error": "consolidator unavailable"},
                    ensure_ascii=False,
                ),
                display=(
                    "Consolidator unavailable — check consolidation, "
                    "memory, or preferences config."
                ),
                error=True,
            )

        report = await consolidator.run(user, force=True)

        payload = {
            "user": report.user,
            "candidates_scanned": report.candidates_scanned,
            "promoted": report.promoted,
            "consolidated": report.consolidated,
            "archived": report.archived,
            "error": report.error,
        }

        if report.error:
            display = f"Consolidation skipped: {report.error}"
            return ToolResult(
                content=json.dumps(payload, ensure_ascii=False),
                display=display,
                error=True,
            )

        parts: list[str] = []
        if report.promoted:
            parts.append(f"{len(report.promoted)} promoted")
        if report.consolidated:
            parts.append(f"{len(report.consolidated)} consolidated")
        if report.archived:
            parts.append(f"{len(report.archived)} archived")
        if not parts:
            parts.append("no changes")
        display = f"Consolidated {user}: " + ", ".join(parts)
        return ToolResult(
            content=json.dumps(payload, ensure_ascii=False),
            display=display,
        )
