"""Tests for tools.consolidate_memory — ConsolidateMemoryTool."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from tank_backend.memory.consolidator import ConsolidationReport
from tank_backend.tools.consolidate_memory import ConsolidateMemoryTool


def _report(
    *,
    user: str = "jackson",
    promoted: list[str] | None = None,
    consolidated: list[tuple[str, list[str]]] | None = None,
    archived: list[str] | None = None,
    error: str | None = None,
) -> ConsolidationReport:
    now = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc)
    return ConsolidationReport(
        started_at=now,
        finished_at=now,
        user=user,
        candidates_scanned=10,
        promoted=promoted or [],
        consolidated=consolidated or [],
        archived=archived or [],
        error=error,
    )


class TestConsolidateMemoryTool:
    async def test_guest_user_returns_error(self):
        tool = ConsolidateMemoryTool(consolidator_factory=_unused_factory)
        result = await tool.execute(user="Guest")

        assert result.error is True
        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert "requires an identified user" in payload["error"]

    async def test_consolidator_unavailable_returns_error(self):
        tool = ConsolidateMemoryTool(
            consolidator_factory=lambda: None,
        )
        result = await tool.execute(user="jackson")

        assert result.error is True
        assert "unavailable" in result.display.lower()

    async def test_success_summary_in_display(self):
        consolidator = MagicMock()
        consolidator.run = AsyncMock(return_value=_report(
            promoted=["Allergic to peanuts"],
            consolidated=[("Prefers metric", ["Uses celsius"])],
            archived=["Old fact"],
        ))
        tool = ConsolidateMemoryTool(
            consolidator_factory=lambda: consolidator,
        )

        result = await tool.execute(user="jackson")

        assert result.error is False
        assert "1 promoted" in result.display
        assert "1 consolidated" in result.display
        assert "1 archived" in result.display
        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert payload["user"] == "jackson"
        assert payload["promoted"] == ["Allergic to peanuts"]

    async def test_error_report_surfaced(self):
        consolidator = MagicMock()
        consolidator.run = AsyncMock(return_value=_report(error="not_idle"))
        tool = ConsolidateMemoryTool(
            consolidator_factory=lambda: consolidator,
        )

        result = await tool.execute(user="jackson")

        assert result.error is True
        assert "not_idle" in result.display

    async def test_no_changes_display(self):
        consolidator = MagicMock()
        consolidator.run = AsyncMock(return_value=_report())
        tool = ConsolidateMemoryTool(
            consolidator_factory=lambda: consolidator,
        )

        result = await tool.execute(user="jackson")

        assert result.error is False
        assert "no changes" in result.display


def _unused_factory() -> None:
    raise AssertionError("factory should not be called for guest")
