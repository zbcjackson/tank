"""Tests for the benchmark local page server and shell helper."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from tank_backend.benchmarks.pageserver import LocalPageServer
from tank_backend.benchmarks.shell import ShellError, run_shell


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("<html>hi</html>", encoding="utf-8")
    return tmp_path


async def test_serves_static_assets(assets):
    async with LocalPageServer(assets, capture_path=None, port=8977) as base:
        with urllib.request.urlopen(f"{base}/index.html", timeout=5) as resp:
            assert resp.status == 200
            assert b"<html>hi</html>" in resp.read()


async def test_form_post_captured_to_file(assets, tmp_path):
    capture = tmp_path / "submissions.jsonl"
    async with LocalPageServer(assets, capture_path=capture, port=8978) as base:
        req = urllib.request.Request(
            f"{base}/submit",
            data=json.dumps({"name": "张三", "email": "z@e.com"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200

    lines = capture.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["kind"] == "submit"
    assert entry["payload"]["name"] == "张三"


async def test_click_log_recorded(assets, tmp_path):
    capture = tmp_path / "submissions.jsonl"
    async with LocalPageServer(assets, capture_path=capture, port=8979) as base:
        urllib.request.urlopen(f"{base}/click?name=link_b", timeout=5).read()

    entry = json.loads(capture.read_text(encoding="utf-8").strip())
    assert entry["kind"] == "click"
    assert entry["name"] == "link_b"


async def test_port_conflict_raises(assets):
    server = LocalPageServer(assets, capture_path=None, port=8980)
    try:
        with pytest.raises(OSError):
            LocalPageServer(assets, capture_path=None, port=8980)
    finally:
        server.stop()


# ── shell helper ─────────────────────────────────────────────────────


async def test_run_shell_captures_output():
    proc = await run_shell("echo hello && echo err >&2", timeout_s=10)
    assert proc.returncode == 0
    assert "hello" in proc.stdout


async def test_run_shell_nonzero_raises():
    with pytest.raises(ShellError) as e:
        await run_shell("exit 3", timeout_s=10)
    assert e.value.returncode == 3


async def test_run_shell_timeout_raises():
    with pytest.raises(ShellError, match="timed out"):
        await run_shell("sleep 5", timeout_s=1)
