"""SkillRegistry — discover, index, and deduplicate skills from disk."""

from __future__ import annotations

import logging
import os
import platform
import shutil
from pathlib import Path

from .models import SkillDefinition
from .parser import parse_skill_file

logger = logging.getLogger(__name__)

_PLATFORM_MAP = {"darwin": "macos", "linux": "linux", "windows": "windows"}


class SkillRegistry:
    """In-memory index of all discovered skills.

    Skills are scanned from multiple directories in priority order.
    The first directory to provide a skill name wins (project > user).
    Ineligible skills (wrong platform, missing dependencies) are excluded.
    """

    def __init__(self, skill_dirs: list[Path] | None = None) -> None:
        self._skills: dict[str, SkillDefinition] = {}
        self._skill_dirs = skill_dirs or []

    def scan(self) -> None:
        """Discover skills from configured directories."""
        self._skills.clear()
        for skill_dir in self._skill_dirs:
            if not skill_dir.exists():
                logger.debug("Skill directory does not exist, skipping: %s", skill_dir)
                continue
            self._scan_directory(skill_dir)
        logger.info("SkillRegistry: %d skills discovered", len(self._skills))

    def _scan_directory(self, base_dir: Path) -> None:
        """Scan a single directory for skill subdirectories containing SKILL.md."""
        for child in sorted(base_dir.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                skill = parse_skill_file(child)
                if skill.metadata.name in self._skills:
                    logger.debug(
                        "Skill '%s' already registered (higher priority), skipping %s",
                        skill.metadata.name, child,
                    )
                    continue
                if not self._is_eligible(skill):
                    continue
                self._skills[skill.metadata.name] = skill
                logger.info("Discovered skill: %s (%s)", skill.metadata.name, child)
            except ValueError as e:
                logger.warning("Skipping invalid skill in %s: %s", child, e)

    @staticmethod
    def _is_eligible(skill: SkillDefinition) -> bool:
        """Check if a skill is eligible for the current environment."""
        meta = skill.metadata

        # Platform check
        if meta.platforms:
            current = _PLATFORM_MAP.get(platform.system().lower(), platform.system().lower())
            if current not in meta.platforms:
                logger.debug(
                    "Skill '%s' skipped: platform '%s' not in %s",
                    meta.name, current, meta.platforms,
                )
                return False

        # Binary dependency check
        for cmd in meta.requires_commands:
            if shutil.which(cmd) is None:
                logger.debug(
                    "Skill '%s' skipped: required command '%s' not found",
                    meta.name, cmd,
                )
                return False

        # Environment variable check
        for var in meta.requires_env:
            if not os.environ.get(var):
                logger.debug(
                    "Skill '%s' skipped: required env var '%s' not set",
                    meta.name, var,
                )
                return False

        return True

    def get(self, name: str) -> SkillDefinition | None:
        """Get a skill by name, or None if not found."""
        return self._skills.get(name)

    def list_all(self) -> list[SkillDefinition]:
        """Return all registered skills, sorted by name."""
        return sorted(self._skills.values(), key=lambda s: s.metadata.name)

    def register(self, skill: SkillDefinition) -> None:
        """Add or replace a skill in the registry."""
        self._skills[skill.metadata.name] = skill

    def unregister(self, name: str) -> bool:
        """Remove a skill from the registry. Returns True if it existed."""
        return self._skills.pop(name, None) is not None
