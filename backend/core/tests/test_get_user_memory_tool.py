"""Tests for tools.get_user_memory — GetUserMemoryTool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from brain_test_helpers import make_brain, make_mock_context

from tank_backend.pipeline.bus import Bus
from tank_backend.tools.base import ToolResult
from tank_backend.tools.get_user_memory import GetUserMemoryTool


def _make_context_manager(
    *,
    pinned: list[str] | None = None,
    learned: list[str] | None = None,
    facts: list[str] | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.gather_memory_snapshot = AsyncMock(
        return_value=(
            pinned or [],
            learned or [],
            facts or [],
        ),
    )
    return ctx


class TestSchema:
    def test_info_advertises_user_param_optional(self):
        ctx = _make_context_manager()
        tool = GetUserMemoryTool(ctx)
        info = tool.get_info()
        assert info.name == "get_user_memory"
        param_names = {p.name for p in info.parameters}
        assert "user" in param_names
        user_param = next(p for p in info.parameters if p.name == "user")
        assert user_param.required is False


class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_full_snapshot_payload(self):
        ctx = _make_context_manager(
            pinned=["Lives in Tokyo"],
            learned=["Prefers Celsius"],
            facts=["Likes coffee", "uses uv not pip"],
        )
        tool = GetUserMemoryTool(ctx)

        result = await tool.execute(user="Jackson")

        assert isinstance(result, ToolResult)
        assert not result.error
        ctx.gather_memory_snapshot.assert_awaited_once_with("Jackson")

        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert payload == {
            "user": "Jackson",
            "pinned": ["Lives in Tokyo"],
            "learned": ["Prefers Celsius"],
            "facts": ["Likes coffee", "uses uv not pip"],
        }

    @pytest.mark.asyncio
    async def test_display_summarizes_counts_per_bucket(self):
        ctx = _make_context_manager(
            pinned=["a", "b"],
            learned=["c"],
            facts=["x", "y", "z"],
        )
        tool = GetUserMemoryTool(ctx)

        result = await tool.execute(user="Jackson")

        assert "Jackson" in result.display
        assert "2 pinned" in result.display
        assert "1 learned" in result.display
        assert "3 facts" in result.display

    @pytest.mark.asyncio
    async def test_display_when_nothing_stored(self):
        ctx = _make_context_manager()
        tool = GetUserMemoryTool(ctx)

        result = await tool.execute(user="Jackson")

        assert not result.error
        assert "No stored memory" in result.display
        assert "Jackson" in result.display
        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert payload == {
            "user": "Jackson",
            "pinned": [],
            "learned": [],
            "facts": [],
        }

    @pytest.mark.asyncio
    async def test_guest_user_returns_error_without_calling_context(self):
        ctx = _make_context_manager()
        tool = GetUserMemoryTool(ctx)

        result = await tool.execute(user="Guest")

        assert result.error is True
        ctx.gather_memory_snapshot.assert_not_called()
        assert isinstance(result.content, str)
        payload = json.loads(result.content)
        assert "error" in payload

    @pytest.mark.asyncio
    async def test_unknown_user_returns_error(self):
        ctx = _make_context_manager()
        tool = GetUserMemoryTool(ctx)

        result = await tool.execute(user="Unknown")

        assert result.error is True
        ctx.gather_memory_snapshot.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_user_returns_error(self):
        ctx = _make_context_manager()
        tool = GetUserMemoryTool(ctx)

        result = await tool.execute(user="")

        assert result.error is True
        ctx.gather_memory_snapshot.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_user_treated_as_guest(self):
        ctx = _make_context_manager()
        tool = GetUserMemoryTool(ctx)

        result = await tool.execute()

        assert result.error is True
        ctx.gather_memory_snapshot.assert_not_called()


class TestBrainRegistersGetUserMemoryTool:
    """Brain.__init__ should register GetUserMemoryTool against its ContextManager."""

    @pytest.fixture
    def tool_manager(self) -> MagicMock:
        tm = MagicMock()
        tm.approval_policy = MagicMock()
        return tm

    @pytest.fixture
    def context(self) -> MagicMock:
        return make_mock_context()

    def test_brain_registers_get_user_memory_tool(self, tool_manager, context):
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
        memory_tools = [t for t in registered if isinstance(t, GetUserMemoryTool)]

        assert len(memory_tools) == 1, (
            "Expected exactly one GetUserMemoryTool registered, "
            f"got {len(memory_tools)}"
        )
        assert memory_tools[0]._context is brain._context
