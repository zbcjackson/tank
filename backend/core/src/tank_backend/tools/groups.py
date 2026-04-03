"""Tool groups — cohesive sets of tools with shared construction dependencies.

Each group encapsulates the imports, dependency wiring, and conditional
registration logic for a category of tools.  ``ToolManager`` stays a pure
registry; the composition root (``Assistant``) creates groups and feeds
their tools into the manager.
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
    """Web search and scraping tools — need credentials and network policy."""

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
        from .web_scraper import WebScraperTool
        from .web_search import WebSearchTool

        return [
            WebScraperTool(
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
    """Sandbox execution tools — need a Sandbox backend instance."""

    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox

    def create_tools(self) -> list[BaseTool]:
        from .sandbox_exec import SandboxExecTool
        from .sandbox_process import SandboxProcessTool

        tools: list[BaseTool] = [
            SandboxExecTool(self._sandbox),
            SandboxProcessTool(self._sandbox),
        ]

        caps = getattr(self._sandbox, "capabilities", None)
        if caps is not None and caps.persistent_sessions:
            from .sandbox_bash import SandboxBashTool

            tools.append(SandboxBashTool(self._sandbox))
            logger.info("sandbox_bash included (persistent sessions available)")
        else:
            logger.info("sandbox_bash skipped (backend has no persistent sessions)")

        return tools


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
        from .file_list import FileListTool
        from .file_read import FileReadTool
        from .file_write import FileWriteTool

        policy = FileAccessPolicy.from_dict(self._config, bus=self._bus)
        backup = BackupManager.from_dict(self._config.get("backup", {}))

        return [
            FileReadTool(policy, approval_callback=self._approval_callback),
            FileWriteTool(policy, backup, approval_callback=self._approval_callback),
            FileDeleteTool(policy, backup, approval_callback=self._approval_callback),
            FileListTool(policy, approval_callback=self._approval_callback),
        ]
