"""Tests for skill system enhancements: priority, when_to_use, conditional skills, versioning."""

from __future__ import annotations

import platform
import shutil
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def skill_with_when_to_use(tmp_path: Path) -> Path:
    """Create a skill with when_to_use field."""
    skill_dir = tmp_path / "commit-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
        ---
        name: commit-skill
        description: Create a git commit
        when_to_use: |
          Use when the user wants to commit changes.
          Examples: "commit this", "make a commit", "git commit"
        priority: 80
        ---

        Create a git commit with the provided message.
    """)
    )
    return skill_dir


@pytest.fixture()
def skill_with_aliases(tmp_path: Path) -> Path:
    """Create a skill using alias fields (triggers, examples)."""
    skill_dir = tmp_path / "alias-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
        ---
        name: alias-skill
        description: Test alias fields
        triggers: Use when testing aliases
        examples:
          - "test this"
          - "try that"
        ---

        Body content.
    """)
    )
    return skill_dir


@pytest.fixture()
def skill_with_platform_filter(tmp_path: Path) -> Path:
    """Create a skill that only works on macOS."""
    skill_dir = tmp_path / "macos-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
        ---
        name: macos-skill
        description: macOS-only skill
        platforms: [macos]
        ---

        macOS-specific functionality.
    """)
    )
    return skill_dir


@pytest.fixture()
def skill_with_requires(tmp_path: Path) -> Path:
    """Create a skill with binary and env requirements."""
    skill_dir = tmp_path / "docker-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
        ---
        name: docker-skill
        description: Docker debugging skill
        requires:
          commands: [docker, docker-compose]
          env: [DOCKER_HOST]
        ---

        Debug Docker containers.
    """)
    )
    return skill_dir


@pytest.fixture()
def high_priority_skill(tmp_path: Path) -> Path:
    """Create a high-priority skill."""
    skill_dir = tmp_path / "high-priority"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
        ---
        name: high-priority
        description: High priority skill
        priority: 90
        ---

        Important skill.
    """)
    )
    return skill_dir


@pytest.fixture()
def low_priority_skill(tmp_path: Path) -> Path:
    """Create a low-priority skill."""
    skill_dir = tmp_path / "low-priority"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
        ---
        name: low-priority
        description: Low priority skill
        priority: 10
        ---

        Less important skill.
    """)
    )
    return skill_dir


# ---------------------------------------------------------------------------
# Parser tests for new fields
# ---------------------------------------------------------------------------


