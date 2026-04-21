"""SkillManager — orchestrates skill invoke, create, install, and remove."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .models import ReviewResult, SkillDefinition
from .parser import parse_skill_file
from .registry import SkillRegistry
from .reviewer import SecurityReviewer

logger = logging.getLogger(__name__)

# Default budget: 2% of max_history_tokens (in chars, ~4 chars/token).
DEFAULT_CATALOG_BUDGET_PERCENT = 2
DEFAULT_CATALOG_BUDGET_MAX_CHARS = 12000
MAX_DESCRIPTION_CHARS = 250


class SkillManager:
    """High-level orchestrator for the skills system."""

    def __init__(
        self,
        registry: SkillRegistry,
        reviewer: SecurityReviewer,
        bus: Any = None,
        auto_approve_threshold: str = "low",
        catalog_budget_percent: int = DEFAULT_CATALOG_BUDGET_PERCENT,
        catalog_budget_max_chars: int = DEFAULT_CATALOG_BUDGET_MAX_CHARS,
        max_history_tokens: int = 8000,
    ) -> None:
        self._registry = registry
        self._reviewer = reviewer
        self._bus = bus
        self._auto_approve_threshold = auto_approve_threshold
        # Effective budget: min(percent-based, hard ceiling)
        percent_chars = int(max_history_tokens * 4 * catalog_budget_percent / 100)
        self._catalog_budget = min(percent_chars, catalog_budget_max_chars)

    @property
    def registry(self) -> SkillRegistry:
        return self._registry

    # ------------------------------------------------------------------
    # Startup — auto-review unreviewed skills
    # ------------------------------------------------------------------

    def startup(self) -> None:
        """Auto-review unreviewed skills on startup."""
        risk_levels = ("low", "medium", "high")
        if self._auto_approve_threshold in risk_levels:
            threshold_idx = risk_levels.index(self._auto_approve_threshold)
        else:
            threshold_idx = 0

        for skill in list(self._registry.list_all()):
            if skill.reviewed and skill.content_hash == skill.review_hash:
                continue

            result = self._reviewer.review(skill)
            if not result.passed:
                logger.warning(
                    "Skill '%s' failed security review (risk: %s): %s",
                    skill.metadata.name, result.risk_level,
                    "; ".join(result.findings),
                )
                continue

            if result.risk_level in risk_levels:
                skill_idx = risk_levels.index(result.risk_level)
            else:
                skill_idx = 99

            if skill_idx <= threshold_idx:
                self._persist_review(skill.path, result)
                skill = parse_skill_file(skill.path)
                self._registry.register(skill)
                logger.info(
                    "Skill '%s' auto-approved (risk: %s)",
                    skill.metadata.name, result.risk_level,
                )
            else:
                logger.warning(
                    "Skill '%s' needs manual approval (risk: %s > threshold: %s)",
                    skill.metadata.name, result.risk_level,
                    self._auto_approve_threshold,
                )

    # ------------------------------------------------------------------
    # Explicit review — re-review a single skill by name
    # ------------------------------------------------------------------

    def review(self, name: str) -> dict[str, Any]:
        """Re-review a skill and persist the result if it passes.

        Use this when a skill was edited in place and its content hash
        no longer matches the review hash.

        Returns a dict with review outcome (passed, risk_level, findings).
        """
        skill = self._registry.get(name)
        if skill is None:
            return {"error": f"Skill '{name}' not found"}

        # Re-parse from disk to pick up any file changes
        try:
            skill = parse_skill_file(skill.path)
        except ValueError as exc:
            return {"error": f"Failed to parse skill '{name}': {exc}"}

        result = self._reviewer.review(skill)

        if result.passed:
            self._persist_review(skill.path, result)
            skill = parse_skill_file(skill.path)
            self._registry.register(skill)
            self._post_bus_event("reviewed", name)
            return {
                "skill_name": name,
                "passed": True,
                "risk_level": result.risk_level,
                "findings": list(result.findings),
                "message": (
                    f"Skill '{name}' passed security review "
                    f"(risk: {result.risk_level})."
                ),
            }

        return {
            "skill_name": name,
            "passed": False,
            "risk_level": result.risk_level,
            "findings": list(result.findings),
            "error": (
                f"Skill '{name}' failed security review "
                f"(risk: {result.risk_level})"
            ),
            "message": (
                f"Skill '{name}' failed security review "
                f"(risk: {result.risk_level}): "
                + "; ".join(result.findings)
            ),
        }

    # ------------------------------------------------------------------
    # Hot reload — rescan disk, re-review, return diff
    # ------------------------------------------------------------------

    def reload(self) -> dict[str, list[str]]:
        """Rescan skill directories and re-review new/changed skills.

        Returns a dict with ``added``, ``removed``, and ``updated`` skill
        name lists so callers know what changed.
        """
        old_names = {s.metadata.name for s in self._registry.list_all()}
        old_hashes = {
            s.metadata.name: s.content_hash
            for s in self._registry.list_all()
        }

        self._registry.scan()
        self.startup()

        new_names = {s.metadata.name for s in self._registry.list_all()}
        new_hashes = {
            s.metadata.name: s.content_hash
            for s in self._registry.list_all()
        }

        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)
        updated = sorted(
            name for name in (old_names & new_names)
            if old_hashes.get(name) != new_hashes.get(name)
        )

        total = len(added) + len(removed) + len(updated)
        logger.info(
            "Skill reload complete: %d added, %d removed, %d updated",
            len(added), len(removed), len(updated),
        )

        if total > 0:
            self._post_bus_event("reloaded", f"+{len(added)}-{len(removed)}~{len(updated)}")

        return {"added": added, "removed": removed, "updated": updated}

    # ------------------------------------------------------------------
    # Skill catalog for system-reminder injection
    # ------------------------------------------------------------------

    def get_skill_catalog(self) -> str:
        """Return a compact skill catalog for system prompt injection.

        Returns an empty string if no reviewed skills are available.
        Uses tiered truncation to fit within the configured budget:
        Tier 1: name + description + when_to_use (full)
        Tier 2: name + description only (compact)
        Tier 3: name only
        Tier 4: truncate list with "... and N more"

        Skills are sorted by priority (descending), then name.
        """
        skills = [
            s for s in self._registry.list_all()
            if s.reviewed and s.content_hash == s.review_hash
        ]
        if not skills:
            return ""

        # Sort by priority descending, then name ascending
        skills.sort(key=lambda s: (-s.metadata.priority, s.metadata.name))

        budget = self._catalog_budget

        # Try Tier 1: full entries
        result = self._format_catalog(skills, budget, tier=1)
        if result is not None:
            return result

        # Try Tier 2: compact (no when_to_use)
        result = self._format_catalog(skills, budget, tier=2)
        if result is not None:
            return result

        # Tier 3: names only
        result = self._format_catalog(skills, budget, tier=3)
        if result is not None:
            return result

        # Shouldn't happen, but return empty if budget is impossibly small
        return ""

    def _format_catalog(
        self,
        skills: list[SkillDefinition],
        budget: int,
        tier: int,
    ) -> str | None:
        """Format skill catalog at a given tier. Returns None if it doesn't fit."""
        header = (
            "AVAILABLE SKILLS:\n"
            "Before responding, scan the skills below. If a skill matches the "
            "user's request, call use_skill with the skill name. Prefer skills "
            "over handling requests yourself.\n"
        )
        used = len(header)
        entries: list[str] = []

        for skill in skills:
            entry = self._format_skill_entry(skill, tier)
            entry_cost = len(entry) + 1  # +1 for newline

            if used + entry_cost > budget:
                remaining = len(skills) - len(entries)
                if remaining > 0:
                    entries.append(f"... and {remaining} more skills")
                break

            entries.append(entry)
            used += entry_cost

        if not entries:
            return None

        return header + "\n".join(entries)

    @staticmethod
    def _format_skill_entry(skill: SkillDefinition, tier: int) -> str:
        """Format a single skill entry at the given tier level."""
        meta = skill.metadata
        version_tag = f" (v{meta.version})" if meta.version != "1.0.0" else ""

        if tier == 3:
            return f"- {meta.name}{version_tag}"

        desc = meta.description
        if len(desc) > MAX_DESCRIPTION_CHARS:
            desc = desc[: MAX_DESCRIPTION_CHARS - 3] + "..."

        entry = f"- {meta.name}{version_tag}: {desc}"

        if tier == 1 and meta.when_to_use:
            when = meta.when_to_use.replace("\n", " ").strip()
            entry += f" — {when}"
        elif tier <= 2 and meta.tags:
            entry += f" [tags: {', '.join(meta.tags)}]"

        return entry

    # ------------------------------------------------------------------
    # Invoke
    # ------------------------------------------------------------------

    async def invoke(self, name: str, args: str = "") -> dict[str, Any]:
        """Load a skill's instructions and metadata for execution.

        Returns a dict with ``instructions``, ``allowed_tools``, and
        ``context`` (inline or fork) for the tool wrapper to execute.
        """
        skill = self._registry.get(name)
        if skill is None:
            return {
                "error": f"Skill '{name}' not found",
                "message": f"Skill '{name}' not found.",
            }

        if not skill.reviewed:
            return {
                "error": f"Skill '{name}' has not passed security review",
                "message": (
                    f"Skill '{name}' is not reviewed. "
                    "Use the review_skill tool to run security review."
                ),
            }

        if skill.content_hash != skill.review_hash:
            return {
                "error": f"Skill '{name}' content changed since last review",
                "message": (
                    f"Skill '{name}' was modified after review. "
                    "Use the review_skill tool to re-review it."
                ),
            }

        instructions = skill.instructions
        if args:
            instructions = f"Arguments: {args}\n\n{instructions}"

        self._post_bus_event("invoked", name)

        return {
            "skill_name": name,
            "instructions": instructions,
            "allowed_tools": list(skill.metadata.allowed_tools),
            "context": skill.metadata.context,
        }

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        name: str,
        description: str,
        instructions: str,
        allowed_tools: list[str] | None = None,
        target_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Create a new skill, write SKILL.md, review, and register."""
        if target_dir is None:
            dirs = self._registry._skill_dirs
            if not dirs:
                return {"error": "No skill directories configured"}
            target_dir = dirs[0]

        skill_dir = target_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        frontmatter: dict[str, Any] = {
            "name": name,
            "description": description,
            "version": "1.0.0",
            "allowed-tools": allowed_tools or [],
            "approval": "auto",
            "tags": [],
        }

        skill_md = f"---\n{yaml.dump(frontmatter, default_flow_style=False).strip()}\n---\n\n"
        skill_md += instructions + "\n"

        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

        try:
            skill = parse_skill_file(skill_dir)
        except ValueError as e:
            return {"error": str(e), "message": f"Failed to create skill: {e}"}

        result = self._reviewer.review(skill)
        self._persist_review(skill_dir, result, source_url="")

        skill = parse_skill_file(skill_dir)
        self._registry.register(skill)

        self._post_bus_event("created", name)

        return {
            "skill_name": name,
            "path": str(skill_dir),
            "review_passed": result.passed,
            "risk_level": result.risk_level,
            "message": (
                f"Skill '{name}' created at {skill_dir}. "
                f"Review: {'passed' if result.passed else 'FAILED'} "
                f"(risk: {result.risk_level})."
            ),
        }

    # ------------------------------------------------------------------
    # Install — from git URL or local path
    # ------------------------------------------------------------------

    async def install(
        self, source: str, skill_name: str | None = None,
    ) -> dict[str, Any]:
        """Install skill(s) from a git URL, clawhub slug, or local path.

        If the source contains multiple skills and *skill_name* is given,
        only that skill is installed.  If *skill_name* is ``None``, all
        skills found are installed.
        """
        import shutil

        from .source import ClawHubSource, GitSource, LocalSource, find_skill_dirs

        sources = [GitSource(), ClawHubSource(), LocalSource()]
        matched = next((s for s in sources if s.matches(source)), None)
        if matched is None:
            return {"error": f"No source handler for: {source}"}

        is_remote = not isinstance(matched, LocalSource)
        try:
            root = await matched.fetch(source)
        except RuntimeError as e:
            return {"error": str(e), "message": str(e)}

        try:
            skill_dirs = find_skill_dirs(root)
            if not skill_dirs:
                return {
                    "error": "No SKILL.md found",
                    "message": f"No skills found at {source}.",
                }

            # Filter to a specific skill if requested
            if skill_name:
                skill_dirs = [
                    d for d in skill_dirs
                    if d.name == skill_name
                    or (d / "SKILL.md").exists()
                    and self._skill_name_matches(d, skill_name)
                ]
                if not skill_dirs:
                    available = [d.name for d in find_skill_dirs(root)]
                    return {
                        "error": f"Skill '{skill_name}' not found",
                        "message": (
                            f"Skill '{skill_name}' not found in {source}. "
                            f"Available: {', '.join(available)}"
                        ),
                    }

            # For remote sources, copy to local skill dir first
            dirs = self._registry._skill_dirs
            if not dirs:
                return {"error": "No skill directories configured"}
            target_base = dirs[0]
            target_base.mkdir(parents=True, exist_ok=True)

            results: list[dict[str, Any]] = []
            for skill_dir in skill_dirs:
                if is_remote:
                    try:
                        skill = parse_skill_file(skill_dir)
                    except ValueError as e:
                        results.append({"error": str(e)})
                        continue
                    dest = target_base / skill.metadata.name
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(skill_dir, dest)
                    r = await self.install_from_path(dest, source_url=source)
                else:
                    r = await self.install_from_path(skill_dir, source_url=source)
                results.append(r)

            if len(results) == 1:
                return results[0]

            installed = [r["skill_name"] for r in results if "skill_name" in r]
            failed = [r.get("error", "unknown") for r in results if "error" in r]
            msg_parts = []
            if installed:
                msg_parts.append(f"Installed: {', '.join(installed)}")
            if failed:
                msg_parts.append(f"Failed: {'; '.join(failed)}")

            return {
                "installed": installed,
                "failed": failed,
                "message": ". ".join(msg_parts) + ".",
            }

        finally:
            if is_remote:
                # Clean up the temp clone directory
                shutil.rmtree(root.parent, ignore_errors=True)

    @staticmethod
    def _skill_name_matches(skill_dir: Path, name: str) -> bool:
        """Check if a skill directory's SKILL.md has the given name."""
        try:
            skill = parse_skill_file(skill_dir)
            return skill.metadata.name == name
        except ValueError:
            return False

    async def install_from_path(
        self,
        source_path: Path,
        target_dir: Path | None = None,
        source_url: str = "",
    ) -> dict[str, Any]:
        """Install a skill from a local directory."""
        try:
            skill = parse_skill_file(source_path)
        except ValueError as e:
            return {"error": str(e), "message": f"Invalid skill: {e}"}

        result = self._reviewer.review(skill)

        if not result.passed:
            return {
                "error": "Security review failed",
                "risk_level": result.risk_level,
                "findings": list(result.findings),
                "message": (
                    f"Skill '{skill.metadata.name}' failed security review "
                    f"(risk: {result.risk_level}). Findings: "
                    + "; ".join(result.findings)
                ),
            }

        self._persist_review(source_path, result, source_url=source_url)

        skill = parse_skill_file(source_path)
        self._registry.register(skill)

        self._post_bus_event("installed", skill.metadata.name)

        return {
            "skill_name": skill.metadata.name,
            "path": str(source_path),
            "risk_level": result.risk_level,
            "message": f"Skill '{skill.metadata.name}' installed successfully.",
        }

    # ------------------------------------------------------------------
    # Remove
    # ------------------------------------------------------------------

    def remove(self, name: str) -> dict[str, Any]:
        """Unregister a skill (does not delete files)."""
        if self._registry.unregister(name):
            self._post_bus_event("removed", name)
            return {"message": f"Skill '{name}' removed from registry."}
        return {"error": f"Skill '{name}' not found", "message": f"Skill '{name}' not found."}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _persist_review(
        self,
        skill_dir: Path,
        result: ReviewResult,
        source_url: str = "",
    ) -> None:
        """Write .review file to persist review state and version tracking."""
        now = datetime.now(timezone.utc).isoformat()

        # Preserve existing timestamps if updating
        review_file = skill_dir / ".review"
        installed_at = now
        if review_file.exists():
            try:
                existing = yaml.safe_load(review_file.read_text(encoding="utf-8")) or {}
                installed_at = existing.get("installed_at", now)
            except Exception:
                pass

        review_data = {
            "hash": result.content_hash,
            "risk_level": result.risk_level,
            "passed": result.passed,
            "findings": list(result.findings),
            "version": "",  # Filled after re-parse
            "installed_at": installed_at,
            "updated_at": now,
            "source_url": source_url,
        }

        # Read version from the skill metadata
        try:
            skill = parse_skill_file(skill_dir)
            review_data["version"] = skill.metadata.version
        except ValueError:
            pass

        review_file.write_text(
            yaml.dump(review_data, default_flow_style=False),
            encoding="utf-8",
        )

    def _post_bus_event(self, event: str, skill_name: str) -> None:
        """Post a skill lifecycle event to the Bus."""
        if self._bus is None:
            return
        import time

        from ..pipeline.bus import BusMessage

        self._bus.post(BusMessage(
            type="skill",
            source="skill_manager",
            payload={"event": event, "skill_name": skill_name},
            timestamp=time.time(),
        ))
