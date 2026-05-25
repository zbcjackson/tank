"""Tests for tools.compact_context — CompactContextTool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from brain_test_helpers import make_brain, make_mock_context

from tank_backend.pipeline.bus import Bus
from tank_backend.tools.base import ToolResult
from tank_backend.tools.compact_context import CompactContextTool


def _make_context_manager(*, before: int, after: int) -> MagicMock:
    ctx = MagicMock()
    ctx.count_tokens.side_effect = [before, after]
    ctx.compact = AsyncMock()
    return ctx


class TestSchema:
    def test_info_advertises_focus_param(self):
        ctx = _make_context_manager(before=0, after=0)
        tool = CompactContextTool(ctx)
        info = tool.get_info()
        assert info.name == "compact_context"
        param_names = {p.name for p in info.parameters}
        assert "focus" in param_names
        focus_param = next(p for p in info.parameters if p.name == "focus")
        assert focus_param.required is False


class TestExecute:
    async def test_compact_without_focus_passes_none(self):
        ctx = _make_context_manager(before=8000, after=2000)
        tool = CompactContextTool(ctx)

        result = await tool.execute()

        assert isinstance(result, ToolResult)
        assert not result.error
        ctx.compact.assert_awaited_once_with(focus=None)
        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert payload == {
            "tokens_before": 8000,
            "tokens_after": 2000,
            "focus": None,
        }
        assert "8000" in result.display
        assert "2000" in result.display

    async def test_compact_with_focus_forwards_to_manager(self):
        ctx = _make_context_manager(before=5000, after=1500)
        tool = CompactContextTool(ctx)

        result = await tool.execute(focus="API design")

        assert isinstance(result, ToolResult)
        ctx.compact.assert_awaited_once_with(focus="API design")
        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert payload["focus"] == "API design"
        assert "API design" in result.display

    async def test_blank_focus_treated_as_none(self):
        ctx = _make_context_manager(before=100, after=100)
        tool = CompactContextTool(ctx)

        await tool.execute(focus="   ")

        ctx.compact.assert_awaited_once_with(focus=None)

    async def test_returns_tool_result_with_concise_display(self):
        ctx = _make_context_manager(before=1234, after=567)
        tool = CompactContextTool(ctx)

        result = await tool.execute()

        assert isinstance(result, ToolResult)
        assert len(result.display) < 200


class TestBrainRegistersCompactContextTool:
    """Brain.__init__ should register CompactContextTool against its ContextManager."""

    @pytest.fixture
    def tool_manager(self) -> MagicMock:
        tm = MagicMock()
        tm.approval_policy = MagicMock()
        return tm

    @pytest.fixture
    def context(self) -> MagicMock:
        return make_mock_context()

    def test_brain_registers_compact_context_tool(self, tool_manager, context):
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
        compact_tools = [t for t in registered if isinstance(t, CompactContextTool)]

        assert len(compact_tools) == 1, (
            "Expected exactly one CompactContextTool registered, "
            f"got {len(compact_tools)}"
        )
        assert compact_tools[0]._context is brain._context
