"""Tests for ToolGroup pattern and ToolManager registry."""

from __future__ import annotations

from unittest.mock import MagicMock

from tank_backend.tools.base import BaseTool, ToolInfo
from tank_backend.tools.groups import (
    DefaultToolGroup,
    FileToolGroup,
    SandboxToolGroup,
    WebToolGroup,
)
from tank_backend.tools.manager import ToolManager

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

class _StubTool(BaseTool):
    """Minimal tool for testing registration."""

    def __init__(self, name: str) -> None:
        self._name = name

    def get_info(self) -> ToolInfo:
        return ToolInfo(name=self._name, description="stub", parameters=[])

    async def execute(self, **kwargs):
        return {"ok": True}


# ------------------------------------------------------------------
# ToolManager registry
# ------------------------------------------------------------------

def test_register_tool():
    tm = ToolManager()
    tm.register_tool(_StubTool("alpha"))
    assert "alpha" in tm.tools


def test_register_all():
    tm = ToolManager()
    tm.register_all([_StubTool("a"), _StubTool("b"), _StubTool("c")])
    assert set(tm.tools.keys()) == {"a", "b", "c"}


def test_register_all_empty():
    tm = ToolManager()
    tm.register_all([])
    assert tm.tools == {}


# ------------------------------------------------------------------
# DefaultToolGroup
# ------------------------------------------------------------------

def test_default_group_creates_three_tools():
    tools = DefaultToolGroup().create_tools()
    names = {t.get_info().name for t in tools}
    assert names == {"get_weather", "get_time", "calculate"}


# ------------------------------------------------------------------
# SandboxToolGroup
# ------------------------------------------------------------------

def test_sandbox_group_without_persistent_sessions():
    sandbox = MagicMock()
    sandbox.capabilities.persistent_sessions = False

    tools = SandboxToolGroup(sandbox).create_tools()
    names = {t.get_info().name for t in tools}
    assert "run_command" in names
    assert "manage_process" in names
    assert "persistent_shell" not in names


def test_sandbox_group_with_persistent_sessions():
    sandbox = MagicMock()
    sandbox.capabilities.persistent_sessions = True

    tools = SandboxToolGroup(sandbox).create_tools()
    names = {t.get_info().name for t in tools}
    assert "run_command" in names
    assert "manage_process" in names
    assert "persistent_shell" in names


def test_sandbox_group_no_capabilities_attr():
    """Sandbox without capabilities attribute should skip persistent_shell."""
    sandbox = MagicMock(spec=[])  # no attributes at all

    tools = SandboxToolGroup(sandbox).create_tools()
    names = {t.get_info().name for t in tools}
    assert "persistent_shell" not in names
    assert len(tools) == 2


# ------------------------------------------------------------------
# WebToolGroup
# ------------------------------------------------------------------

def test_web_group_creates_two_tools():
    cred_mgr = MagicMock()
    tools = WebToolGroup(cred_mgr).create_tools()
    names = {t.get_info().name for t in tools}
    assert names == {"web_search", "web_scraper"}


# ------------------------------------------------------------------
# FileToolGroup
# ------------------------------------------------------------------

def test_file_group_creates_four_tools():
    tools = FileToolGroup(config={}).create_tools()
    names = {t.get_info().name for t in tools}
    assert names == {"file_read", "file_write", "file_delete", "file_list"}


# ------------------------------------------------------------------
# Integration: groups → manager
# ------------------------------------------------------------------

def test_groups_feed_into_manager():
    tm = ToolManager()
    tm.register_all(DefaultToolGroup().create_tools())
    assert len(tm.tools) == 3

    cred_mgr = MagicMock()
    tm.register_all(WebToolGroup(cred_mgr).create_tools())
    assert len(tm.tools) == 5

    tm.register_all(FileToolGroup(config={}).create_tools())
    assert len(tm.tools) == 9
