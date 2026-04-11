"""SkillSource ABC — pluggable interface for fetching skills from various sources.

Each source knows how to fetch skill directories to a local path.
The SkillManager uses sources to resolve URLs/paths before installing.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillSource(ABC):
    """A backend that can fetch skills to a local directory."""

    @abstractmethod
    async def fetch(self, identifier: str) -> Path:
        """Fetch skill(s) to a local directory and return the root path.

        The returned path may contain a single SKILL.md at root,
        or multiple subdirectories each containing SKILL.md.
        """
        ...

    @abstractmethod
    def matches(self, identifier: str) -> bool:
        """Return True if this source can handle the given identifier."""
        ...


class LocalSource(SkillSource):
    """Handles local filesystem paths."""

    def matches(self, identifier: str) -> bool:
        return not identifier.startswith(("https://", "http://", "git@"))

    async def fetch(self, identifier: str) -> Path:
        return Path(identifier).resolve()


class GitSource(SkillSource):
    """Clones a git repository to a temporary directory."""

    def matches(self, identifier: str) -> bool:
        return identifier.startswith(("https://", "http://", "git@"))

    async def fetch(self, identifier: str) -> Path:
        """Clone the repo and return the repo root path.

        Raises ``RuntimeError`` if git clone fails.
        The caller is responsible for cleaning up the parent temp directory.
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="tank_skill_"))
        repo_dir = tmp_dir / "repo"

        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", identifier, str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RuntimeError(f"git clone failed: {stderr.decode().strip()}")

        return repo_dir


def find_skill_dirs(root: Path) -> list[Path]:
    """Find all directories containing SKILL.md under *root*.

    Handles three layouts:
    - Single skill at root: root/SKILL.md
    - Multiple skills in subdirs: root/skill-a/SKILL.md, root/skill-b/SKILL.md
    - Nested one level: root/skills/skill-a/SKILL.md (common in monorepos)
    """
    results: list[Path] = []

    if (root / "SKILL.md").exists():
        results.append(root)
        return results

    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / "SKILL.md").exists():
            results.append(child)
        else:
            for grandchild in sorted(child.iterdir()):
                if grandchild.is_dir() and (grandchild / "SKILL.md").exists():
                    results.append(grandchild)

    return results
