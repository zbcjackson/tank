"""Tests for prompts.assembler — PromptAssembler."""

from pathlib import Path

import pytest

from tank_backend.prompts.assembler import AssemblerConfig, PromptAssembler, PromptScope
from tank_backend.prompts.resolver import AGENTS_FILENAME


class TestPromptAssembler:
    @pytest.fixture
    def defaults_dir(self, tmp_path):
        """Create a minimal defaults directory."""
        d = tmp_path / "defaults"
        d.mkdir()
        (d / "base.md").write_text(
            "SECURITY:\n- rule1\n\nENVIRONMENT:\n"
            "- OS: {os_label}\n- Home: {home_dir}\n- User: {username}",
            encoding="utf-8",
        )
        (d / "SOUL.md").write_text("You are TestBot.", encoding="utf-8")
        (d / "USER.md").write_text("USER PREFS:\n- lang: en", encoding="utf-8")
        (d / "AGENTS.md").write_text("TOOL USAGE:\n- use tools wisely", encoding="utf-8")
        return d

    @pytest.fixture
    def user_dir(self, tmp_path):
        """Create an empty user dir (no overrides by default)."""
        d = tmp_path / "user_tank"
        d.mkdir()
        return d

    @pytest.fixture
    def config(self, defaults_dir, user_dir):
        return AssemblerConfig(user_dir=str(user_dir), defaults_dir=str(defaults_dir))

    @pytest.fixture
    def assembler(self, config):
        return PromptAssembler(config=config)

    # ------------------------------------------------------------------
    # Basic assembly
    # ------------------------------------------------------------------

    def test_assembles_with_defaults_only(self, assembler):
        prompt = assembler.assemble()
        assert "SECURITY" in prompt
        assert "TestBot" in prompt
        assert "USER PREFS" in prompt
        assert "TOOL USAGE" in prompt

    def test_platform_placeholders_filled(self, assembler):
        prompt = assembler.assemble()
        assert "{os_label}" not in prompt
        assert "{home_dir}" not in prompt
        assert "{username}" not in prompt
        # Actual values present
        assert str(Path.home()) in prompt

    def test_user_files_override_defaults(self, assembler, config):
        user_dir = Path(config.user_dir)
        (user_dir / "SOUL.md").write_text("You are CustomBot.", encoding="utf-8")
        assembler.mark_dirty()
        prompt = assembler.assemble()
        assert "CustomBot" in prompt
        assert "TestBot" not in prompt

    def test_base_md_never_user_overridden(self, assembler, config):
        """base.md always comes from defaults, even if user dir has one."""
        user_dir = Path(config.user_dir)
        (user_dir / "base.md").write_text("HACKED BASE", encoding="utf-8")
        assembler.mark_dirty()
        prompt = assembler.assemble()
        assert "HACKED BASE" not in prompt
        assert "SECURITY" in prompt

    # ------------------------------------------------------------------
    # needs_rebuild
    # ------------------------------------------------------------------

    def test_needs_rebuild_true_initially(self, assembler):
        assert assembler.needs_rebuild()

    def test_needs_rebuild_false_after_assemble(self, assembler):
        assembler.assemble()
        assert not assembler.needs_rebuild()

    def test_needs_rebuild_true_after_mark_dirty(self, assembler):
        assembler.assemble()
        assembler.mark_dirty()
        assert assembler.needs_rebuild()

    def test_needs_rebuild_true_after_new_discovery(self, assembler, tmp_path):
        assembler.assemble()
        # Simulate a workspace AGENTS.md discovery
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / AGENTS_FILENAME).write_text("# workspace rules", encoding="utf-8")
        assembler.resolver.resolve_chain(str(workspace / "file.py"))
        assert assembler.needs_rebuild()

    # ------------------------------------------------------------------
    # Workspace rules
    # ------------------------------------------------------------------

    def test_workspace_agents_included(self, assembler, tmp_path):
        assembler.assemble()  # Initial assembly

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / AGENTS_FILENAME).write_text("WORKSPACE RULE: do X", encoding="utf-8")
        assembler.resolver.resolve_chain(str(workspace / "src" / "foo.py"))

        prompt = assembler.assemble()
        assert "WORKSPACE RULE: do X" in prompt
        assert "WORKSPACE RULES:" in prompt

    def test_multi_level_workspace_chain(self, assembler, tmp_path):
        assembler.assemble()

        root = tmp_path / "repo"
        root.mkdir()
        (root / AGENTS_FILENAME).write_text("ROOT RULE", encoding="utf-8")
        sub = root / "pkg"
        sub.mkdir()
        (sub / AGENTS_FILENAME).write_text("PKG RULE", encoding="utf-8")

        assembler.resolver.resolve_chain(str(sub / "main.py"))
        prompt = assembler.assemble()

        assert "ROOT RULE" in prompt
        assert "PKG RULE" in prompt
        # Root should appear before pkg (root-first order)
        assert prompt.index("ROOT RULE") < prompt.index("PKG RULE")

    # ------------------------------------------------------------------
    # Scope change detection
    # ------------------------------------------------------------------

    def test_scope_section_present(self, assembler):
        prompt = assembler.assemble()
        assert "ACTIVE SCOPE:" in prompt

    def test_scope_change_note_on_new_workspace(self, assembler, tmp_path):
        assembler.assemble()  # Initial — no workspace

        workspace = tmp_path / "ws"
        workspace.mkdir()
        (workspace / AGENTS_FILENAME).write_text("WS RULE", encoding="utf-8")
        assembler.resolver.resolve_chain(str(workspace / "f.py"))

        prompt = assembler.assemble()
        assert "Newly active workspace rules:" in prompt

    def test_scope_change_note_on_removed_workspace(self, assembler, tmp_path):
        # First: discover workspace A
        ws_a = tmp_path / "ws_a"
        ws_a.mkdir()
        (ws_a / AGENTS_FILENAME).write_text("A RULE", encoding="utf-8")
        assembler.resolver.resolve_chain(str(ws_a / "f.py"))
        assembler.assemble()

        # Now: remove ws_a's AGENTS.md and invalidate
        (ws_a / AGENTS_FILENAME).unlink()
        assembler.resolver.invalidate_cache()
        assembler.resolver._discovered.discard(str(ws_a / AGENTS_FILENAME))
        assembler.mark_dirty()

        prompt = assembler.assemble()
        assert "no longer apply" in prompt

    # ------------------------------------------------------------------
    # get_base_rules / get_workspace_rules_for
    # ------------------------------------------------------------------

    def test_get_base_rules(self, assembler):
        rules = assembler.get_base_rules()
        assert "SECURITY" in rules
        assert "{os_label}" not in rules  # Placeholders filled

    def test_get_workspace_rules_for_empty(self, assembler):
        assert assembler.get_workspace_rules_for([]) == ""

    def test_get_workspace_rules_for_with_paths(self, assembler, tmp_path):
        workspace = tmp_path / "project"
        workspace.mkdir()
        (workspace / AGENTS_FILENAME).write_text("PROJECT RULE", encoding="utf-8")

        result = assembler.get_workspace_rules_for([str(workspace / "src/main.py")])
        assert "PROJECT RULE" in result

    # ------------------------------------------------------------------
    # AssemblerConfig defaults
    # ------------------------------------------------------------------

    def test_config_defaults(self):
        cfg = AssemblerConfig()
        assert cfg.user_dir  # Not empty
        assert cfg.defaults_dir  # Not empty

    def test_config_custom(self, tmp_path):
        cfg = AssemblerConfig(user_dir=str(tmp_path), defaults_dir=str(tmp_path))
        assert cfg.user_dir == str(tmp_path)


class TestPromptScope:
    def test_empty_scope(self):
        scope = PromptScope()
        assert scope.workspace_agents == ()

    def test_scope_equality(self):
        a = PromptScope(workspace_agents=("/a/AGENTS.md",))
        b = PromptScope(workspace_agents=("/a/AGENTS.md",))
        assert a == b

    def test_scope_inequality(self):
        a = PromptScope(workspace_agents=("/a/AGENTS.md",))
        b = PromptScope(workspace_agents=("/b/AGENTS.md",))
        assert a != b
