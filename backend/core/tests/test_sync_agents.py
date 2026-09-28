"""Exercise the portable agent generator through its actual CLI."""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
import tomllib
import yaml

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/sync_agents.py"


def run_sync(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        cwd=root.parent, capture_output=True, text=True, check=False,
    )


def write_agent(root: Path, relative: str, name: str, body: str) -> Path:
    path = root / "agents" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\nname: {name}\ndescription: "Describe {name}"\n---\n{body}', encoding="utf-8",
    )
    return path


def test_generates_all_agents_and_preserves_body(tmp_path: Path) -> None:
    bodies = {
        "code-reviewer": '# Review\n中文 🐍 "quotes" \\ paths\n---\n',
        "planner": "# Plan\n\nKeep this trailing newline.\n",
    }
    write_agent(tmp_path, "review.md", "code-reviewer", bodies["code-reviewer"])
    write_agent(tmp_path, "nested/planner.md", "planner", bodies["planner"])
    result = run_sync(tmp_path)
    assert result.returncode == 0, result.stderr
    for name, body in bodies.items():
        pi_text = (tmp_path / f".pi/agents/{name}.md").read_text(encoding="utf-8")
        header, pi_body = pi_text.removeprefix("---\n").split("\n---\n", 1)
        assert yaml.safe_load(header) == {"name": name, "description": f"Describe {name}"}
        assert pi_body == body
        codex = tomllib.loads((tmp_path / f".codex/agents/{name}.toml").read_text())
        assert codex == {
            "name": name, "description": f"Describe {name}", "developer_instructions": body,
        }


@pytest.mark.parametrize("text", [
    "No frontmatter\n",
    "name: bad\ndescription: missing opening delimiter\n---\nBody\n",
    "---\nname: ../escape\ndescription: bad\n---\nBody\n",
    "---\nname: UpperCase\ndescription: bad\n---\nBody\n",
    "---\nname: yes\ndescription: bad\n---\nBody\n",
    "---\nname: bad\n---\nBody\n",
    "---\nname: bad\ndescription: ['nested']\n---\nBody\n",
    "---\nname: bad\nname: other\ndescription: duplicate\n---\nBody\n",
    "---\nname: bad\ndescription: ' '\n---\nBody\n",
    "---\nname: bad\ndescription: ok\nmodel: ignored-setting\n---\nBody\n",
    "---\nname: bad\ndescription: [\n---\nBody\n",
    "---\nname: bad\ndescription: ok\n---\n \n",
])
def test_invalid_definition_causes_no_writes(tmp_path: Path, text: str) -> None:
    write_agent(tmp_path, "a-good.md", "good", "Good body\n")
    (tmp_path / "agents/z-bad.md").write_text(text, encoding="utf-8")
    result = run_sync(tmp_path)
    assert result.returncode == 2
    assert "z-bad.md" in result.stderr
    assert not (tmp_path / ".pi").exists()
    assert not (tmp_path / ".codex").exists()


def test_duplicate_names_are_rejected_before_writing(tmp_path: Path) -> None:
    write_agent(tmp_path, "first.md", "reviewer", "First body\n")
    write_agent(tmp_path, "nested/second.md", "reviewer", "Second body\n")
    result = run_sync(tmp_path)
    assert result.returncode == 2 and "duplicate" in result.stderr
    assert not (tmp_path / ".pi").exists()
    assert not (tmp_path / ".codex").exists()


@pytest.mark.parametrize("absolute", [False, True])
def test_custom_source_directory(tmp_path: Path, absolute: bool) -> None:
    write_agent(tmp_path, "planner.md", "planner", "Plan\n")
    (tmp_path / "agents").rename(tmp_path / "shared")
    source = str(tmp_path / "shared") if absolute else "shared"
    result = run_sync(tmp_path, "--source-dir", source)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".pi/agents/planner.md").exists()


@pytest.mark.parametrize("empty", [False, True])
def test_missing_or_empty_source_is_an_error(tmp_path: Path, empty: bool) -> None:
    if empty:
        (tmp_path / "agents").mkdir()
    result = run_sync(tmp_path)
    assert result.returncode == 2 and "definitions" in result.stderr
    assert not (tmp_path / ".pi").exists()


