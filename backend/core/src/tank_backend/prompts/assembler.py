"""PromptAssembler — compiles the final system prompt from multiple sources.

Assembly order (joined with ``SECTION_SEPARATOR`` into the final prompt):

1. [BASE]             Security boundaries + platform context (always from defaults)
2. [IDENTITY]         SOUL.md  (user's ~/.tank/SOUL.md or default)
3. [GLOBAL RULES]     AGENTS.md (user's ~/.tank/AGENTS.md or default)
4. [SKILLS]           Available skill catalog from SkillManager
5. [WORKSPACE RULES]  Discovered AGENTS.md chain (root → leaf)
6. [SCOPE]            Auto-generated active-paths / scope-change notes
7. [VOLATILE]         USER.md + memory facts + per-user preferences
                       (filled in by :class:`ContextManager` per turn)

Tiering for prompt-prefix caching:

* **stable**   — sections 1–4. Change only when a default file, SOUL.md,
  global AGENTS.md, or the skill catalog is edited.
* **context**  — sections 5–6. Change when the active workspace shifts
  (a new ``AGENTS.md`` is discovered or an old one falls out of scope).
* **volatile** — section 7. Rebuilt every turn from per-user data
  (memory recall, preferences, USER.md).

Callers that want one concatenated string still call :meth:`assemble`;
callers that want the tiers exposed (for cache breakpoints, debugging,
or per-tier rebuild logic) call :meth:`assemble_tiered`.

Priority: more-specific (deeper) workspace rules take precedence over
general ones.  base.md security boundaries are non-negotiable and
cannot be overridden.
"""

from __future__ import annotations

import logging
import os
import platform
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import FileCache
from .resolver import AgentsFileResolver
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
class TieredPrompt:
    """Three-tier breakdown of the system prompt for caching purposes.

    Each tier is a prebuilt string (or empty when no content applies).
    :meth:`joined` reassembles the full prompt using ``SECTION_SEPARATOR``.

    Attributes:
        stable: BASE + IDENTITY + GLOBAL RULES + SKILLS.  Changes rarely;
            ideal for prompt-prefix caching.
        context: WORKSPACE RULES + SCOPE.  Changes when the active
            workspace shifts.
        volatile: USER.md + memory facts + USER PREFERENCES.  Rebuilt
            every turn by :class:`ContextManager`.  The assembler leaves
            this empty by default — it has no per-user state.
    """

    stable: str
    context: str
    volatile: str = ""

    def joined(self, sep: str = SECTION_SEPARATOR) -> str:
        """Concatenate the non-empty tiers with ``sep``."""
        parts = [p for p in (self.stable, self.context, self.volatile) if p]
        return sep.join(parts)


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

    Create one instance per session.  Call :meth:`assemble` for a single
    string or :meth:`assemble_tiered` for the stable/context/volatile
    breakdown.  The assembler subscribes to the Bus internally (via
    :class:`AgentsFileResolver`) so workspace ``AGENTS.md`` files are
    discovered lazily when tools access paths.
    """

    def __init__(
        self,
        bus: Any = None,
        config: AssemblerConfig | None = None,
        skill_provider: Callable[[], str] | None = None,
    ) -> None:
        self._config = config or AssemblerConfig()
        self._cache = FileCache()
        self._resolver = AgentsFileResolver(bus=bus)
        self._skill_provider = skill_provider
        self._previous_scope = PromptScope()
        self._needs_rebuild = True
        self._cached_prompt: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def resolver(self) -> AgentsFileResolver:
        """Access the underlying resolver (e.g. for manual ``resolve_chain``)."""
        return self._resolver

    def needs_rebuild(self) -> bool:
        """True when the prompt should be reassembled before the next LLM call."""
        return self._needs_rebuild or self._resolver.has_new_discovery

    def assemble(self) -> str:
        """Assemble the full system prompt as a single string.

        Equivalent to ``self.assemble_tiered().joined()``.  Kept for
        callers that don't need the tier breakdown (e.g. sub-agent
        prompt building in :class:`AgentRunner`).
        """
        return self.assemble_tiered().joined()

    def assemble_tiered(self) -> TieredPrompt:
        """Assemble the prompt and return it split into stable/context/volatile.

        ``volatile`` is always empty here — :class:`ContextManager` fills
        it per-turn with USER.md, recalled facts, and preferences.
        """
        stable_parts: list[str] = []

        # 1. BASE — always from defaults, never user-overridden.
        base = self._load_default("base.md")
        if base:
            stable_parts.append(self._fill_platform_context(base))

        # 2. IDENTITY — SOUL.md
        soul = self._load_user_or_default("SOUL.md")
        if soul:
            stable_parts.append(soul)

        # 3. GLOBAL RULES — AGENTS.md (USER.md moved to volatile tier).
        global_agents = self._load_user_or_default("AGENTS.md")
        if global_agents:
            stable_parts.append(global_agents)

        # 4. SKILLS — available skill catalog
        skills_section = self._build_skills_section()
        if skills_section:
            stable_parts.append(skills_section)

        # 5. WORKSPACE RULES — discovered AGENTS.md chain
        context_parts: list[str] = []
        workspace_section = self._build_workspace_section()
        if workspace_section:
            context_parts.append(workspace_section)

        # 6. SCOPE — active paths and change notes
        current_scope = PromptScope(
            workspace_agents=tuple(sorted(self._resolver.all_discovered)),
        )
        scope_section = self._build_scope_section(current_scope)
        if scope_section:
            context_parts.append(scope_section)

        self._previous_scope = current_scope
        self._resolver.reset_discovery_flag()
        self._needs_rebuild = False

        tiered = TieredPrompt(
            stable=SECTION_SEPARATOR.join(stable_parts),
            context=SECTION_SEPARATOR.join(context_parts),
        )
        self._cached_prompt = tiered.joined()

        logger.info(
            "System prompt assembled "
            "(stable=%d chars, context=%d chars, workspace_agents=%s)",
            len(tiered.stable),
            len(tiered.context),
            list(current_scope.workspace_agents) or "none",
        )
        return tiered

    def load_user_md(self) -> str:
        """Return the sanitized USER.md content for the volatile tier.

        Goes through the same user-or-default chain + block-mode sanitize
        used during full assembly.  Returns an empty string when no
        USER.md exists in either location.
        """
        return self._load_user_or_default("USER.md") or ""

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
            sanitized = sanitize(content, source_path=agents_path, block=True)
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
        """Load from ``~/.tank/`` if it exists, otherwise from defaults.

        User-editable content is hard-blocked when an injection pattern
        matches; defaults run with the warn-only path.
        """
        user_path = Path(self._config.user_dir) / filename
        content = self._cache.read(user_path)
        if content is not None:
            logger.debug("Loaded user file: %s", user_path)
            return sanitize(content, source_path=str(user_path), block=True)

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
            sanitized = sanitize(content, source_path=agents_path, block=True)
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

    def _build_skills_section(self) -> str:
        """Build the skills catalog section from the skill provider."""
        if self._skill_provider is None:
            return ""
        catalog = self._skill_provider()
        if not catalog:
            return ""
        return catalog

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
