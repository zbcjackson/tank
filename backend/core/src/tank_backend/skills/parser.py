"""Parse SKILL.md files into SkillDefinition objects."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from .models import SkillDefinition, SkillMetadata

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$|^[a-z0-9]$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)


def _parse_string_tuple(value: Any) -> tuple[str, ...]:
    """Parse a field that can be a list of strings or a comma-separated string."""
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    if isinstance(value, str):
        return tuple(v.strip() for v in value.split(",") if v.strip())
    return ()


def _parse_when_to_use(frontmatter: dict[str, Any], tags: tuple[str, ...]) -> str:
    """Parse when_to_use with alias support and synthesis from other fields."""
    # Try direct field with aliases
    when_to_use = (
        frontmatter.get("when_to_use")
        or frontmatter.get("when-to-use")
        or frontmatter.get("triggers")
        or frontmatter.get("use_when")
        or ""
    )

    if when_to_use:
        if isinstance(when_to_use, list):
            return ". ".join(str(item) for item in when_to_use)
        return str(when_to_use)

    # Synthesize from available metadata
    parts = []

    # Mine from examples field
    examples = frontmatter.get("examples")
    if isinstance(examples, list) and examples:
        examples_str = ", ".join(f'"{e}"' for e in examples[:3])
        parts.append(f"Examples: {examples_str}")
    elif isinstance(examples, str) and examples:
        parts.append(f"Examples: {examples}")

    # Mine from tags if no other info available
    if not parts and tags:
        parts.append(f"Related to: {', '.join(tags[:5])}")

    return ". ".join(parts)


def compute_directory_hash(directory: Path) -> str:
    """SHA-256 hash of all file contents in a directory, sorted by path."""
    h = hashlib.sha256()
    for file_path in sorted(directory.rglob("*")):
        if file_path.is_file() and file_path.name != ".review":
            h.update(str(file_path.relative_to(directory)).encode())
            h.update(file_path.read_bytes())
    return h.hexdigest()


def parse_skill_file(skill_dir: Path) -> SkillDefinition:
    """Parse a SKILL.md file and return a SkillDefinition.

    Raises ``ValueError`` if the file is missing or malformed.
    """
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        raise ValueError(f"SKILL.md not found in {skill_dir}")

    text = skill_file.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"Invalid SKILL.md format in {skill_dir}: missing YAML frontmatter")

    raw_yaml, body = match.group(1), match.group(2).strip()

    try:
        frontmatter: dict[str, Any] = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {skill_file}: {e}") from e

    # --- Validate required fields ---
    name = frontmatter.get("name")
    if not name:
        raise ValueError(f"Missing required field 'name' in {skill_file}")
    if not _NAME_RE.match(name):
        raise ValueError(
            f"Invalid skill name '{name}': must be lowercase alphanumeric + hyphens, "
            f"1-64 chars"
        )

    description = frontmatter.get("description")
    if not description:
        raise ValueError(f"Missing required field 'description' in {skill_file}")

    # --- Build metadata ---
    # Accept both "allowed-tools" and "allowed_tools" from frontmatter
    raw_tools = (
        frontmatter.get("allowed-tools")
        or frontmatter.get("allowed_tools")
        or frontmatter.get("tools")  # backward compat
        or []
    )
    if isinstance(raw_tools, list):
        allowed_tools = tuple(raw_tools)
    elif isinstance(raw_tools, str):
        # Handle comma-separated string: "Bash(foo), Bash(bar)"
        allowed_tools = tuple(t.strip() for t in raw_tools.split(",") if t.strip())
    else:
        allowed_tools = ()

    raw_tags = frontmatter.get("tags", [])
    tags = tuple(raw_tags) if isinstance(raw_tags, list) else ()

    approval = frontmatter.get("approval", "auto")
    if approval not in ("auto", "always", "first-time"):
        logger.warning("Unknown approval value '%s' in %s, defaulting to 'auto'", approval, name)
        approval = "auto"

    context = frontmatter.get("context", "inline")
    if context not in ("inline", "fork"):
        logger.warning("Unknown context value '%s' in %s, defaulting to 'inline'", context, name)
        context = "inline"

    # --- when_to_use: alias mapping + synthesis ---
    when_to_use = _parse_when_to_use(frontmatter, tags)

    # --- priority ---
    raw_priority = frontmatter.get("priority", 50)
    priority = max(0, min(100, int(raw_priority))) if isinstance(raw_priority, (int, float)) else 50

    # --- conditional fields ---
    platforms = _parse_string_tuple(frontmatter.get("platforms"))

    requires = frontmatter.get("requires", {})
    if not isinstance(requires, dict):
        requires = {}
    requires_commands = _parse_string_tuple(
        requires.get("commands") or frontmatter.get("requires_commands")
    )
    requires_env = _parse_string_tuple(
        requires.get("env") or frontmatter.get("requires_env")
    )

    min_tank_version = str(frontmatter.get("min_tank_version", ""))

    metadata = SkillMetadata(
        name=name,
        description=description,
        version=frontmatter.get("version", "1.0.0"),
        author=frontmatter.get("author", ""),
        allowed_tools=allowed_tools,
        approval=approval,
        tags=tags,
        context=context,
        when_to_use=when_to_use,
        priority=priority,
        platforms=platforms,
        requires_commands=requires_commands,
        requires_env=requires_env,
        min_tank_version=min_tank_version,
    )

    content_hash = compute_directory_hash(skill_dir)

    # --- Check for persisted review state ---
    review_file = skill_dir / ".review"
    reviewed = False
    review_hash = ""
    installed_at = ""
    updated_at = ""
    source_url = ""
    if review_file.exists():
        try:
            review_data = yaml.safe_load(review_file.read_text(encoding="utf-8")) or {}
            review_hash = review_data.get("hash", "")
            reviewed = review_hash == content_hash
            installed_at = review_data.get("installed_at", "")
            updated_at = review_data.get("updated_at", "")
            source_url = review_data.get("source_url", "")
        except Exception:
            logger.warning("Failed to read .review file in %s", skill_dir)

    return SkillDefinition(
        metadata=metadata,
        instructions=body,
        path=skill_dir,
        content_hash=content_hash,
        reviewed=reviewed,
        review_hash=review_hash,
        installed_at=installed_at,
        updated_at=updated_at,
        source_url=source_url,
    )
