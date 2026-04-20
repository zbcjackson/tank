"""Tests for ToolGroup pattern and ToolManager integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def _make_app_config(**overrides):
    """Build a mock AppConfig with sensible defaults."""
    sections = {
        "network_access": {},
        "audit": {},
        "approval_policies": {},
        "sandbox": {},
        "file_access": {},
    }
    sections.update(overrides)

    cfg = MagicMock()
    cfg.get_section = MagicMock(
        side_effect=lambda key, default=None: sections.get(key, default or {}),
    )
    return cfg


# ------------------------------------------------------------------
# DefaultToolGroup
# ------------------------------------------------------------------

def test_default_group_creates_three_tools():
    tools = DefaultToolGroup().create_tools()
    names = {t.get_info().name for t in tools}
    assert names == {"get_weather", "get_time", "calculate"}


# ------------------------------------------------------------------
# SandboxToolGroup (builds from config)
# ------------------------------------------------------------------

def test_sandbox_group_disabled():
    group = SandboxToolGroup(config={"enabled": False})
    assert group.create_tools() == []
    assert group.sandbox is None


def test_sandbox_group_enabled():
    mock_sandbox = MagicMock()
    mock_sandbox.capabilities.persistent_sessions = False

    with patch(
        "tank_backend.sandbox.factory.SandboxFactory.create",
        return_value=mock_sandbox,
    ):
        group = SandboxToolGroup(
            config={"enabled": True, "backend": "docker"},
        )
        tools = group.create_tools()
        names = {t.get_info().name for t in tools}
        assert "run_command" in names
        assert "manage_process" in names
        assert "persistent_shell" not in names
        assert group.sandbox is mock_sandbox


def test_sandbox_group_with_persistent_sessions():
    mock_sandbox = MagicMock()
    mock_sandbox.capabilities.persistent_sessions = True

    with patch(
        "tank_backend.sandbox.factory.SandboxFactory.create",
        return_value=mock_sandbox,
    ):
        group = SandboxToolGroup(
            config={"enabled": True, "backend": "docker"},
        )
        tools = group.create_tools()
        names = {t.get_info().name for t in tools}
        assert "persistent_shell" in names


def test_sandbox_group_creation_failure():
    """If SandboxFactory.create raises, group returns no tools."""
    with patch(
        "tank_backend.sandbox.factory.SandboxFactory.create",
        side_effect=RuntimeError("no backend"),
    ):
        group = SandboxToolGroup(
            config={"enabled": True, "backend": "docker"},
        )
        assert group.create_tools() == []
        assert group.sandbox is None


@pytest.mark.asyncio
async def test_sandbox_group_cleanup():
    mock_sandbox = MagicMock()
    mock_sandbox.is_running = True
    mock_sandbox.cleanup = AsyncMock()
    mock_sandbox.capabilities.persistent_sessions = False

    with patch(
        "tank_backend.sandbox.factory.SandboxFactory.create",
        return_value=mock_sandbox,
    ):
        group = SandboxToolGroup(
            config={"enabled": True, "backend": "docker"},
        )
        await group.cleanup()
        mock_sandbox.cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_sandbox_group_cleanup_not_running():
    mock_sandbox = MagicMock()
    mock_sandbox.is_running = False
    mock_sandbox.cleanup = AsyncMock()
    mock_sandbox.capabilities.persistent_sessions = False

    with patch(
        "tank_backend.sandbox.factory.SandboxFactory.create",
        return_value=mock_sandbox,
    ):
        group = SandboxToolGroup(
            config={"enabled": True, "backend": "docker"},
        )
        await group.cleanup()
        mock_sandbox.cleanup.assert_not_awaited()


# ------------------------------------------------------------------
# WebToolGroup
# ------------------------------------------------------------------

def test_web_group_creates_two_tools():
    cred_mgr = MagicMock()
    tools = WebToolGroup(cred_mgr).create_tools()
    names = {t.get_info().name for t in tools}
    assert names == {"web_search", "web_fetch"}


# ------------------------------------------------------------------
# FileToolGroup
# ------------------------------------------------------------------

def test_file_group_creates_six_tools():
    tools = FileToolGroup(config={}).create_tools()
    names = {t.get_info().name for t in tools}
    assert names == {
        "file_read", "file_write", "file_edit",
        "file_delete", "file_list", "file_search",
    }


# ------------------------------------------------------------------
# ToolManager integration
# ------------------------------------------------------------------

def test_tool_manager_creates_default_tools():
    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)
    assert "calculate" in tm.tools
    assert "get_time" in tm.tools
    assert "get_weather" in tm.tools


def test_tool_manager_has_approval_manager():
    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)
    assert tm.approval_manager is not None


def test_tool_manager_has_approval_policy():
    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)
    assert tm.approval_policy is not None


def test_tool_manager_registers_file_tools():
    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)
    assert "file_read" in tm.tools
    assert "file_write" in tm.tools


def test_tool_manager_registers_web_tools():
    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)
    assert "web_search" in tm.tools
    assert "web_fetch" in tm.tools


def test_tool_manager_sandbox_disabled_by_default():
    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)
    assert "run_command" not in tm.tools


def test_tool_manager_register_tool():
    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)
    tm.register_tool(_StubTool("custom"))
    assert "custom" in tm.tools


@pytest.mark.asyncio
async def test_tool_manager_cleanup_delegates():
    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)

    # All groups should have cleanup called without error
    await tm.cleanup()


def test_tool_manager_approval_policy_from_config():
    cfg = _make_app_config(
        approval_policies={
            "always_approve": ["calculate"],
            "require_approval": ["run_command"],
            "require_approval_first_time": ["web_search"],
        }
    )
    tm = ToolManager(app_config=cfg)
    policy = tm.approval_policy
    assert not policy.needs_approval("calculate")
    assert policy.needs_approval("run_command")
    assert policy.needs_approval("web_search")
