"""Tool groups — cohesive sets of tools with shared construction dependencies.

Each group encapsulates the imports, dependency wiring, and conditional
registration logic for a category of tools.  ``ToolManager`` creates groups
internally — external code only sees ``ToolManager``.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool, ToolGroup

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def make_approval_callback(approval_manager: Any, bus: Any = None) -> Any:
    """Create an ApprovalCallback that bridges to ApprovalManager + Bus.

    Returns an async callable matching the ``ApprovalCallback`` protocol.
    """

    async def callback(
        tool_name: str, path: str, operation: str, reason: str,
    ) -> bool:
        from ..agents.approval import (
            ApprovalRequest,
            make_approval_id,
            request_with_notification,
        )

        request = ApprovalRequest(
            approval_id=make_approval_id(),
            tool_name=tool_name,
            tool_args={"path": path, "operation": operation},
            description=f"{operation} {path} ({reason})",
            session_id="file_access",
        )
        result = await request_with_notification(approval_manager, request, bus)
        return result.approved

    return callback


# ------------------------------------------------------------------
# Concrete groups
# ------------------------------------------------------------------

class DefaultToolGroup(ToolGroup):
    """Calculator, Time, Weather — no external dependencies."""

    def create_tools(self) -> list[BaseTool]:
        from .calculator import CalculatorTool
        from .time import TimeTool
        from .weather import WeatherTool

        return [CalculatorTool(), TimeTool(), WeatherTool()]


class WebToolGroup(ToolGroup):
    """Web search and fetch tools — need credentials and network policy."""

    def __init__(
        self,
        credential_manager: Any,
        network_policy: Any = None,
        approval_callback: Any = None,
    ) -> None:
        self._credential_manager = credential_manager
        self._network_policy = network_policy
        self._approval_callback = approval_callback

    def create_tools(self) -> list[BaseTool]:
        from .web_fetch import WebFetchTool
        from .web_search import WebSearchTool

        return [
            WebFetchTool(
                network_policy=self._network_policy,
                approval_callback=self._approval_callback,
            ),
            WebSearchTool(
                credential_manager=self._credential_manager,
                network_policy=self._network_policy,
                approval_callback=self._approval_callback,
            ),
        ]


class SandboxToolGroup(ToolGroup):
    """Sandbox execution tools — builds sandbox from config, owns lifecycle."""

    def __init__(
        self,
        config: dict | None = None,
        credential_manager: Any = None,
    ) -> None:
        self._sandbox = None
        config = config or {}

        from ..sandbox.policy import SandboxPolicy

        policy = SandboxPolicy.from_dict(config)
        if not policy.enabled:
            return

        try:
            from ..sandbox.factory import SandboxFactory

            cred_env = (
                credential_manager.get_env_for_sandbox()
                if credential_manager else None
            )
            self._sandbox = SandboxFactory.create(
                policy, credential_env=cred_env or None,
            )
            logger.info("Sandbox backend created (lazily)")
        except Exception:
            logger.warning(
                "Failed to create sandbox backend — continuing without sandbox",
                exc_info=True,
            )
            self._sandbox = None

    @property
    def sandbox(self) -> Any:
        """The underlying Sandbox instance, or None."""
        return self._sandbox

    def create_tools(self) -> list[BaseTool]:
        if self._sandbox is None:
            return []

        from .manage_process import ManageProcessTool
        from .run_command import RunCommandTool

        tools: list[BaseTool] = [
            RunCommandTool(self._sandbox),
            ManageProcessTool(self._sandbox),
        ]

        caps = getattr(self._sandbox, "capabilities", None)
        if caps is not None and caps.persistent_sessions:
            from .persistent_shell import PersistentShellTool

            tools.append(PersistentShellTool(self._sandbox))
            logger.info("persistent_shell included (persistent sessions available)")
        else:
            logger.info("persistent_shell skipped (backend has no persistent sessions)")

        return tools

    async def cleanup(self) -> None:
        if self._sandbox is not None and self._sandbox.is_running:
            await self._sandbox.cleanup()


class FileToolGroup(ToolGroup):
    """File read/write/delete/list tools — need access policy and backup."""

    def __init__(
        self,
        config: dict | None = None,
        approval_callback: Any = None,
        bus: Any = None,
    ) -> None:
        self._config = config or {}
        self._approval_callback = approval_callback
        self._bus = bus

    def create_tools(self) -> list[BaseTool]:
        from ..policy import BackupManager, FileAccessPolicy
        from .file_delete import FileDeleteTool
        from .file_edit import FileEditTool
        from .file_list import FileListTool
        from .file_read import FileReadTool
        from .file_search import FileSearchTool
        from .file_write import FileWriteTool

        policy = FileAccessPolicy.from_dict(self._config, bus=self._bus)
        backup = BackupManager.from_dict(self._config.get("backup", {}))

        return [
            FileReadTool(policy, approval_callback=self._approval_callback),
            FileWriteTool(policy, backup, approval_callback=self._approval_callback),
            FileEditTool(policy, backup, approval_callback=self._approval_callback),
            FileDeleteTool(policy, backup, approval_callback=self._approval_callback),
            FileListTool(policy, approval_callback=self._approval_callback),
            FileSearchTool(policy, approval_callback=self._approval_callback),
        ]


class SkillToolGroup(ToolGroup):
    """Skills system — single router tool + catalog in system prompt."""

    def __init__(
        self, config: dict | None = None, bus: Any = None,
        tool_manager: Any = None, max_history_tokens: int = 8000,
    ) -> None:
        self._config = config or {}
        self._bus = bus
        self._tool_manager = tool_manager
        self._max_history_tokens = max_history_tokens
        self._manager: Any = None
        self._use_skill_tool: Any = None  # ref for agent_runner wiring

    def create_tools(self) -> list[BaseTool]:
        if not self._config.get("enabled", False):
            return []

        from pathlib import Path

        from ..skills.manager import SkillManager
        from ..skills.registry import SkillRegistry
        from ..skills.reviewer import SecurityReviewer
        from .skill_tools import (
            CreateSkillTool,
            InstallSkillTool,
            ListSkillsTool,
            ReloadSkillsTool,
            ReviewSkillTool,
            SearchSkillsTool,
            UseSkillTool,
        )

        raw_dirs = self._config.get("dirs", [])
        skill_dirs = [Path(d).expanduser().resolve() for d in raw_dirs]

        registry = SkillRegistry(skill_dirs)
        registry.scan()

        auto_approve_threshold = self._config.get(
            "auto_approve_threshold", "low",
        )

        reviewer = SecurityReviewer()
        self._manager = SkillManager(
            registry, reviewer, self._bus,
            auto_approve_threshold=auto_approve_threshold,
            catalog_budget_percent=self._config.get("catalog_budget_percent", 2),
            catalog_budget_max_chars=self._config.get("catalog_budget_max_chars", 12000),
            max_history_tokens=self._max_history_tokens,
        )
        self._manager.startup()

        reviewed = [
            s for s in registry.list_all()
            if s.reviewed and s.content_hash == s.review_hash
        ]
        logger.info(
            "SkillToolGroup: %d reviewed skills, 7 management tools",
            len(reviewed),
        )

        self._use_skill_tool = UseSkillTool(self._manager)

        return [
            self._use_skill_tool,
            ListSkillsTool(self._manager),
            CreateSkillTool(self._manager),
            InstallSkillTool(self._manager),
            ReviewSkillTool(self._manager),
            ReloadSkillsTool(self._manager),
            SearchSkillsTool(),
        ]

    def get_skill_catalog(self) -> str:
        """Return a compact skill catalog for system prompt injection."""
        if self._manager is None:
            return ""
        return self._manager.get_skill_catalog()

    def reload_skills(self) -> dict[str, list[str]]:
        """Rescan skill directories and return diff of changes."""
        if self._manager is None:
            return {"added": [], "removed": [], "updated": []}
        return self._manager.reload()

    def set_agent_runner(self, runner: Any) -> None:
        """Wire AgentRunner into UseSkillTool for fork-mode execution."""
        if self._use_skill_tool is not None:
            self._use_skill_tool._agent_runner = runner
