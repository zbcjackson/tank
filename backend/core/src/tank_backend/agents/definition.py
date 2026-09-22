"""Agent definitions — configurable agent types loaded from markdown files."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


@dataclass(frozen=True)
class GroundingConfig:
    """Opt-in desktop experiment; split remains the default for existing configs."""

    profile: str | None = None
    fallback_profile: str | None = None
    protocol: str = "point"
    nullable_style: str = "integer"
    strict: bool = False
    detail: str = "auto"
    status_field: bool = True
    mode: str = "split"
    host_restore: bool = True

    def __post_init__(self) -> None:
        from ..tools.computer_grounding import GroundingAdapter

        if self.mode not in {"split", "integrated"} or type(self.host_restore) is not bool:
            raise ValueError("Invalid grounding mode/host_restore")
        if self.mode == "split" and (not self.host_restore or self.protocol == "legacy"):
            raise ValueError("Split grounding requires image restoration and an adapter")
        if self.mode == "integrated" and (
            self.profile is not None or self.fallback_profile is not None or self.strict
        ):
            raise ValueError("Integrated mode uses only the planner and non-strict tools")
        protocol = "point" if self.protocol == "legacy" else self.protocol
        GroundingAdapter(protocol, self.nullable_style, self.strict,
                         self.detail, self.status_field)
        for profile in (self.profile, self.fallback_profile):
            if profile is not None and (not isinstance(profile, str) or not profile.strip()):
                raise ValueError("grounding profiles must be nonempty names")


@dataclass(frozen=True)
class AgentDefinition:
    """A named agent type with its system prompt and tool constraints."""

    name: str
    description: str
    system_prompt: str
    disallowed_tools: frozenset[str] = frozenset()
    toolset: str = ""  # Named toolset profile (empty = all tools)
    tool_filter: tuple[str, ...] | None = None  # Inline allowlist; None = use toolset/all
    skills: tuple[str, ...] = ()
    background: bool = False
    token_budget: int = 0
    model: str | None = None
    # Plugin agent engine (B2): registry full name like "agent-n2:agent".
    # None = the built-in LLMAgent loop.
    engine: str | None = None
    extension: str | None = None
    grounding: GroundingConfig | None = None

    def __post_init__(self) -> None:
        if self.grounding is not None and (self.engine or self.extension):
            raise ValueError("grounding is only supported by the built-in agent")
        if self.engine and self.extension:
            raise ValueError("engine and extension cannot both be configured")
        if self.extension is not None and (
            not isinstance(self.extension, str)
            or not re.fullmatch(r"[^\s:]+:[^\s:]+", self.extension)
        ):
            raise ValueError("extension must be a plugin:extension reference")


def parse_agent_file(path: Path) -> AgentDefinition:
    """Parse an agent definition from a markdown file with YAML frontmatter.

    Raises ``ValueError`` if the file is malformed.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"Invalid agent file {path}: missing YAML frontmatter")

    raw_yaml, body = match.group(1), match.group(2).strip()

    try:
        fm: dict[str, Any] = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e

    name = fm.get("name")
    if not name:
        raise ValueError(f"Missing required field 'name' in {path}")

    description = fm.get("description", "")

    raw_disallowed = fm.get("disallowed-tools") or fm.get("disallowed_tools") or []
    if isinstance(raw_disallowed, str):
        disallowed = frozenset(t.strip() for t in raw_disallowed.split(",") if t.strip())
    elif isinstance(raw_disallowed, list):
        disallowed = frozenset(raw_disallowed)
    else:
        disallowed = frozenset()

    raw_skills = fm.get("skills") or []
    if isinstance(raw_skills, str):
        skills = tuple(s.strip() for s in raw_skills.split(",") if s.strip())
    elif isinstance(raw_skills, list):
        skills = tuple(raw_skills)
    else:
        skills = ()

    grounding = None
    if "grounding" in fm:
        if not isinstance(fm["grounding"], dict):
            raise ValueError("grounding must be a configuration mapping")
        try:
            grounding = GroundingConfig(**fm["grounding"])
        except TypeError as exc:
            raise ValueError(f"Invalid grounding configuration: {exc}") from exc

    return AgentDefinition(
        name=name,
        description=description,
        system_prompt=body,
        disallowed_tools=disallowed,
        toolset=fm.get("toolset", ""),
        skills=skills,
        background=bool(fm.get("background", False)),
        token_budget=int(fm.get("token-budget", fm.get("token_budget", 0))),
        model=fm.get("model"),
        engine=fm.get("engine"),
        extension=fm.get("extension"),
        grounding=grounding,
    )


def load_agent_definitions(dirs: list[Path]) -> dict[str, AgentDefinition]:
    """Load agent definitions from directories. First dir wins on name conflict."""
    definitions: dict[str, AgentDefinition] = {}
    for base_dir in dirs:
        if not base_dir.exists():
            continue
        for path in sorted(base_dir.glob("*.md")):
            try:
                defn = parse_agent_file(path)
                if defn.name in definitions:
                    logger.debug(
                        "Agent '%s' already loaded (higher priority), skipping %s",
                        defn.name, path,
                    )
                    continue
                definitions[defn.name] = defn
                logger.info("Loaded agent definition: %s (%s)", defn.name, path)
            except ValueError as e:
                logger.warning("Skipping invalid agent file %s: %s", path, e)
    return definitions
