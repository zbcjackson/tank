"""Tests for the skills system."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_skill_dir(tmp_path: Path) -> Path:
    """Create a minimal valid skill directory."""
    skill_dir = tmp_path / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: test-skill
        description: "A test skill"
        version: "1.0.0"
        allowed-tools: []
        approval: auto
        tags: [test]
        ---

        Do something with the provided arguments.
    """))
    return skill_dir


@pytest.fixture()
def tmp_skill_with_scripts(tmp_path: Path) -> Path:
    """Create a skill directory with a safe script."""
    skill_dir = tmp_path / "scripted-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: scripted-skill
        description: "A skill with scripts"
        version: "1.0.0"
        allowed-tools: []
        approval: auto
        tags: [test]
        ---

        Run the helper script.
    """))
    scripts = skill_dir / "scripts"
    scripts.mkdir()
    (scripts / "helper.py").write_text("print('hello')\n")
    return skill_dir


@pytest.fixture()
def tmp_dangerous_skill(tmp_path: Path) -> Path:
    """Create a skill with dangerous patterns in scripts."""
    skill_dir = tmp_path / "dangerous-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
        ---
        name: dangerous-skill
        description: "A dangerous skill"
        version: "1.0.0"
        allowed-tools: []
        ---

        Do something dangerous.
    """))
    scripts = skill_dir / "scripts"
    scripts.mkdir()
    (scripts / "bad.py").write_text(
        "import subprocess\n"
        "result = subprocess.run(['ls'])\n"
    )
    return skill_dir


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParser:
    def test_parse_valid_skill(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file

        skill = parse_skill_file(tmp_skill_dir)

        assert skill.metadata.name == "test-skill"
        assert skill.metadata.description == "A test skill"
        assert skill.metadata.version == "1.0.0"
        assert skill.metadata.allowed_tools == ()
        assert skill.metadata.approval == "auto"
        assert skill.metadata.tags == ("test",)
        assert "arguments" in skill.instructions
        assert skill.content_hash != ""
        assert skill.path == tmp_skill_dir

    def test_parse_missing_name(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file

        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: test\n---\nBody\n")

        with pytest.raises(ValueError, match="Missing required field 'name'"):
            parse_skill_file(skill_dir)

    def test_parse_missing_description(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file

        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: bad\n---\nBody\n")

        with pytest.raises(ValueError, match="Missing required field 'description'"):
            parse_skill_file(skill_dir)

    def test_parse_invalid_name(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file

        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: Bad_Skill!\ndescription: test\n---\nBody\n"
        )

        with pytest.raises(ValueError, match="Invalid skill name"):
            parse_skill_file(skill_dir)

    def test_parse_missing_frontmatter(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file

        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("Just some text without frontmatter\n")

        with pytest.raises(ValueError, match="missing YAML frontmatter"):
            parse_skill_file(skill_dir)

    def test_parse_missing_skill_md(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file

        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()

        with pytest.raises(ValueError, match="SKILL.md not found"):
            parse_skill_file(skill_dir)

    def test_content_hash_changes(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file

        skill1 = parse_skill_file(tmp_skill_dir)
        hash1 = skill1.content_hash

        skill_file = tmp_skill_dir / "SKILL.md"
        skill_file.write_text(skill_file.read_text() + "\nExtra line.\n")

        skill2 = parse_skill_file(tmp_skill_dir)
        assert skill2.content_hash != hash1

    def test_review_state_persisted(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.parser import compute_directory_hash, parse_skill_file

        content_hash = compute_directory_hash(tmp_skill_dir)
        (tmp_skill_dir / ".review").write_text(
            yaml.dump({"hash": content_hash, "passed": True})
        )

        skill = parse_skill_file(tmp_skill_dir)
        assert skill.reviewed is True
        assert skill.review_hash == content_hash

    def test_parse_allowed_tools(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file

        skill_dir = tmp_path / "tools-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
            ---
            name: tools-skill
            description: "A skill with allowed tools"
            allowed-tools:
              - web_search
              - web_scraper
            ---

            Search the web.
        """))

        skill = parse_skill_file(skill_dir)
        assert skill.metadata.allowed_tools == ("web_search", "web_scraper")

    def test_parse_backward_compat_tools_field(self, tmp_path: Path) -> None:
        """Old 'tools:' field should still work for backward compat."""
        from tank_backend.skills.parser import parse_skill_file

        skill_dir = tmp_path / "compat-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(textwrap.dedent("""\
            ---
            name: compat-skill
            description: "Uses old tools field"
            tools:
              - web_search
            ---

            Search.
        """))

        skill = parse_skill_file(skill_dir)
        assert skill.metadata.allowed_tools == ("web_search",)


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_scan_discovers_skills(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.registry import SkillRegistry

        registry = SkillRegistry([tmp_skill_dir.parent])
        registry.scan()

        assert len(registry.list_all()) == 1
        assert registry.get("test-skill") is not None

    def test_scan_skips_invalid(self, tmp_path: Path) -> None:
        from tank_backend.skills.registry import SkillRegistry

        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "SKILL.md").write_text("---\nname: bad\n---\nBody\n")

        registry = SkillRegistry([tmp_path])
        registry.scan()

        assert len(registry.list_all()) == 0

    def test_deduplication_first_wins(self, tmp_path: Path) -> None:
        from tank_backend.skills.registry import SkillRegistry

        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        for d, desc in [(dir1, "first"), (dir2, "second")]:
            skill_dir = d / "my-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: my-skill\ndescription: {desc}\n---\nBody\n"
            )

        registry = SkillRegistry([dir1, dir2])
        registry.scan()

        skill = registry.get("my-skill")
        assert skill is not None
        assert skill.metadata.description == "first"

    def test_register_and_unregister(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file
        from tank_backend.skills.registry import SkillRegistry

        registry = SkillRegistry([])
        skill = parse_skill_file(tmp_skill_dir)

        registry.register(skill)
        assert registry.get("test-skill") is not None

        assert registry.unregister("test-skill") is True
        assert registry.get("test-skill") is None
        assert registry.unregister("test-skill") is False

    def test_scan_nonexistent_dir(self, tmp_path: Path) -> None:
        from tank_backend.skills.registry import SkillRegistry

        registry = SkillRegistry([tmp_path / "does-not-exist"])
        registry.scan()
        assert len(registry.list_all()) == 0


# ---------------------------------------------------------------------------
# Reviewer tests
# ---------------------------------------------------------------------------

class TestReviewer:
    def test_prompt_only_low_risk(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file
        from tank_backend.skills.reviewer import SecurityReviewer

        skill = parse_skill_file(tmp_skill_dir)
        result = SecurityReviewer().review(skill)

        assert result.passed is True
        assert result.risk_level == "low"
        assert len(result.findings) == 0

    def test_safe_scripts_medium_risk(self, tmp_skill_with_scripts: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file
        from tank_backend.skills.reviewer import SecurityReviewer

        skill = parse_skill_file(tmp_skill_with_scripts)
        result = SecurityReviewer().review(skill)

        assert result.passed is True
        assert result.risk_level == "medium"

    def test_dangerous_patterns_critical(self, tmp_dangerous_skill: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file
        from tank_backend.skills.reviewer import SecurityReviewer

        skill = parse_skill_file(tmp_dangerous_skill)
        result = SecurityReviewer().review(skill)

        assert result.passed is False
        assert result.risk_level == "critical"
        assert any("subprocess" in f for f in result.findings)

    def test_unexpected_file_type(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file
        from tank_backend.skills.reviewer import SecurityReviewer

        skill_dir = tmp_path / "weird-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: weird-skill\ndescription: test\n---\nBody\n"
        )
        scripts = skill_dir / "scripts"
        scripts.mkdir()
        (scripts / "data.exe").write_text("binary stuff")

        skill = parse_skill_file(skill_dir)
        result = SecurityReviewer().review(skill)

        assert any("Unexpected file type" in f for f in result.findings)

    def test_network_tools_medium_risk(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file
        from tank_backend.skills.reviewer import SecurityReviewer

        skill_dir = tmp_path / "net-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: net-skill\ndescription: test\n"
            "allowed-tools:\n  - web_search\n---\nBody\n"
        )

        skill = parse_skill_file(skill_dir)
        result = SecurityReviewer().review(skill)

        assert result.risk_level == "medium"

    def test_high_risk_tools(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file
        from tank_backend.skills.reviewer import SecurityReviewer

        skill_dir = tmp_path / "risky-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: risky-skill\ndescription: test\n"
            "allowed-tools:\n  - run_command\n---\nBody\n"
        )

        skill = parse_skill_file(skill_dir)
        result = SecurityReviewer().review(skill)

        assert result.risk_level == "high"

    def test_undeclared_tool_finding(self, tmp_path: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file
        from tank_backend.skills.reviewer import SecurityReviewer

        skill_dir = tmp_path / "scope-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: scope-skill\ndescription: test\n"
            "allowed-tools: []\n---\n"
            "Use web_search to find results.\n"
        )

        skill = parse_skill_file(skill_dir)
        result = SecurityReviewer().review(skill)

        assert any("web_search" in f and "not declared" in f for f in result.findings)

    def test_content_hash_in_result(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.parser import parse_skill_file
        from tank_backend.skills.reviewer import SecurityReviewer

        skill = parse_skill_file(tmp_skill_dir)
        result = SecurityReviewer().review(skill)

        assert result.content_hash == skill.content_hash


# ---------------------------------------------------------------------------
# Manager tests
# ---------------------------------------------------------------------------

class TestManager:
    @pytest.fixture()
    def manager(self, tmp_skill_dir: Path) -> Any:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        registry = SkillRegistry([tmp_skill_dir.parent])
        registry.scan()

        reviewer = SecurityReviewer()
        mgr = SkillManager(registry, reviewer)
        mgr.startup()  # auto-review
        return mgr

    @pytest.mark.asyncio()
    async def test_invoke_reviewed_skill(self, manager: Any) -> None:
        result = await manager.invoke("test-skill", "hello")

        assert "instructions" in result
        assert "hello" in result["instructions"]
        assert result["allowed_tools"] == []

    @pytest.mark.asyncio()
    async def test_invoke_with_empty_args(self, manager: Any) -> None:
        result = await manager.invoke("test-skill")

        assert "instructions" in result
        assert "Arguments:" not in result["instructions"]

    @pytest.mark.asyncio()
    async def test_invoke_unreviewed_rejects(self, tmp_path: Path) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        skill_dir = tmp_path / "unreviewed"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: unreviewed\ndescription: test\n---\nBody\n"
        )

        registry = SkillRegistry([tmp_path])
        registry.scan()
        # Don't call startup() — skill stays unreviewed
        mgr = SkillManager(registry, SecurityReviewer())

        result = await mgr.invoke("unreviewed")
        assert "error" in result
        assert "not passed security review" in result["error"]

    @pytest.mark.asyncio()
    async def test_invoke_not_found(self, manager: Any) -> None:
        result = await manager.invoke("nonexistent")
        assert "error" in result

    @pytest.mark.asyncio()
    async def test_create_skill(self, tmp_path: Path) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        registry = SkillRegistry([skills_dir])
        mgr = SkillManager(registry, SecurityReviewer())

        result = await mgr.create(
            name="new-skill",
            description="A brand new skill",
            instructions="Do something cool.",
            allowed_tools=[],
        )

        assert result["skill_name"] == "new-skill"
        assert result["review_passed"] is True
        assert (skills_dir / "new-skill" / "SKILL.md").exists()
        assert registry.get("new-skill") is not None

    @pytest.mark.asyncio()
    async def test_invoke_tampered_skill(self, tmp_skill_dir: Path) -> None:
        """Skill modified after review should be rejected."""
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.parser import compute_directory_hash
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        content_hash = compute_directory_hash(tmp_skill_dir)
        (tmp_skill_dir / ".review").write_text(
            yaml.dump({"hash": content_hash, "passed": True})
        )

        registry = SkillRegistry([tmp_skill_dir.parent])
        registry.scan()

        # Tamper after review
        skill_file = tmp_skill_dir / "SKILL.md"
        skill_file.write_text(skill_file.read_text() + "\nInjected content!\n")
        registry.scan()

        mgr = SkillManager(registry, SecurityReviewer())
        result = await mgr.invoke("test-skill")

        assert "error" in result
        assert "not passed security review" in result["error"]

    def test_remove_skill(self, manager: Any) -> None:
        result = manager.remove("test-skill")
        assert "removed" in result["message"]

        result = manager.remove("nonexistent")
        assert "error" in result

    def test_startup_auto_reviews(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        registry = SkillRegistry([tmp_skill_dir.parent])
        registry.scan()

        skill = registry.get("test-skill")
        assert skill is not None
        assert skill.reviewed is False

        mgr = SkillManager(registry, SecurityReviewer())
        mgr.startup()

        skill = registry.get("test-skill")
        assert skill is not None
        assert skill.reviewed is True

    def test_get_skill_catalog_empty(self) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        mgr = SkillManager(SkillRegistry([]), SecurityReviewer())
        assert mgr.get_skill_catalog() == ""

    def test_get_skill_catalog_with_skills(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        registry = SkillRegistry([tmp_skill_dir.parent])
        registry.scan()

        mgr = SkillManager(registry, SecurityReviewer())
        mgr.startup()

        catalog = mgr.get_skill_catalog()
        assert "AVAILABLE SKILLS:" in catalog
        assert "test-skill" in catalog
        assert "A test skill" in catalog

    def test_get_skill_catalog_budget(self, tmp_path: Path) -> None:
        """Catalog should respect budget constraint."""
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer

        # Create many skills
        for i in range(20):
            skill_dir = tmp_path / f"skill-{i:02d}"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: skill-{i:02d}\n"
                f"description: Skill number {i} with a long description\n---\nBody\n"
            )

        registry = SkillRegistry([tmp_path])
        registry.scan()

        mgr = SkillManager(registry, SecurityReviewer())
        mgr.startup()

        # Very small budget
        catalog = mgr.get_skill_catalog(budget_chars=300)
        assert "..." in catalog  # Should have truncation indicator


# ---------------------------------------------------------------------------
# Tool wrapper tests
# ---------------------------------------------------------------------------

class TestSkillTools:
    def test_use_skill_tool_get_info(self) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer
        from tank_backend.tools.skill_tools import UseSkillTool

        mgr = SkillManager(SkillRegistry([]), SecurityReviewer())
        tool = UseSkillTool(mgr)

        info = tool.get_info()
        assert info.name == "use_skill"
        assert len(info.parameters) == 2
        assert info.parameters[0].name == "skill"
        assert info.parameters[1].name == "args"

    @pytest.mark.asyncio()
    async def test_use_skill_tool_execute(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer
        from tank_backend.tools.skill_tools import UseSkillTool

        registry = SkillRegistry([tmp_skill_dir.parent])
        registry.scan()
        mgr = SkillManager(registry, SecurityReviewer())
        mgr.startup()

        tool = UseSkillTool(mgr)
        result = await tool.execute(skill="test-skill", args="hello")

        assert result["status"] == "inline"
        assert result["skill_name"] == "test-skill"
        assert "SKILL ACTIVATED" in result["message"]
        assert "hello" in result["message"]
        assert "BEGIN SKILL INSTRUCTIONS" in result["message"]

    def test_list_skills_tool_get_info(self) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer
        from tank_backend.tools.skill_tools import ListSkillsTool

        mgr = SkillManager(SkillRegistry([]), SecurityReviewer())
        tool = ListSkillsTool(mgr)

        info = tool.get_info()
        assert info.name == "list_skills"

    def test_create_skill_tool_get_info(self) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer
        from tank_backend.tools.skill_tools import CreateSkillTool

        mgr = SkillManager(SkillRegistry([]), SecurityReviewer())
        tool = CreateSkillTool(mgr)

        info = tool.get_info()
        assert info.name == "create_skill"
        assert len(info.parameters) >= 3

    @pytest.mark.asyncio()
    async def test_list_skills_empty(self) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer
        from tank_backend.tools.skill_tools import ListSkillsTool

        mgr = SkillManager(SkillRegistry([]), SecurityReviewer())
        tool = ListSkillsTool(mgr)

        result = await tool.execute()
        assert result["skills"] == []

    @pytest.mark.asyncio()
    async def test_list_skills_with_skills(self, tmp_skill_dir: Path) -> None:
        from tank_backend.skills.manager import SkillManager
        from tank_backend.skills.registry import SkillRegistry
        from tank_backend.skills.reviewer import SecurityReviewer
        from tank_backend.tools.skill_tools import ListSkillsTool

        registry = SkillRegistry([tmp_skill_dir.parent])
        registry.scan()
        mgr = SkillManager(registry, SecurityReviewer())
        tool = ListSkillsTool(mgr)

        result = await tool.execute()
        assert len(result["skills"]) == 1
        assert result["skills"][0]["name"] == "test-skill"


# ---------------------------------------------------------------------------
# SkillToolGroup tests
# ---------------------------------------------------------------------------

class TestSkillToolGroup:
    def test_disabled_returns_empty(self) -> None:
        from tank_backend.tools.groups import SkillToolGroup

        group = SkillToolGroup(config={"enabled": False})
        assert group.create_tools() == []

    def test_enabled_creates_four_tools(self, tmp_path: Path) -> None:
        from tank_backend.tools.groups import SkillToolGroup

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        group = SkillToolGroup(
            config={"enabled": True, "dirs": [str(skills_dir)]},
        )
        tools = group.create_tools()

        names = [t.get_info().name for t in tools]
        assert names == ["use_skill", "list_skills", "create_skill", "install_skill"]

    def test_auto_review_on_startup(self, tmp_skill_dir: Path) -> None:
        from tank_backend.tools.groups import SkillToolGroup

        # No .review file — skill is unreviewed
        assert not (tmp_skill_dir / ".review").exists()

        group = SkillToolGroup(
            config={
                "enabled": True,
                "dirs": [str(tmp_skill_dir.parent)],
                "auto_approve_threshold": "low",
            },
        )
        group.create_tools()

        # .review file should now exist from startup()
        assert (tmp_skill_dir / ".review").exists()

    def test_skill_catalog_after_startup(self, tmp_skill_dir: Path) -> None:
        from tank_backend.tools.groups import SkillToolGroup

        group = SkillToolGroup(
            config={
                "enabled": True,
                "dirs": [str(tmp_skill_dir.parent)],
                "auto_approve_threshold": "low",
            },
        )
        group.create_tools()

        catalog = group.get_skill_catalog()
        assert "test-skill" in catalog
        assert "AVAILABLE SKILLS:" in catalog

    def test_medium_risk_not_auto_approved_at_low_threshold(
        self, tmp_skill_with_scripts: Path,
    ) -> None:
        from tank_backend.tools.groups import SkillToolGroup

        group = SkillToolGroup(
            config={
                "enabled": True,
                "dirs": [str(tmp_skill_with_scripts.parent)],
                "auto_approve_threshold": "low",
            },
        )
        group.create_tools()

        catalog = group.get_skill_catalog()
        assert "scripted-skill" not in catalog

    def test_dangerous_skill_never_auto_approved(
        self, tmp_dangerous_skill: Path,
    ) -> None:
        from tank_backend.tools.groups import SkillToolGroup

        group = SkillToolGroup(
            config={
                "enabled": True,
                "dirs": [str(tmp_dangerous_skill.parent)],
                "auto_approve_threshold": "high",
            },
        )
        group.create_tools()

        catalog = group.get_skill_catalog()
        assert "dangerous-skill" not in catalog
