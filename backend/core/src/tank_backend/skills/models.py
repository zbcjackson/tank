"""Data models for the skills system."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillMetadata:
    """Parsed YAML frontmatter from SKILL.md."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    allowed_tools: tuple[str, ...] = ()
    approval: str = "auto"  # "auto" | "always" | "first-time"
    tags: tuple[str, ...] = ()
    context: str = "inline"  # "inline" | "fork"
    when_to_use: str = ""  # Rich matching context with examples
    priority: int = 50  # 0-100, higher = shown first in catalog
    platforms: tuple[str, ...] = ()  # Empty = all platforms
    requires_commands: tuple[str, ...] = ()  # Binary dependencies
    requires_env: tuple[str, ...] = ()  # Environment variables
    min_tank_version: str = ""  # Minimum Tank backend version required


@dataclass(frozen=True)
class SkillDefinition:
    """A fully parsed and indexed skill."""

    metadata: SkillMetadata
    instructions: str  # Markdown body
    path: Path  # Directory containing SKILL.md
    content_hash: str  # SHA-256 of all files in skill directory
    reviewed: bool = False
    review_hash: str = ""  # Hash at time of last review
    installed_at: str = ""  # ISO timestamp of installation
    updated_at: str = ""  # ISO timestamp of last update
    source_url: str = ""  # Where it was installed from (git URL, clawhub slug)


@dataclass(frozen=True)
class ReviewResult:
    """Output of the security review pipeline."""

    passed: bool
    risk_level: str  # "low" | "medium" | "high" | "critical"
    findings: tuple[str, ...] = ()
    content_hash: str = ""


@dataclass(frozen=True)
class SkillCandidate:
    """A skill found by a remote source (for future use)."""

    name: str
    description: str
    source_type: str  # "git" | "clawhub" | "registry"
    identifier: str  # URL or registry ID
    tags: tuple[str, ...] = ()
    risk_preview: str = ""  # Quick risk assessment before full review
