"""Tool groups — cohesive sets of tools with shared construction dependencies.

Each group encapsulates the imports, dependency wiring, and conditional
registration logic for a category of tools.  ``ToolManager`` creates groups
internally — external code only sees ``ToolManager``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import BaseTool, ToolGroup

if TYPE_CHECKING:
    from ..config.models import FileAccessConfig, SandboxConfig, SkillsConfig
    from ..pipeline.bus import Bus
    from ..policy.credentials import ServiceCredentialManager
    from ..policy.file_access import FileAccessPolicy
    from ..policy.network_access import NetworkAccessPolicy

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Concrete groups
# ------------------------------------------------------------------

class DefaultToolGroup(ToolGroup):
    """Calculator, Time, Weather, EchoImage, Chart — no external dependencies.

    ``EchoImageTool`` (Phase 16) and ``ChartTool`` (Phase 18) both
    return non-text content;
    :meth:`~tank_backend.tools.manager.ToolManager.execute_tool` plus
    :class:`~tank_backend.connectors.tool_output_observer.ToolOutputObserver`
    handle the outbound-image emit. ChartTool additionally opts into
    the Phase 18 ``ToolContext`` seam to reach the session-scoped
    MediaStore for PNG persistence.
    """

    def create_tools(self) -> list[BaseTool]:
        from .calculator import CalculatorTool
        from .chart import ChartTool
        from .echo_image import EchoImageTool
        from .time import TimeTool
        from .weather import WeatherTool

        return [
            CalculatorTool(),
            TimeTool(),
            WeatherTool(),
            EchoImageTool(),
            ChartTool(),
        ]


class WebToolGroup(ToolGroup):
    """Web search and fetch tools — need credentials and network policy."""

    def __init__(
        self,
        credential_manager: ServiceCredentialManager,
        network_policy: NetworkAccessPolicy | None = None,
    ) -> None:
        self._credential_manager = credential_manager
        self._network_policy = network_policy

    def create_tools(self) -> list[BaseTool]:
        from .web_fetch import WebFetchTool
        from .web_search import WebSearchTool

        return [
            WebFetchTool(
                network_policy=self._network_policy,
            ),
            WebSearchTool(
                credential_manager=self._credential_manager,
                network_policy=self._network_policy,
            ),
        ]


class SandboxToolGroup(ToolGroup):
    """Sandbox execution tools — builds sandbox from config, owns lifecycle."""

    def __init__(
        self,
        config: SandboxConfig,
        credential_manager: ServiceCredentialManager | None = None,
    ) -> None:
        self._sandbox = None

        from ..sandbox.policy import SandboxPolicy

        policy = SandboxPolicy.from_config(config)

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
        config: FileAccessConfig,
        bus: Bus | None = None,
        policy: FileAccessPolicy | None = None,
    ) -> None:
        self._config = config
        self._bus = bus
        self._policy = policy

    def create_tools(self) -> list[BaseTool]:
        from ..policy import BackupManager, FileAccessPolicy
        from .file_delete import FileDeleteTool
        from .file_edit import FileEditTool
        from .file_list import FileListTool
        from .file_read import FileReadTool
        from .file_search import FileSearchTool
        from .file_write import FileWriteTool

        policy = self._policy or FileAccessPolicy(self._config, bus=self._bus)

        backup = BackupManager(self._config.backup)

        return [
            FileReadTool(policy),
            FileWriteTool(policy, backup),
            FileEditTool(policy, backup),
            FileDeleteTool(policy, backup),
            FileListTool(policy),
            FileSearchTool(policy),
        ]


class SkillToolGroup(ToolGroup):
    """Skills system — single router tool + catalog in system prompt."""

    def __init__(
        self, config: SkillsConfig, bus: Bus | None = None,
        tool_manager: Any = None, max_history_tokens: int = 8000,
    ) -> None:
        self._config = config
        self._bus = bus
        self._tool_manager = tool_manager
        self._max_history_tokens = max_history_tokens
        self._manager: Any = None
        self._use_skill_tool: Any = None  # ref for agent_runner wiring

    def create_tools(self) -> list[BaseTool]:
        if not self._config.enabled:
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
            UninstallSkillTool,
            UseSkillTool,
        )

        skill_dirs = [Path(d).expanduser().resolve() for d in self._config.dirs]

        registry = SkillRegistry(skill_dirs)
        registry.scan()

        reviewer = SecurityReviewer()
        self._manager = SkillManager(
            registry, reviewer, self._bus,
            auto_approve_threshold=self._config.auto_approve_threshold,
            catalog_budget_percent=self._config.catalog_budget_percent,
            catalog_budget_max_chars=self._config.catalog_budget_max_chars,
            max_history_tokens=self._max_history_tokens,
        )
        self._manager.startup()

        reviewed = [
            s for s in registry.list_all()
            if s.reviewed and s.content_hash == s.review_hash
        ]
        logger.info(
            "SkillToolGroup: %d reviewed skills, 8 management tools",
            len(reviewed),
        )

        self._use_skill_tool = UseSkillTool(self._manager)

        return [
            self._use_skill_tool,
            ListSkillsTool(self._manager),
            CreateSkillTool(self._manager),
            InstallSkillTool(self._manager),
            ReviewSkillTool(self._manager),
            UninstallSkillTool(self._manager),
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


class PreferencesToolGroup(ToolGroup):
    """User preference management tools."""

    def __init__(self, store: Any = None) -> None:
        self._store = store

    def create_tools(self) -> list[BaseTool]:
        if self._store is None:
            return []

        from .preference_tool import PreferenceTool
        from .remember import RememberTool

        return [PreferenceTool(self._store), RememberTool(self._store)]


class ContextToolGroup(ToolGroup):
    """Context management tools — operate on the live :class:`ContextManager`.

    Session-scoped: instantiated by ``Brain.__init__`` with the running
    ``ContextManager`` so the tool acts on the same instance that owns
    the current conversation's history and budget.
    """

    def __init__(self, context_manager: Any = None) -> None:
        self._context_manager = context_manager

    def create_tools(self) -> list[BaseTool]:
        if self._context_manager is None:
            return []

        from .compact_context import CompactContextTool
        from .get_context_usage import GetContextUsageTool
        from .get_user_memory import GetUserMemoryTool

        return [
            CompactContextTool(self._context_manager),
            GetContextUsageTool(self._context_manager),
            GetUserMemoryTool(self._context_manager),
        ]


class ConsolidationToolGroup(ToolGroup):
    """Dream Consolidation tool — manual trigger for the assistant.

    Constructed by Brain when ``consolidation.enabled`` is true. The
    factory builds a fresh Consolidator per invocation so the underlying
    LLM client and mem0 connection don't have to live on the long-lived
    tool instance.
    """

    def __init__(self, app_config: Any = None) -> None:
        self._app_config = app_config

    def create_tools(self) -> list[BaseTool]:
        if self._app_config is None:
            return []
        if not self._app_config.consolidation.enabled:
            return []

        from ..memory.consolidator import build_consolidator
        from .consolidate_memory import ConsolidateMemoryTool

        app_config = self._app_config

        def factory() -> Any:
            return build_consolidator(app_config)

        return [ConsolidateMemoryTool(factory)]


class ComputerUseToolGroup(ToolGroup):
    """Screenshot + mouse/keyboard automation tools for host UI control.

    Platform-aware: uses macOS-native APIs on Darwin, ydotool on Linux/Wayland.
    Requires the ``computer_use`` LLM profile. Fails gracefully when
    dependencies or profile are unavailable.
    """

    def __init__(self, app_config: Any) -> None:
        self._app_config = app_config

    def create_tools(self) -> list[BaseTool]:
        import sys

        try:
            profile = self._app_config.get_llm_profile("computer_use")
        except Exception:
            logger.info("ComputerUseToolGroup: no 'computer_use' LLM profile, skipping")
            return []

        if sys.platform == "darwin":
            return self._create_macos_tools(profile)
        else:
            return self._create_linux_tools(profile)

    def _create_macos_tools(self, profile: Any) -> list[BaseTool]:
        """Create tools using macOS-native APIs (screencapture + CGEvent)."""
        try:
            import Quartz  # noqa: F401
        except ImportError:
            logger.info(
                "ComputerUseToolGroup: pyobjc-framework-Quartz not installed, skipping. "
                "Install with: pip install pyobjc-framework-Quartz"
            )
            return []

        from .computer_use_macos import (
            ClickTool,
            KeyPressTool,
            MouseMoveTool,
            ScreenshotTool,
            ScrollTool,
            TypeTextTool,
        )

        return [
            ScreenshotTool(profile),
            ClickTool(),
            TypeTextTool(),
            KeyPressTool(),
            ScrollTool(),
            MouseMoveTool(),
        ]

    def _create_linux_tools(self, profile: Any) -> list[BaseTool]:
        """Create tools using Linux backends (portal + ydotool/pyautogui)."""
        try:
            import mss  # noqa: F401
            import pyautogui  # noqa: F401
        except (ImportError, Exception):
            logger.info("ComputerUseToolGroup: mss/pyautogui unavailable, skipping")
            return []

        from .computer_use import (
            ClickTool,
            KeyPressTool,
            MouseMoveTool,
            ScreenshotTool,
            ScrollTool,
            TypeTextTool,
        )

        return [
            ScreenshotTool(profile),
            ClickTool(),
            TypeTextTool(),
            KeyPressTool(),
            ScrollTool(),
            MouseMoveTool(),
        ]
