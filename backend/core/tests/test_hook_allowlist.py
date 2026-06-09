"""Tests for HookAllowlist — consent system for shell hooks."""

from __future__ import annotations

import json
from pathlib import Path

from tank_backend.hooks.allowlist import HookAllowlist, HookIdentity
from tank_backend.hooks.manager import HookManager, HookSpec

# ---------------------------------------------------------------------------
# HookIdentity
# ---------------------------------------------------------------------------

class TestHookIdentity:
    def test_key_format(self):
        h = HookIdentity(event="pre_tool_call", command="/path/to/hook.sh")
        assert h.key == "pre_tool_call:/path/to/hook.sh"

    def test_fingerprint_stable(self):
        h = HookIdentity(event="pre_tool_call", command="/path/to/hook.sh")
        assert len(h.fingerprint) == 8
        assert h.fingerprint == h.fingerprint  # stable


# ---------------------------------------------------------------------------
# HookAllowlist persistence
# ---------------------------------------------------------------------------

class TestHookAllowlist:
    def test_empty_by_default(self, tmp_path: Path):
        al = HookAllowlist(path=tmp_path / "allowlist.json")
        assert al.list_all() == []

    def test_grant_persists(self, tmp_path: Path):
        path = tmp_path / "allowlist.json"
        al = HookAllowlist(path=path)
        hook = HookIdentity(event="pre_tool_call", command="echo hi")

        al.grant(hook)
        assert al.is_allowed(hook) is True

        # Verify file written
        data = json.loads(path.read_text())
        assert hook.key in data["allowed"]

    def test_revoke_removes(self, tmp_path: Path):
        path = tmp_path / "allowlist.json"
        al = HookAllowlist(path=path)
        hook = HookIdentity(event="pre_tool_call", command="echo hi")

        al.grant(hook)
        assert al.is_allowed(hook) is True

        result = al.revoke(hook)
        assert result is True
        assert al.is_allowed(hook) is False

    def test_revoke_nonexistent_returns_false(self, tmp_path: Path):
        al = HookAllowlist(path=tmp_path / "allowlist.json")
        hook = HookIdentity(event="pre_tool_call", command="nope")
        assert al.revoke(hook) is False

    def test_reload_from_disk(self, tmp_path: Path):
        path = tmp_path / "allowlist.json"
        # Write directly
        path.write_text(json.dumps({"allowed": ["pre_tool_call:echo hi"]}))

        al = HookAllowlist(path=path)
        hook = HookIdentity(event="pre_tool_call", command="echo hi")
        assert al.is_allowed(hook) is True

    def test_auto_accept_allows_everything(self, tmp_path: Path):
        al = HookAllowlist(path=tmp_path / "allowlist.json", auto_accept=True)
        hook = HookIdentity(event="pre_tool_call", command="anything")
        assert al.is_allowed(hook) is True

    def test_grant_all(self, tmp_path: Path):
        al = HookAllowlist(path=tmp_path / "allowlist.json")
        hooks = [
            HookIdentity(event="pre_tool_call", command="a"),
            HookIdentity(event="post_tool_call", command="b"),
        ]
        al.grant_all(hooks)
        assert al.is_allowed(hooks[0]) is True
        assert al.is_allowed(hooks[1]) is True

    def test_idempotent_grant(self, tmp_path: Path):
        path = tmp_path / "allowlist.json"
        al = HookAllowlist(path=path)
        hook = HookIdentity(event="pre_tool_call", command="echo hi")

        al.grant(hook)
        al.grant(hook)  # Should not duplicate
        data = json.loads(path.read_text())
        assert data["allowed"].count(hook.key) == 1


# ---------------------------------------------------------------------------
# HookManager with allowlist filtering
# ---------------------------------------------------------------------------

class TestHookManagerWithAllowlist:
    def test_unapproved_hook_skipped(self, tmp_path: Path):
        """Hooks not in the allowlist are filtered out."""
        al = HookAllowlist(path=tmp_path / "allowlist.json")
        hooks = [
            HookSpec(event="pre_tool_call", command="echo blocked"),
        ]
        mgr = HookManager(hooks=hooks, allowlist=al)

        # Not granted — should be empty
        matched = mgr.get_hooks_for_event("pre_tool_call", "run_command")
        assert matched == []

    def test_approved_hook_runs(self, tmp_path: Path):
        """Hooks in the allowlist pass through."""
        al = HookAllowlist(path=tmp_path / "allowlist.json")
        hook_spec = HookSpec(event="pre_tool_call", command="echo allowed")

        # Grant first
        al.grant(HookIdentity(event="pre_tool_call", command="echo allowed"))

        mgr = HookManager(hooks=[hook_spec], allowlist=al)
        matched = mgr.get_hooks_for_event("pre_tool_call", "run_command")
        assert len(matched) == 1

    def test_no_allowlist_means_no_filtering(self):
        """When allowlist is None, all hooks pass through (backward compat)."""
        hooks = [
            HookSpec(event="pre_tool_call", command="echo x"),
        ]
        mgr = HookManager(hooks=hooks, allowlist=None)
        matched = mgr.get_hooks_for_event("pre_tool_call", "run_command")
        assert len(matched) == 1