@pytest.mark.parametrize("conflict", [
    "manual", "symlink-file", "symlink-dir", "directory", "parent-file",
])
def test_output_conflicts_preserve_every_existing_file(tmp_path: Path, conflict: str) -> None:
    write_agent(tmp_path, "reviewer.md", "reviewer", "Review\n")
    destination = tmp_path / ".codex/agents/reviewer.toml"
    external = tmp_path / "external"
    external.mkdir()
    keep = external / "keep.txt"
    keep.write_text("keep")
    if conflict == "symlink-dir":
        (tmp_path / ".codex").symlink_to(external, target_is_directory=True)
    elif conflict == "parent-file":
        (tmp_path / ".codex").write_text("manual")
    else:
        destination.parent.mkdir(parents=True)
        if conflict == "manual":
            destination.write_text("name = 'manual'\n")
        elif conflict == "symlink-file":
            destination.symlink_to(keep)
        else:
            destination.mkdir()
    result = run_sync(tmp_path)
    assert result.returncode == 2 and ".codex" in result.stderr
    assert not (tmp_path / ".pi").exists()
    assert keep.read_text() == "keep"
    if conflict == "manual":
        assert destination.read_text() == "name = 'manual'\n"
    if conflict in {"symlink-file", "symlink-dir"}:
        assert (destination if conflict == "symlink-file" else tmp_path / ".codex").is_symlink()


def test_check_is_read_only_and_sync_updates_only_changed_outputs(tmp_path: Path) -> None:
    source = write_agent(tmp_path, "planner.md", "planner", "Original\n")
    missing = run_sync(tmp_path, "--check")
    assert missing.returncode == 1 and "planner.toml" in missing.stdout
    assert not (tmp_path / ".pi").exists() and not (tmp_path / ".codex").exists()
    assert run_sync(tmp_path).returncode == 0
    targets = [tmp_path / ".pi/agents/planner.md", tmp_path / ".codex/agents/planner.toml"]
    original = [(path.read_bytes(), path.stat().st_mtime_ns) for path in targets]
    unrelated = tmp_path / ".codex/agents/handmade.toml"
    unrelated.write_text("name = 'handmade'\n")
    assert run_sync(tmp_path, "--check").returncode == 0
    assert run_sync(tmp_path).returncode == 0
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in targets] == original
    source.write_text(source.read_text().replace("Original", "Updated"))
    assert run_sync(tmp_path, "--check").returncode == 1
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in targets] == original
    assert run_sync(tmp_path).returncode == 0
    assert tomllib.loads(targets[1].read_text())["developer_instructions"] == "Updated\n"
    assert unrelated.read_text() == "name = 'handmade'\n"
    assert run_sync(tmp_path, "--check").returncode == 0


def test_failed_replace_keeps_old_files_and_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_agent(tmp_path, "planner.md", "planner", "Original\n")
    assert run_sync(tmp_path).returncode == 0
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    source.write_text(source.read_text().replace("Original", "Updated"))
    main = cast(Callable[[], int], runpy.run_path(str(SCRIPT))["main"])
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--root", str(tmp_path)])

    def fail_replace(src: object, dst: object) -> None:
        raise OSError("injected replacement failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    assert main() == 2
    assert {path for path in tmp_path.rglob("*") if path.is_file()} == before.keys()
    for path, content in before.items():
        if path != source:
            assert path.read_bytes() == content


@pytest.mark.parametrize("source_dir", [".", ".pi/agents", ".codex/agents"])
def test_source_cannot_overlap_generated_directories(tmp_path: Path, source_dir: str) -> None:
    source = write_agent(tmp_path, "planner.md", "planner", "Plan\n")
    destination = tmp_path / source_dir / "planner.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)
    result = run_sync(tmp_path, "--source-dir", source_dir)
    assert result.returncode == 2 and "source/output directories overlap" in result.stderr
    assert not (tmp_path / ".codex/agents/planner.toml").exists()


def test_repository_agent_outputs_are_in_sync() -> None:
    result = run_sync(SCRIPT.parents[1], "--check")
    assert result.returncode == 0, result.stdout + result.stderr