class TestParserEnhancements:
    def test_parse_when_to_use(self, skill_with_when_to_use: Path) -> None:
        """Parser should extract when_to_use field."""
        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(skill_with_when_to_use)
        assert "commit changes" in skill.metadata.when_to_use
        assert "Examples:" in skill.metadata.when_to_use

    def test_parse_when_to_use_alias_triggers(self, skill_with_aliases: Path) -> None:
        """Parser should use 'triggers' as alias for when_to_use."""
        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(skill_with_aliases)
        assert "testing aliases" in skill.metadata.when_to_use

    def test_parse_synthesize_from_examples(self, tmp_path: Path) -> None:
        """Parser should synthesize when_to_use from examples field."""
        skill_dir = tmp_path / "examples-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: examples-skill
            description: Test examples synthesis
            examples:
              - "do this"
              - "do that"
            ---

            Body.
        """)
        )

        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(skill_dir)
        assert "Examples:" in skill.metadata.when_to_use
        assert "do this" in skill.metadata.when_to_use

    def test_parse_synthesize_from_tags(self, tmp_path: Path) -> None:
        """Parser should synthesize when_to_use from tags if nothing else available."""
        skill_dir = tmp_path / "tags-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: tags-skill
            description: Test tags synthesis
            tags: [git, commit, version-control]
            ---

            Body.
        """)
        )

        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(skill_dir)
        assert "Related to:" in skill.metadata.when_to_use
        assert "git" in skill.metadata.when_to_use

    def test_parse_priority(self, high_priority_skill: Path) -> None:
        """Parser should extract priority field."""
        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(high_priority_skill)
        assert skill.metadata.priority == 90

    def test_parse_priority_default(self, tmp_path: Path) -> None:
        """Parser should default priority to 50."""
        skill_dir = tmp_path / "no-priority"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: no-priority
            description: No priority specified
            ---

            Body.
        """)
        )

        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(skill_dir)
        assert skill.metadata.priority == 50

    def test_parse_priority_clamped(self, tmp_path: Path) -> None:
        """Parser should clamp priority to 0-100 range."""
        skill_dir = tmp_path / "invalid-priority"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: invalid-priority
            description: Invalid priority
            priority: 150
            ---

            Body.
        """)
        )

        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(skill_dir)
        assert skill.metadata.priority == 100

    def test_parse_platforms(self, skill_with_platform_filter: Path) -> None:
        """Parser should extract platforms field."""
        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(skill_with_platform_filter)
        assert skill.metadata.platforms == ("macos",)

    def test_parse_requires(self, skill_with_requires: Path) -> None:
        """Parser should extract requires.commands and requires.env."""
        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(skill_with_requires)
        assert "docker" in skill.metadata.requires_commands
        assert "docker-compose" in skill.metadata.requires_commands
        assert "DOCKER_HOST" in skill.metadata.requires_env

    def test_parse_version_tracking_from_review(self, tmp_path: Path) -> None:
        """Parser should extract version tracking from .review file."""
        skill_dir = tmp_path / "versioned-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: versioned-skill
            description: Test version tracking
            version: "2.0.0"
            ---

            Body.
        """)
        )

        import yaml

        from tank_backend.skills.parser import compute_directory_hash

        content_hash = compute_directory_hash(skill_dir)
        (skill_dir / ".review").write_text(
            yaml.dump(
                {
                    "hash": content_hash,
                    "passed": True,
                    "risk_level": "low",
                    "findings": [],
                    "version": "2.0.0",
                    "installed_at": "2026-04-17T10:00:00Z",
                    "updated_at": "2026-04-17T12:00:00Z",
                    "source_url": "clawhub:test-skill",
                }
            )
        )

        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(skill_dir)
        assert skill.installed_at == "2026-04-17T10:00:00Z"
        assert skill.updated_at == "2026-04-17T12:00:00Z"
        assert skill.source_url == "clawhub:test-skill"


# ---------------------------------------------------------------------------
# Registry eligibility filtering tests
# ---------------------------------------------------------------------------


class TestRegistryEligibility:
    def test_platform_filter_excludes_wrong_platform(
        self, skill_with_platform_filter: Path
    ) -> None:
        """Registry should exclude skills for wrong platform."""
        from tank_backend.skills.registry import SkillRegistry

        registry = SkillRegistry([skill_with_platform_filter.parent])
        registry.scan()

        current_platform = platform.system().lower()
        platform_map = {"darwin": "macos", "linux": "linux", "windows": "windows"}
        current = platform_map.get(current_platform, current_platform)

        if current == "macos":
            # Should be included on macOS
            assert registry.get("macos-skill") is not None
        else:
            # Should be excluded on other platforms
            assert registry.get("macos-skill") is None

    def test_missing_binary_excludes_skill(self, tmp_path: Path) -> None:
        """Registry should exclude skills with missing binary dependencies."""
        from tank_backend.skills.registry import SkillRegistry

        skill_dir = tmp_path / "needs-fake-bin"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: needs-fake-bin
            description: Requires a nonexistent binary
            requires:
              commands: [__nonexistent_binary_xyz__]
            ---

            Body.
        """)
        )

        registry = SkillRegistry([tmp_path])
        registry.scan()
        assert registry.get("needs-fake-bin") is None

    def test_missing_env_var_excludes_skill(self, tmp_path: Path, monkeypatch) -> None:
        """Registry should exclude skills with missing env vars."""
        skill_dir = tmp_path / "env-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: env-skill
            description: Requires env var
            requires:
              env: [TEST_REQUIRED_VAR]
            ---

            Body.
        """)
        )

        from tank_backend.skills.registry import SkillRegistry

        # Without env var
        monkeypatch.delenv("TEST_REQUIRED_VAR", raising=False)
        registry = SkillRegistry([tmp_path])
        registry.scan()
        assert registry.get("env-skill") is None

        # With env var
        monkeypatch.setenv("TEST_REQUIRED_VAR", "present")
        registry2 = SkillRegistry([tmp_path])
        registry2.scan()
        assert registry2.get("env-skill") is not None


# ---------------------------------------------------------------------------
# Catalog priority and budget tests
# ---------------------------------------------------------------------------


class TestCatalogEnhancements:
    def test_catalog_sorts_by_priority(
        self, tmp_path: Path, high_priority_skill: Path, low_priority_skill: Path
    ) -> None:
        """Catalog should list high-priority skills first."""
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        # Copy both skills to same directory
        dest_dir = tmp_path / "skills"
        dest_dir.mkdir()
        shutil.copytree(high_priority_skill, dest_dir / "high-priority")
        shutil.copytree(low_priority_skill, dest_dir / "low-priority")

        registry = SkillRegistry([dest_dir])
        registry.scan()

        mgr = SkillManager(registry, SecurityReviewer())
        mgr.startup()

        catalog = mgr.get_skill_catalog()
        high_pos = catalog.find("high-priority")
        low_pos = catalog.find("low-priority")

        assert high_pos < low_pos, "High priority skill should appear first"

    def test_catalog_includes_when_to_use(self, skill_with_when_to_use: Path) -> None:
        """Catalog should include when_to_use in full tier."""
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        registry = SkillRegistry([skill_with_when_to_use.parent])
        registry.scan()

        mgr = SkillManager(registry, SecurityReviewer())
        mgr.startup()

        catalog = mgr.get_skill_catalog()
        assert "commit changes" in catalog
        assert "Examples:" in catalog

    def test_catalog_tiered_truncation(self, tmp_path: Path) -> None:
        """Catalog should degrade gracefully: full → compact → names → truncate."""
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        # Create 10 skills with when_to_use
        for i in range(10):
            skill_dir = tmp_path / f"skill-{i:02d}"
            skill_dir.mkdir()
            when = f"Use when doing task {i}"
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                f"name: skill-{i:02d}\n"
                f"description: Skill number {i} with a description\n"
                f"when_to_use: {when}\n"
                f"priority: {90 - i * 5}\n"
                "---\n\n"
                f"Body {i}.\n"
            )

        registry = SkillRegistry([tmp_path])
        registry.scan()

        # Very small budget forces tier 3 (names only)
        mgr = SkillManager(
            registry,
            SecurityReviewer(),
            catalog_budget_max_chars=400,
            catalog_budget_percent=100,
        )
        mgr.startup()

        catalog = mgr.get_skill_catalog()

        # Should have truncation indicator
        assert "..." in catalog
        # Should have at least some skill names
        assert "skill-00" in catalog

    def test_catalog_version_not_displayed(self, tmp_path: Path) -> None:
        """Catalog should NOT show version tags — they confuse LLM skill lookup."""
        skill_dir = tmp_path / "versioned"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: versioned
            description: Versioned skill
            version: "2.5.0"
            ---

            Body.
        """)
        )

        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        registry = SkillRegistry([tmp_path])
        registry.scan()

        mgr = SkillManager(registry, SecurityReviewer())
        mgr.startup()

        catalog = mgr.get_skill_catalog()
        assert "versioned" in catalog
        assert "(v2.5.0)" not in catalog

    def test_catalog_percentage_budget(self, tmp_path: Path) -> None:
        """Catalog budget should scale with max_history_tokens."""
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        # Create one skill
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: test-skill
            description: Test
            ---

            Body.
        """)
        )

        registry = SkillRegistry([tmp_path])
        registry.scan()

        # Small context window: 2% of 1000 tokens * 4 chars/token = 80 chars
        mgr_small = SkillManager(
            registry,
            SecurityReviewer(),
            catalog_budget_percent=2,
            catalog_budget_max_chars=12000,
            max_history_tokens=1000,
        )
        assert mgr_small._catalog_budget == 80

        # Large context window: 2% of 100000 tokens * 4 = 8000, capped at 12000
        mgr_large = SkillManager(
            registry,
            SecurityReviewer(),
            catalog_budget_percent=2,
            catalog_budget_max_chars=12000,
            max_history_tokens=100000,
        )
        assert mgr_large._catalog_budget == 8000


# ---------------------------------------------------------------------------
# Version tracking tests
# ---------------------------------------------------------------------------


class TestVersionTracking:
    async def test_install_records_timestamps(self, tmp_path: Path) -> None:
        """Installing a skill should record installed_at and updated_at."""
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        skill_dir = tmp_path / "new-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: new-skill
            description: New skill
            ---

            Body.
        """)
        )

        registry = SkillRegistry([tmp_path])
        mgr = SkillManager(registry, SecurityReviewer())

        result = await mgr.install_from_path(skill_dir, source_url="test://source")

        assert result.get("skill_name") == "new-skill"

        # Check .review file
        import yaml

        review_data = yaml.safe_load((skill_dir / ".review").read_text())
        assert "installed_at" in review_data
        assert "updated_at" in review_data
        assert review_data["source_url"] == "test://source"
        assert review_data["version"] == "1.0.0"

    async def test_update_preserves_installed_at(self, tmp_path: Path) -> None:
        """Updating a skill should preserve installed_at but update updated_at."""
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.parser import compute_directory_hash
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        skill_dir = tmp_path / "update-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: update-skill
            description: Original
            ---

            Body.
        """)
        )

        # First install
        import yaml

        content_hash = compute_directory_hash(skill_dir)
        (skill_dir / ".review").write_text(
            yaml.dump(
                {
                    "hash": content_hash,
                    "passed": True,
                    "risk_level": "low",
                    "findings": [],
                    "version": "1.0.0",
                    "installed_at": "2026-04-17T10:00:00Z",
                    "updated_at": "2026-04-17T10:00:00Z",
                    "source_url": "test://source",
                }
            )
        )

        # Modify skill
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent("""\
            ---
            name: update-skill
            description: Updated
            ---

            New body.
        """)
        )

        registry = SkillRegistry([tmp_path])
        mgr = SkillManager(registry, SecurityReviewer())

        await mgr.install_from_path(skill_dir, source_url="test://source")

        # Check .review file
        review_data = yaml.safe_load((skill_dir / ".review").read_text())
        assert review_data["installed_at"] == "2026-04-17T10:00:00Z"  # Preserved
        assert review_data["updated_at"] != "2026-04-17T10:00:00Z"  # Changed
