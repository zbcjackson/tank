"""SkillSource ABC — pluggable interface for fetching skills from various sources.

Each source knows how to fetch skill directories to a local path.
The SkillManager uses sources to resolve URLs/paths before installing.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil
import tempfile
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from .models import SkillCandidate

logger = logging.getLogger(__name__)

CLAWHUB_BASE_URL = "https://clawhub.ai"
CLAWHUB_PREFIX = "clawhub:"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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


class ClawHubSource(SkillSource):
    """Fetches skills from the clawhub.ai registry via its REST API."""

    def matches(self, identifier: str) -> bool:
        return identifier.startswith(CLAWHUB_PREFIX)

    async def fetch(self, identifier: str) -> Path:
        """Download a skill zip from clawhub.ai and extract it.

        Raises ``RuntimeError`` on API errors or malware-blocked skills.
        The caller is responsible for cleaning up the parent temp directory.
        """
        slug = identifier.removeprefix(CLAWHUB_PREFIX).strip()
        if not _SLUG_RE.match(slug):
            raise RuntimeError(f"Invalid ClawHub slug: {slug!r}")

        async with httpx.AsyncClient(
            base_url=CLAWHUB_BASE_URL, timeout=30.0,
        ) as client:
            # Verify skill exists and check moderation
            resp = await client.get(f"/api/v1/skills/{slug}")
            if resp.status_code == 404:
                raise RuntimeError(f"Skill '{slug}' not found on clawhub.ai")
            resp.raise_for_status()

            data = resp.json()
            moderation = data.get("moderation") or {}
            if moderation.get("isMalwareBlocked"):
                raise RuntimeError(
                    f"Skill '{slug}' is blocked by clawhub.ai moderation "
                    f"(verdict: {moderation.get('verdict', 'unknown')})"
                )

            # Download the zip
            dl_resp = await client.get(
                "/api/v1/download", params={"slug": slug},
            )
            if dl_resp.status_code == 404:
                raise RuntimeError(f"Download not available for '{slug}'")
            dl_resp.raise_for_status()

        # Extract to temp directory
        tmp_dir = Path(tempfile.mkdtemp(prefix="tank_skill_clawhub_"))
        skill_dir = tmp_dir / "skill"

        try:
            with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as zf:
                zf.extractall(skill_dir)
        except zipfile.BadZipFile as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RuntimeError(f"Invalid zip from clawhub.ai for '{slug}': {e}") from e

        # If the zip contains a single top-level directory, descend into it
        children = [c for c in skill_dir.iterdir() if not c.name.startswith(".")]
        if len(children) == 1 and children[0].is_dir():
            skill_dir = children[0]

        logger.info("Downloaded skill '%s' from clawhub.ai to %s", slug, skill_dir)
        return skill_dir

    @staticmethod
    async def search(query: str, limit: int = 10) -> list[SkillCandidate]:
        """Search clawhub.ai for skills matching *query*."""
        async with httpx.AsyncClient(
            base_url=CLAWHUB_BASE_URL, timeout=15.0,
        ) as client:
            resp = await client.get(
                "/api/v1/search", params={"q": query, "limit": limit},
            )
            resp.raise_for_status()

        candidates: list[SkillCandidate] = []
        for item in resp.json().get("results", []):
            candidates.append(SkillCandidate(
                name=item.get("displayName", item.get("slug", "")),
                description=item.get("summary", ""),
                source_type="clawhub",
                identifier=f"{CLAWHUB_PREFIX}{item['slug']}",
                tags=(),
                risk_preview="",
            ))
        return candidates


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
