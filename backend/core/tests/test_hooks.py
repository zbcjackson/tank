"""Tests for HookManager — shell hook system."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from tank_backend.hooks.manager import HookDecision, HookManager, HookSpec

# ---------------------------------------------------------------------------
# HookSpec and HookDecision basics
# ---------------------------------------------------------------------------

class TestHookDecision:
    def test_allow(self):
        d = HookDecision.allow()
        assert d.blocked is False
        assert d.reason == ""

    def test_block(self):
        d = HookDecision.block("not allowed")
        assert d.blocked is True
        assert d.reason == "not allowed"


class TestHookSpec:
    def test_defaults(self):
        spec = HookSpec(event="pre_tool_call", command="echo hi")
        assert spec.matcher == ""
        assert spec.timeout == 5.0
        assert spec.enabled is True


# ---------------------------------------------------------------------------
# HookManager filtering
# ---------------------------------------------------------------------------

class TestHookManagerFiltering:
    def test_no_hooks_returns_empty(self):
        mgr = HookManager(hooks=[])
        assert mgr.get_hooks_for_event("pre_tool_call", "run_command") == []

    def test_matches_by_event(self):
        hooks = [
            HookSpec(event="pre_tool_call", command="echo pre"),
            HookSpec(event="post_tool_call", command="echo post"),
        ]
        mgr = HookManager(hooks=hooks)
        pre = mgr.get_hooks_for_event("pre_tool_call", "run_command")
        assert len(pre) == 1
        assert pre[0].command == "echo pre"

    def test_matcher_filters_tool_name(self):
        hooks = [
            HookSpec(
                event="pre_tool_call", command="echo cmd",
                matcher="run_command|persistent_shell",
            ),
            HookSpec(event="pre_tool_call", command="echo all"),
        ]
        mgr = HookManager(hooks=hooks)
        # "file_read" only matches the hook without a matcher
        matched = mgr.get_hooks_for_event("pre_tool_call", "file_read")
        assert len(matched) == 1
        assert matched[0].command == "echo all"

        # "run_command" matches both
        matched = mgr.get_hooks_for_event("pre_tool_call", "run_command")
        assert len(matched) == 2

    def test_disabled_hooks_excluded(self):
        hooks = [
            HookSpec(event="pre_tool_call", command="echo x", enabled=False),
        ]
        mgr = HookManager(hooks=hooks)
        assert mgr.get_hooks_for_event("pre_tool_call", "any") == []


# ---------------------------------------------------------------------------
# Hook execution
# ---------------------------------------------------------------------------

def _make_script(tmp_path: Path, name: str, content: str) -> str:
    """Create an executable script and return its path."""
    script = tmp_path / name
    script.write_text(f"#!/bin/bash\n{content}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


class TestHookExecution:
    @pytest.mark.asyncio
    async def test_pre_tool_call_allow(self, tmp_path: Path):
        """Hook that outputs nothing → allow."""
        script = _make_script(tmp_path, "hook.sh", "cat > /dev/null")
        mgr = HookManager(hooks=[
            HookSpec(event="pre_tool_call", command=script),
        ])
        decision = await mgr.run_pre_tool_call("run_command", {"command": "ls"})
        assert decision.blocked is False

    @pytest.mark.asyncio
    async def test_pre_tool_call_block(self, tmp_path: Path):
        """Hook that returns block action → blocked."""
        script = _make_script(
            tmp_path, "hook.sh",
            'cat > /dev/null; echo \'{"action": "block", "reason": "forbidden"}\'',
        )
        mgr = HookManager(hooks=[
            HookSpec(event="pre_tool_call", command=script),
        ])
        decision = await mgr.run_pre_tool_call("run_command", {"command": "rm -rf /"})
        assert decision.blocked is True
        assert "forbidden" in decision.reason

    @pytest.mark.asyncio
    async def test_pre_tool_call_timeout(self, tmp_path: Path):
        """Hook that hangs → times out, treated as allow."""
        script = _make_script(tmp_path, "hook.sh", "sleep 30")
        mgr = HookManager(hooks=[
            HookSpec(event="pre_tool_call", command=script, timeout=0.5),
        ])
        decision = await mgr.run_pre_tool_call("run_command", {"command": "ls"})
        assert decision.blocked is False  # Timeout = allow (fail-open)

    @pytest.mark.asyncio
    async def test_pre_tool_call_receives_json_stdin(self, tmp_path: Path):
        """Hook receives tool call details on stdin."""
        output_file = tmp_path / "received.json"
        script = _make_script(
            tmp_path, "hook.sh",
            f"cat > {output_file}",
        )
        mgr = HookManager(hooks=[
            HookSpec(event="pre_tool_call", command=script),
        ])
        await mgr.run_pre_tool_call(
            "run_command",
            {"command": "ls -la"},
            session_id="test-session",
        )
        data = json.loads(output_file.read_text())
        assert data["hook_event_name"] == "pre_tool_call"
        assert data["tool_name"] == "run_command"
        assert data["tool_input"] == {"command": "ls -la"}
        assert data["session_id"] == "test-session"

    @pytest.mark.asyncio
    async def test_post_tool_call_fire_and_forget(self, tmp_path: Path):
        """Post-tool hooks run without blocking."""
        output_file = tmp_path / "post.json"
        script = _make_script(
            tmp_path, "hook.sh",
            f"cat > {output_file}",
        )
        mgr = HookManager(hooks=[
            HookSpec(event="post_tool_call", command=script),
        ])
        await mgr.run_post_tool_call(
            "run_command",
            {"command": "ls"},
            result_content="file1\nfile2",
            error=False,
            session_id="s1",
        )
        data = json.loads(output_file.read_text())
        assert data["hook_event_name"] == "post_tool_call"
        assert data["tool_name"] == "run_command"
        assert data["error"] is False
        assert "file1" in data["result"]

    @pytest.mark.asyncio
    async def test_post_tool_call_error_ignored(self, tmp_path: Path):
        """Post-tool hook that fails doesn't raise."""
        script = _make_script(tmp_path, "hook.sh", "exit 1")
        mgr = HookManager(hooks=[
            HookSpec(event="post_tool_call", command=script),
        ])
        # Should not raise
        await mgr.run_post_tool_call("run_command", {"command": "x"})

    @pytest.mark.asyncio
    async def test_missing_command_handled(self):
        """Hook with non-existent command doesn't crash."""
        mgr = HookManager(hooks=[
            HookSpec(event="pre_tool_call", command="/nonexistent/hook"),
        ])
        decision = await mgr.run_pre_tool_call("run_command", {"command": "ls"})
        assert decision.blocked is False

    @pytest.mark.asyncio
    async def test_first_block_wins(self, tmp_path: Path):
        """When multiple hooks match, first block wins."""
        script1 = _make_script(
            tmp_path, "hook1.sh",
            'cat > /dev/null; echo \'{"action": "block", "reason": "hook1"}\'',
        )
        script2 = _make_script(
            tmp_path, "hook2.sh",
            'cat > /dev/null; echo \'{"action": "block", "reason": "hook2"}\'',
        )
        mgr = HookManager(hooks=[
            HookSpec(event="pre_tool_call", command=script1),
            HookSpec(event="pre_tool_call", command=script2),
        ])
        decision = await mgr.run_pre_tool_call("run_command", {"command": "x"})
        assert decision.blocked is True
        assert "hook1" in decision.reason
