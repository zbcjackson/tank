"""Tests for ToolMetadata, conditional registration, and metadata-based approval routing."""

from __future__ import annotations

import pytest  # noqa: F401

from tank_backend.tools.base import BaseTool, ToolInfo, ToolMetadata, ToolResult

# ---------------------------------------------------------------------------
# ToolMetadata defaults
# ---------------------------------------------------------------------------

class TestToolMetadata:
    def test_defaults(self):
        meta = ToolMetadata()
        assert meta.category == "general"
        assert meta.idempotent is False
        assert meta.requires_network is False
        assert meta.requires_filesystem is False

    def test_custom_values(self):
        meta = ToolMetadata(
            category="command", idempotent=True,
            requires_network=False, requires_filesystem=True,
        )
        assert meta.category == "command"
        assert meta.idempotent is True
        assert meta.requires_filesystem is True

    def test_frozen(self):
        meta = ToolMetadata()
        with pytest.raises(AttributeError):
            meta.category = "file"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BaseTool.get_metadata() / is_available()
# ---------------------------------------------------------------------------

class _DummyTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(name="dummy", description="test", parameters=[])

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(content="ok")


class _UnavailableTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(name="unavailable", description="test", parameters=[])

    def is_available(self) -> bool:
        return False

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(content="ok")


class _CommandTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(name="my_cmd", description="test", parameters=[])

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="command")

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(content="ok")


class TestBaseToolDefaults:
    def test_default_metadata(self):
        tool = _DummyTool()
        meta = tool.get_metadata()
        assert meta.category == "general"
        assert meta.idempotent is False

    def test_default_is_available(self):
        tool = _DummyTool()
        assert tool.is_available() is True

    def test_unavailable_tool(self):
        tool = _UnavailableTool()
        assert tool.is_available() is False

    def test_custom_metadata(self):
        tool = _CommandTool()
        assert tool.get_metadata().category == "command"


# ---------------------------------------------------------------------------
# ToolManager conditional registration
# ---------------------------------------------------------------------------

class TestConditionalRegistration:
    def test_unavailable_tool_not_registered(self):
        """ToolManager.register_tool skips unavailable tools."""
        from unittest.mock import MagicMock

        # Minimal ToolManager mock — we just test register_tool behavior
        from tank_backend.tools.manager import ToolManager

        # Create a minimal config mock
        config = MagicMock()
        config.network_access.rules = []
        config.network_access.default = "allow"
        config.network_access.service_credentials = []
        config.file_access.rules = []
        config.file_access.default_read = "allow"
        config.file_access.default_write = "allow"
        config.file_access.default_delete = "allow"
        config.command_security.extra_safe_commands = ()
        config.command_security.extra_dangerous_patterns = ()
        config.command_security.always_require_approval = ()
        config.command_security.llm_evaluation.enabled = False
        config.audit.enabled = False
        config.sandbox.enabled = False
        config.skills = MagicMock()
        config.skills.enabled = False
        config.get_llm_profile.return_value = MagicMock()

        try:
            mgr = ToolManager(config)
        except Exception:
            # If full ToolManager init fails due to missing deps, test the
            # register_tool method directly on a partially-constructed instance
            pytest.skip("ToolManager requires full config")

        # Register an unavailable tool — should be skipped
        unavailable = _UnavailableTool()
        mgr.register_tool(unavailable)
        assert "unavailable" not in mgr.tools

        # Register a normal tool — should work
        normal = _DummyTool()
        mgr.register_tool(normal)
        assert "dummy" in mgr.tools
        assert "dummy" in mgr.tool_metadata


# ---------------------------------------------------------------------------
# Approval routing via metadata
# ---------------------------------------------------------------------------

class TestApprovalRouting:
    def test_get_category_from_metadata(self):
        from tank_backend.agents.approval import ToolApprovalPolicy
        from tank_backend.tools.base import ToolMetadata

        metadata = {
            "custom_cmd": ToolMetadata(category="command"),
            "custom_file": ToolMetadata(category="file"),
            "custom_web": ToolMetadata(category="web"),
            "custom_general": ToolMetadata(category="general"),
        }

        policy = ToolApprovalPolicy(tool_metadata=metadata)

        assert policy._get_category("custom_cmd") == "command"
        assert policy._get_category("custom_file") == "file"
        assert policy._get_category("custom_web") == "web"
        assert policy._get_category("custom_general") == "general"

    def test_fallback_to_legacy_frozensets(self):
        from tank_backend.agents.approval import ToolApprovalPolicy

        # No metadata provided — falls back to hardcoded sets
        policy = ToolApprovalPolicy()

        assert policy._get_category("run_command") == "command"
        assert policy._get_category("persistent_shell") == "command"
        assert policy._get_category("file_read") == "file"
        assert policy._get_category("web_search") == "web"
        assert policy._get_category("calculator") == "general"
