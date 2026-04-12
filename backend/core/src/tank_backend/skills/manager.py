"""SkillManager — orchestrates skill invoke, create, install, and remove."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .models import ReviewResult
from .parser import parse_skill_file
from .registry import SkillRegistry
from .reviewer import SecurityReviewer

logger = logging.getLogger(__name__)

# Budget for skill catalog: 1% of context window in chars.
DEFAULT_CATALOG_BUDGET_CHARS = 8000
MAX_DESCRIPTION_CHARS = 250


class SkillManager:
    """High-level orchestrator for the skills system."""

    def __init__(
        self,
        registry: SkillRegistry,
        reviewer: SecurityReviewer,
        bus: Any = None,
        auto_approve_threshold: str = "low",
    ) -> None:
        self._registry = registry
        self._reviewer = reviewer
        self._bus = bus
        self._auto_approve_threshold = auto_approve_threshold

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
    # Skill catalog for system-reminder injection
    # ------------------------------------------------------------------

    def get_skill_catalog(
        self, budget_chars: int = DEFAULT_CATALOG_BUDGET_CHARS,
    ) -> str:
        """Return a compact skill catalog for per-turn system-reminder injection.

        Returns an empty string if no reviewed skills are available.
        Budget-constrained: truncates descriptions to fit within *budget_chars*.
        """
        skills = [
            s for s in self._registry.list_all()
            if s.reviewed and s.content_hash == s.review_hash
        ]
        if not skills:
            return ""

        lines = [
            "AVAILABLE SKILLS:",
            "When a user's request matches a skill, call the use_skill tool "
            "with the skill name. Prefer skills over handling requests yourself.",
            "",
        ]
        used = sum(len(line) for line in lines)

        for skill in skills:
            desc = skill.metadata.description
            if len(desc) > MAX_DESCRIPTION_CHARS:
                desc = desc[: MAX_DESCRIPTION_CHARS - 3] + "..."
            entry = f"- {skill.metadata.name}: {desc}"
            if skill.metadata.tags:
                entry += f" [tags: {', '.join(skill.metadata.tags)}]"

            if used + len(entry) + 1 > budget_chars:
                lines.append(f"... and {len(skills) - len(lines) + 3} more skills")
                break
            lines.append(entry)
            used += len(entry) + 1

        return "\n".join(lines)

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
                    "Run security review before using it."
                ),
            }

        if skill.content_hash != skill.review_hash:
            return {
                "error": f"Skill '{name}' content changed since last review",
                "message": (
                    f"Skill '{name}' was modified after review. "
                    "It must be re-reviewed before use."
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
        self._persist_review(skill_dir, result)

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
                    r = await self.install_from_path(dest)
                else:
                    r = await self.install_from_path(skill_dir)
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

        self._persist_review(source_path, result)

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

    def _persist_review(self, skill_dir: Path, result: ReviewResult) -> None:
        """Write .review file to persist review state."""
        review_data = {
            "hash": result.content_hash,
            "risk_level": result.risk_level,
            "passed": result.passed,
            "findings": list(result.findings),
        }
        (skill_dir / ".review").write_text(
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
