"""Tests for tools.get_context_usage — GetContextUsageTool."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from brain_test_helpers import make_brain, make_mock_context

from tank_backend.context.manager import UsageSnapshot
from tank_backend.pipeline.bus import Bus
from tank_backend.tools.base import ToolResult
from tank_backend.tools.get_context_usage import GetContextUsageTool


def _make_snapshot(
    *,
    tokens_used: int = 1000,
    budget: int = 8000,
    context_window: int = 32000,
    fill_pct: float = 0.125,
    last_compaction_at: str | None = None,
    ineffective_count: int = 0,
    compaction_passes: int = 0,
    conversation_id: str | None = "conv-1",
) -> UsageSnapshot:
    return UsageSnapshot(
        tokens_used=tokens_used,
        budget=budget,
        context_window=context_window,
        fill_pct=fill_pct,
        last_compaction_at=last_compaction_at,
        ineffective_count=ineffective_count,
        compaction_passes=compaction_passes,
        conversation_id=conversation_id,
    )


def _make_context_manager(snapshot: UsageSnapshot) -> MagicMock:
    ctx = MagicMock()
    ctx.usage_snapshot.return_value = snapshot
    return ctx


class TestSchema:
    def test_info_advertises_no_parameters(self):
        ctx = _make_context_manager(_make_snapshot())
        tool = GetContextUsageTool(ctx)
        info = tool.get_info()
        assert info.name == "get_context_usage"
        assert info.parameters == []


class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_tool_result_with_snapshot_payload(self):
        snapshot = _make_snapshot(
            tokens_used=1234,
            budget=8000,
            context_window=128000,
            fill_pct=0.154,
            last_compaction_at="2026-05-24T12:00:00+00:00",
            ineffective_count=1,
            compaction_passes=2,
            conversation_id="abc",
        )
        ctx = _make_context_manager(snapshot)
        tool = GetContextUsageTool(ctx)

        result = await tool.execute()

        assert isinstance(result, ToolResult)
        assert not result.error
        ctx.usage_snapshot.assert_called_once_with()

        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert payload == {
            "tokens_used": 1234,
            "budget": 8000,
            "context_window": 128000,
            "fill_pct": 0.154,
            "last_compaction_at": "2026-05-24T12:00:00+00:00",
            "ineffective_count": 1,
            "compaction_passes": 2,
            "conversation_id": "abc",
        }

    @pytest.mark.asyncio
    async def test_display_shows_percentage_and_token_counts(self):
        snapshot = _make_snapshot(
            tokens_used=2000, budget=8000, fill_pct=0.25,
        )
        tool = GetContextUsageTool(_make_context_manager(snapshot))

        result = await tool.execute()

        assert "25%" in result.display
        assert "2000" in result.display
        assert "8000" in result.display

    @pytest.mark.asyncio
    async def test_execute_rounds_fill_percentage_to_four_places(self):
        snapshot = _make_snapshot(
            tokens_used=1234, budget=8000, fill_pct=0.15436,
        )
        tool = GetContextUsageTool(_make_context_manager(snapshot))

        result = await tool.execute()

        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert payload["fill_pct"] == 0.1544

    @pytest.mark.asyncio
    async def test_execute_concise_display(self):
        snapshot = _make_snapshot()
        tool = GetContextUsageTool(_make_context_manager(snapshot))

        result = await tool.execute()

        assert len(result.display) < 200

    @pytest.mark.asyncio
    async def test_execute_ignores_extra_kwargs(self):
        snapshot = _make_snapshot()
        tool = GetContextUsageTool(_make_context_manager(snapshot))

        result = await tool.execute(unexpected="value")

        assert isinstance(result, ToolResult)
        assert not result.error

    @pytest.mark.asyncio
    async def test_execute_zero_budget_renders_zero_percent(self):
        snapshot = _make_snapshot(tokens_used=0, budget=0, fill_pct=0.0)
        tool = GetContextUsageTool(_make_context_manager(snapshot))

        result = await tool.execute()

        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert payload["budget"] == 0
        assert payload["fill_pct"] == 0.0
        assert "0%" in result.display


class TestBrainRegistersGetContextUsageTool:
    """Brain.__init__ should register GetContextUsageTool against its ContextManager."""

    @pytest.fixture
    def tool_manager(self) -> MagicMock:
        tm = MagicMock()
        tm.approval_policy = MagicMock()
        return tm

    @pytest.fixture
    def context(self) -> MagicMock:
        return make_mock_context()

    def test_brain_registers_get_context_usage_tool(self, tool_manager, context):
        brain = make_brain(
            tool_manager=tool_manager,
            context=context,
            bus=Bus(),
        )

        registered = [
            call.args[0]
            for call in tool_manager.register_tool.call_args_list
            if call.args
        ]
        usage_tools = [t for t in registered if isinstance(t, GetContextUsageTool)]

        assert len(usage_tools) == 1, (
            "Expected exactly one GetContextUsageTool registered, "
            f"got {len(usage_tools)}"
        )
        assert usage_tools[0]._context is brain._context
