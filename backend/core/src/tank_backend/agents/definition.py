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
class AgentDefinition:
    """A named agent type with its system prompt and tool constraints."""

    name: str
    description: str
    system_prompt: str
    disallowed_tools: frozenset[str] = frozenset()
    skills: tuple[str, ...] = ()
    background: bool = False
    max_turns: int = 25
    model: str | None = None


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

    return AgentDefinition(
        name=name,
        description=description,
        system_prompt=body,
        disallowed_tools=disallowed,
        skills=skills,
        background=bool(fm.get("background", False)),
        max_turns=int(fm.get("max-turns", fm.get("max_turns", 25))),
        model=fm.get("model"),
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


def load_agents_from_config(config: dict[str, Any]) -> dict[str, AgentDefinition]:
    """Backward compat: convert config.yaml workers: section to AgentDefinitions."""
    workers = config.get("workers", {})
    definitions: dict[str, AgentDefinition] = {}

    for worker_name, worker_cfg in workers.items():
        description = worker_cfg.get("description", f"Agent: {worker_name}")
        system_prompt = worker_cfg.get(
            "system_prompt",
            f"You are a {worker_name} agent. Use the available tools to complete tasks. "
            f"Do NOT just describe what you would do — actually execute the commands.",
        )

        definitions[worker_name] = AgentDefinition(
            name=worker_name,
            description=description,
            system_prompt=system_prompt,
            max_turns=int(worker_cfg.get("timeout", 180) / 7),
        )

    return definitions
