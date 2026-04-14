"""Tests for prompts.resolver — AgentsFileResolver."""

from unittest.mock import MagicMock

import pytest

from tank_backend.prompts.resolver import AGENTS_FILENAME, AgentsFileResolver


class TestAgentsFileResolver:
    @pytest.fixture
    def resolver(self):
        return AgentsFileResolver()

    @pytest.fixture
    def tree_single(self, tmp_path):
        """tmp_path/project/AGENTS.md exists, resolve from tmp_path/project/src/foo.py."""
        project = tmp_path / "project"
        project.mkdir()
        agents = project / AGENTS_FILENAME
        agents.write_text("# Project rules", encoding="utf-8")
        src = project / "src"
        src.mkdir()
        (src / "foo.py").write_text("pass", encoding="utf-8")
        return project, src / "foo.py"

    @pytest.fixture
    def tree_multi(self, tmp_path):
        """Two levels: tmp_path/AGENTS.md and tmp_path/project/AGENTS.md."""
        (tmp_path / AGENTS_FILENAME).write_text("# Root rules", encoding="utf-8")
        project = tmp_path / "project"
        project.mkdir()
        (project / AGENTS_FILENAME).write_text("# Project rules", encoding="utf-8")
        src = project / "src"
        src.mkdir()
        (src / "foo.py").write_text("pass", encoding="utf-8")
        return tmp_path, project, src / "foo.py"

    def test_resolve_chain_single(self, resolver, tree_single):
        project, file_path = tree_single
        chain = resolver.resolve_chain(str(file_path))
        assert len(chain) == 1
        assert chain[0] == str(project / AGENTS_FILENAME)

    def test_resolve_chain_multi_level_root_first(self, resolver, tree_multi):
        root, project, file_path = tree_multi
        chain = resolver.resolve_chain(str(file_path))
        assert len(chain) >= 2
        # Root comes before project (root-first order)
        root_idx = chain.index(str(root / AGENTS_FILENAME))
        proj_idx = chain.index(str(project / AGENTS_FILENAME))
        assert root_idx < proj_idx

    def test_resolve_chain_no_agents_md(self, resolver, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        chain = resolver.resolve_chain(str(empty_dir))
        assert chain == []

    def test_resolve_chain_caches_result(self, resolver, tree_single):
        project, file_path = tree_single
        chain1 = resolver.resolve_chain(str(file_path.parent))
        chain2 = resolver.resolve_chain(str(file_path.parent))
        assert chain1 == chain2

    def test_resolve_chain_file_path_uses_parent(self, resolver, tree_single):
        project, file_path = tree_single
        chain = resolver.resolve_chain(str(file_path))
        # Should find AGENTS.md in project/ (parent of src/)
        assert str(project / AGENTS_FILENAME) in chain

    def test_has_new_discovery_flag(self, resolver, tree_single):
        assert not resolver.has_new_discovery
        project, file_path = tree_single
        resolver.resolve_chain(str(file_path))
        assert resolver.has_new_discovery

    def test_reset_discovery_flag(self, resolver, tree_single):
        project, file_path = tree_single
        resolver.resolve_chain(str(file_path))
        assert resolver.has_new_discovery
        resolver.reset_discovery_flag()
        assert not resolver.has_new_discovery

    def test_no_new_discovery_on_repeat(self, resolver, tree_single):
        project, file_path = tree_single
        resolver.resolve_chain(str(file_path))
        resolver.reset_discovery_flag()
        # Resolve same path again — no new discovery
        resolver.resolve_chain(str(file_path))
        # The chain is cached, so _discovered doesn't grow
        assert not resolver.has_new_discovery

    def test_all_discovered(self, resolver, tree_multi):
        root, project, file_path = tree_multi
        resolver.resolve_chain(str(file_path))
        discovered = resolver.all_discovered
        assert str(root / AGENTS_FILENAME) in discovered
        assert str(project / AGENTS_FILENAME) in discovered

    def test_invalidate_cache_clears(self, resolver, tree_single):
        project, file_path = tree_single
        resolver.resolve_chain(str(file_path.parent))
        resolver.invalidate_cache()
        # After invalidation, the chain cache is empty but _discovered persists
        # A new resolve will re-walk the filesystem
        chain = resolver.resolve_chain(str(file_path.parent))
        assert len(chain) == 1

    def test_on_file_access_triggers_discovery(self, tree_single):
        project, file_path = tree_single
        bus = MagicMock()
        resolver = AgentsFileResolver(bus=bus)

        # Verify subscribe was called
        bus.subscribe.assert_called_once_with("file_access_decision", resolver._on_file_access)

        # Simulate a Bus message
        from tank_backend.pipeline.bus import BusMessage

        msg = BusMessage(
            type="file_access_decision",
            source="file_read",
            payload={"path": str(file_path), "operation": "read", "level": "allow"},
        )
        resolver._on_file_access(msg)

        assert resolver.has_new_discovery
        assert str(project / AGENTS_FILENAME) in resolver.all_discovered

    def test_on_file_access_ignores_deny(self, tree_single):
        project, file_path = tree_single
        resolver = AgentsFileResolver()

        from tank_backend.pipeline.bus import BusMessage

        msg = BusMessage(
            type="file_access_decision",
            source="file_read",
            payload={"path": str(file_path), "operation": "read", "level": "deny"},
        )
        resolver._on_file_access(msg)

        assert not resolver.has_new_discovery

    def test_on_file_access_ignores_bad_payload(self):
        resolver = AgentsFileResolver()

        from tank_backend.pipeline.bus import BusMessage

        msg = BusMessage(
            type="file_access_decision",
            source="file_read",
            payload="not a dict",
        )
        resolver._on_file_access(msg)  # Should not raise
        assert not resolver.has_new_discovery

    def test_on_file_access_ignores_missing_path(self):
        resolver = AgentsFileResolver()

        from tank_backend.pipeline.bus import BusMessage

        msg = BusMessage(
            type="file_access_decision",
            source="file_read",
            payload={"operation": "read", "level": "allow"},
        )
        resolver._on_file_access(msg)  # Should not raise
        assert not resolver.has_new_discovery
