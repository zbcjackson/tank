"""PromptAssembler — compiles the final system prompt from multiple sources.

Assembly order:
1. [BASE]             Security boundaries + platform context (always from defaults)
2. [IDENTITY]         SOUL.md  (user's ~/.tank/SOUL.md or default)
3. [USER PREFERENCES] USER.md  (user's ~/.tank/USER.md or default)
4. [GLOBAL RULES]     AGENTS.md (user's ~/.tank/AGENTS.md or default)
5. [WORKSPACE RULES]  Discovered AGENTS.md chain (root → leaf)
6. [SCOPE]            Auto-generated active-paths / scope-change notes

Priority: more-specific (deeper) workspace rules take precedence over general
ones.  base.md security boundaries are non-negotiable and cannot be overridden.
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import FileCache
from .resolver import AgentsResolver
from .sanitizer import sanitize

logger = logging.getLogger(__name__)

_DEFAULTS_DIR = Path(__file__).parent / "defaults"
_USER_DIR = Path("~/.tank").expanduser()

SECTION_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class PromptScope:
    """Snapshot of which workspace AGENTS.md files are active."""

    workspace_agents: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssemblerConfig:
    """Configuration for the PromptAssembler."""

    user_dir: str = ""
    defaults_dir: str = ""

    def __post_init__(self) -> None:
        # Frozen dataclass — use object.__setattr__ for defaults
        if not self.user_dir:
            object.__setattr__(self, "user_dir", str(_USER_DIR))
        if not self.defaults_dir:
            object.__setattr__(self, "defaults_dir", str(_DEFAULTS_DIR))


class PromptAssembler:
    """Assembles the system prompt from multiple source files.

    Create one instance per session.  Call :meth:`assemble` to get the
    current system prompt.  The assembler subscribes to the Bus internally
    (via :class:`AgentsResolver`) so workspace ``AGENTS.md`` files are
    discovered lazily when tools access paths.
    """

    def __init__(
        self,
        bus: Any = None,
        config: AssemblerConfig | None = None,
    ) -> None:
        self._config = config or AssemblerConfig()
        self._cache = FileCache()
        self._resolver = AgentsResolver(bus=bus)
        self._previous_scope = PromptScope()
        self._needs_rebuild = True
        self._cached_prompt: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def resolver(self) -> AgentsResolver:
        """Access the underlying resolver (e.g. for manual ``resolve_chain``)."""
        return self._resolver

    def needs_rebuild(self) -> bool:
        """True when the prompt should be reassembled before the next LLM call."""
        return self._needs_rebuild or self._resolver.has_new_discovery

    def assemble(self) -> str:
        """Assemble the full system prompt from all sources."""
        sections: list[str] = []

        # 1. BASE — always from defaults, never user-overridden
        base = self._load_default("base.md")
        if base:
            sections.append(self._fill_platform_context(base))

        # 2. IDENTITY — SOUL.md
        soul = self._load_user_or_default("SOUL.md")
        if soul:
            sections.append(soul)

        # 3. USER PREFERENCES — USER.md
        user = self._load_user_or_default("USER.md")
        if user:
            sections.append(user)

        # 4. GLOBAL RULES — AGENTS.md
        global_agents = self._load_user_or_default("AGENTS.md")
        if global_agents:
            sections.append(global_agents)

        # 5. WORKSPACE RULES — discovered AGENTS.md chain
        workspace_section = self._build_workspace_section()
        if workspace_section:
            sections.append(workspace_section)

        # 6. SCOPE — active paths and change notes
        current_scope = PromptScope(
            workspace_agents=tuple(sorted(self._resolver.all_discovered)),
        )
        scope_section = self._build_scope_section(current_scope)
        if scope_section:
            sections.append(scope_section)

        self._previous_scope = current_scope
        self._resolver.reset_discovery_flag()
        self._needs_rebuild = False
        self._cached_prompt = SECTION_SEPARATOR.join(sections)

        logger.info(
            "System prompt assembled (%d chars, %d sections, workspace_agents=%s)",
            len(self._cached_prompt),
            len(sections),
            list(current_scope.workspace_agents) or "none",
        )
        return self._cached_prompt

    def mark_dirty(self) -> None:
        """Force a rebuild on the next :meth:`assemble` call."""
        self._needs_rebuild = True

    def get_base_rules(self) -> str:
        """Return base security rules (for sub-agent prompt building)."""
        content = self._load_default("base.md")
        if content:
            return self._fill_platform_context(content)
        return ""

    def get_workspace_rules_for(self, paths: list[str]) -> str:
        """Return workspace AGENTS.md content relevant to *paths*.

        Used by :class:`AgentRunner` to build sub-agent prompts.
        """
        if not paths:
            return ""

        # Collect unique AGENTS.md files from all paths
        seen: set[str] = set()
        ordered: list[str] = []
        for p in paths:
            for agents_path in self._resolver.resolve_chain(p):
                if agents_path not in seen:
                    seen.add(agents_path)
                    ordered.append(agents_path)

        if not ordered:
            return ""

        parts: list[str] = []
        for agents_path in ordered:
            content = self._cache.read(agents_path)
            if content is None:
                continue
            sanitized = sanitize(content, source_path=agents_path)
            if sanitized:
                parts.append(f"[From {agents_path}]\n{sanitized}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # File loading helpers
    # ------------------------------------------------------------------

    def _load_default(self, filename: str) -> str | None:
        """Load a file from the defaults directory only."""
        defaults_path = Path(self._config.defaults_dir) / filename
        content = self._cache.read(defaults_path)
        if content is not None:
            return sanitize(content, source_path=str(defaults_path))
        return None

    def _load_user_or_default(self, filename: str) -> str | None:
        """Load from ``~/.tank/`` if it exists, otherwise from defaults."""
        user_path = Path(self._config.user_dir) / filename
        content = self._cache.read(user_path)
        if content is not None:
            logger.debug("Loaded user file: %s", user_path)
            return sanitize(content, source_path=str(user_path))

        defaults_path = Path(self._config.defaults_dir) / filename
        content = self._cache.read(defaults_path)
        if content is not None:
            logger.debug("Loaded default file: %s", defaults_path)
            return sanitize(content, source_path=str(defaults_path))

        logger.warning(
            "Prompt file not found: %s (checked %s and %s)",
            filename,
            user_path,
            defaults_path,
        )
        return None

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _build_workspace_section(self) -> str:
        """Build the workspace rules section from discovered AGENTS.md files."""
        discovered = sorted(self._resolver.all_discovered)
        if not discovered:
            return ""

        parts: list[str] = ["WORKSPACE RULES:"]
        for agents_path in discovered:
            content = self._cache.read(agents_path)
            if content is None:
                continue
            sanitized = sanitize(content, source_path=agents_path)
            if sanitized:
                parts.append(f"[From {agents_path}]\n{sanitized}")

        return "\n\n".join(parts) if len(parts) > 1 else ""

    def _build_scope_section(self, current: PromptScope) -> str:
        """Build scope info and scope-change notes."""
        lines: list[str] = ["ACTIVE SCOPE:"]

        if current.workspace_agents:
            lines.append("Workspace rules loaded from:")
            for p in current.workspace_agents:
                lines.append(f"  - {p}")
            lines.append(
                "Note: more specific (deeper directory) rules take precedence."
            )
        else:
            lines.append("No workspace-specific rules active.")

        # Detect scope changes
        prev_set = set(self._previous_scope.workspace_agents)
        curr_set = set(current.workspace_agents)
        removed = prev_set - curr_set
        added = curr_set - prev_set

        if removed or added:
            lines.append("")
            lines.append("SCOPE CHANGE:")
            if removed:
                lines.append(
                    "The following workspace rules no longer apply: "
                    + ", ".join(sorted(removed))
                )
            if added:
                lines.append(
                    "Newly active workspace rules: "
                    + ", ".join(sorted(added))
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Platform context
    # ------------------------------------------------------------------

    @staticmethod
    def _fill_platform_context(template: str) -> str:
        """Replace ``{os_label}``, ``{home_dir}``, ``{username}`` placeholders."""
        system = platform.system()
        os_label = {"Darwin": "macOS", "Linux": "Linux", "Windows": "Windows"}.get(
            system, system
        )
        return (
            template.replace("{os_label}", os_label)
            .replace("{home_dir}", str(Path.home()))
            .replace("{username}", os.getenv("USER") or os.getenv("USERNAME", "unknown"))
        )
