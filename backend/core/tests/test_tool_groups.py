"""Tests for ToolGroup pattern and ToolManager integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tank_backend.config.models import (
    FileAccessConfig,
    SandboxConfig,
)
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
    from tank_backend.config.models import (
        AuditConfig,
        CommandSecurityConfig,
        FileAccessConfig,
        NetworkAccessConfig,
        SandboxConfig,
        SkillsConfig,
    )

    cfg = MagicMock()
    cfg.network_access = overrides.get("network_access", NetworkAccessConfig())
    cfg.file_access = overrides.get("file_access", FileAccessConfig())
    cfg.audit = overrides.get("audit", AuditConfig())
    cfg.command_security = overrides.get("command_security", CommandSecurityConfig())
    cfg.sandbox = overrides.get("sandbox", SandboxConfig(enabled=False))
    cfg.skills = overrides.get("skills", SkillsConfig(enabled=False))
    cfg.get_llm_profile = MagicMock(
        side_effect=lambda name: MagicMock(
            api_key="test", model="test", base_url="http://test",
            extra_headers={}, stream_options=False,
        ),
    )
    return cfg


# ------------------------------------------------------------------
# DefaultToolGroup
# ------------------------------------------------------------------

def test_default_group_creates_five_tools():
    tools = DefaultToolGroup().create_tools()
    names = {t.get_info().name for t in tools}
    # Phase 18 added render_chart — the second DefaultToolGroup tool
    # that returns non-text content. All five remain dependency-free
    # at instantiation time (matplotlib import is deferred to first
    # chart render).
    assert names == {
        "get_weather", "get_time", "calculate",
        "echo_image", "render_chart",
    }


# ------------------------------------------------------------------
# SandboxToolGroup (builds from config)
# ------------------------------------------------------------------

def test_sandbox_group_disabled():
    group = SandboxToolGroup(config=SandboxConfig(enabled=False))
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
            config=SandboxConfig(enabled=True, backend="docker"),
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
            config=SandboxConfig(enabled=True, backend="docker"),
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
            config=SandboxConfig(enabled=True, backend="docker"),
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
            config=SandboxConfig(enabled=True, backend="docker"),
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
            config=SandboxConfig(enabled=True, backend="docker"),
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
    tools = FileToolGroup(config=FileAccessConfig()).create_tools()
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
    """Command tools require approval by default (no command arg), others auto-approve."""
    from tank_backend.policy.verdict import AccessLevel

    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)
    policy = tm.approval_policy
    # Command tools without command arg → require approval
    assert policy.evaluate("run_command").level == AccessLevel.REQUIRE_APPROVAL
    assert policy.evaluate("persistent_shell").level == AccessLevel.REQUIRE_APPROVAL
    # Command tools with safe command → auto-approve
    v = policy.evaluate("run_command", {"command": "ls -la"})
    assert v.level == AccessLevel.ALLOW
    # Non-command tools → auto-approve
    assert policy.evaluate("calculate").level == AccessLevel.ALLOW
    assert policy.evaluate("web_search").level == AccessLevel.ALLOW


def test_array_typed_param_includes_items_in_openai_schema():
    """Regression for Phase 18: Azure/OpenAI rejected the chart tool
    because ``ToolManager.get_openai_tools`` produced an array schema
    without an ``items`` key — the OpenAI function-calling spec
    requires it. The fix added ``items: {}`` as a permissive default
    in the auto-builder; tools that need a tighter shape (ChartTool)
    override via ``get_raw_schema``.

    Without this default, the LLM rejected the entire tools array
    on every request — breaking not just chart rendering but every
    other tool too. Pinning this prevents a regression that would
    take down the whole tool surface.
    """
    from tank_backend.tools.base import BaseTool, ToolInfo, ToolParameter, ToolResult

    class _ArrayTool(BaseTool):
        def get_info(self) -> ToolInfo:
            return ToolInfo(
                name="test_array_tool",
                description="Test tool with an array param.",
                parameters=[
                    ToolParameter(
                        name="items_list",
                        type="array",
                        description="Some items.",
                        required=True,
                    ),
                ],
            )

        async def execute(self, **_kwargs) -> ToolResult:
            return ToolResult(content="ok")

    cfg = _make_app_config()
    tm = ToolManager(app_config=cfg)
    tm.tools["test_array_tool"] = _ArrayTool()

    schemas = tm.get_openai_tools()
    schema = next(s for s in schemas if s["function"]["name"] == "test_array_tool")
    items_list = schema["function"]["parameters"]["properties"]["items_list"]
    assert items_list["type"] == "array"
    # Permissive empty-object items satisfies the OpenAI validator.
    # Tools that want a tighter shape ship a get_raw_schema override.
    assert "items" in items_list
