"""Tests for benchmark task YAML loading and platform overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from tank_backend.benchmarks.task import (
    BenchTask,
    TaskError,
    current_platform,
    load_suite,
    load_suite_tasks,
    load_task,
)

VALID = """
id: local-form-submit
category: form
difficulty: 2
platforms: [linux, macos]
instruction: "Fill the form and submit"
setup: |
  rm -rf ~/bench-work && mkdir -p ~/bench-work
validator:
  kind: shell
  command: test -f ~/bench-work/submitted.json
timeout_s: 120
max_steps: 25
"""


def _write(tmp_path: Path, body: str, name: str = "t.yaml") -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


# ── loading ──────────────────────────────────────────────────────────


def test_load_task_full_fields(tmp_path):
    task = load_task(_write(tmp_path, VALID), platform="linux")
    assert task.id == "local-form-submit"
    assert task.category == "form"
    assert task.difficulty == 2
    assert task.platforms == ("linux", "macos")
    assert task.instruction == "Fill the form and submit"
    assert "mkdir" in task.setup
    assert task.validator_command == "test -f ~/bench-work/submitted.json"
    assert task.timeout_s == 120
    assert task.max_steps == 25


def test_platform_overrides(tmp_path):
    body = VALID + """
instruction_macos: "Open Safari and fill the form"
setup_macos: |
  rm -rf ~/bench-work
validator_macos:
  kind: shell
  command: test -f /tmp/mac.json
"""
    mac = load_task(_write(tmp_path, body), platform="macos")
    linux = load_task(_write(tmp_path, body, name="t2.yaml"), platform="linux")
    assert mac.instruction.startswith("Open Safari")
    assert mac.validator_command == "test -f /tmp/mac.json"
    assert mac.setup == "rm -rf ~/bench-work\n"
    assert linux.instruction == "Fill the form and submit"
    assert linux.validator_command == "test -f ~/bench-work/submitted.json"


def test_defaults_when_optional_fields_missing(tmp_path):
    body = """
id: minimal
category: app
difficulty: 1
platforms: [macos]
instruction: "Do it"
validator:
  kind: shell
  command: "true"
"""
    task = load_task(
        _write(tmp_path, body), platform="macos",
        defaults={"timeout_s": 60, "max_steps": 10},
    )
    assert task.setup == ""
    assert task.timeout_s == 60
    assert task.max_steps == 10


# ── validation ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body,match",
    [
        ("id: x\ncategory: app\ndifficulty: 1\nplatforms: [macos]\n", "instruction"),
        ("category: app\ndifficulty: 1\nplatforms: [macos]\ninstruction: i\n", "id"),
        ("id: x\ndifficulty: 1\nplatforms: [macos]\ninstruction: i\n", "category"),
        (
            "id: x\ncategory: bogus\ndifficulty: 1\nplatforms: [macos]\ninstruction: i\n",
            "category",
        ),
        (
            "id: x\ncategory: app\ndifficulty: 5\nplatforms: [macos]\ninstruction: i\n",
            "difficulty",
        ),
        (
            "id: x\ncategory: app\ndifficulty: 1\ninstruction: i\n",
            "platforms",
        ),
        (
            "id: x\ncategory: app\ndifficulty: 1\nplatforms: [macos]\ninstruction: i\n"
            "validator:\n  kind: shell\n",
            "command",
        ),
        (
            "id: x\ncategory: app\ndifficulty: 1\nplatforms: [macos]\ninstruction: i\n"
            "validator:\n  kind: pixels\n  command: x\n",
            "kind",
        ),
    ],
)
def test_invalid_task_raises(tmp_path, body, match):
    with pytest.raises(TaskError, match=match):
        load_task(_write(tmp_path, body), platform="macos")


def test_suite_tasks_filtered_by_platform(tmp_path):
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "a.yaml").write_text(VALID, encoding="utf-8")
    (tasks_dir / "b.yaml").write_text(
        VALID.replace("local-form-submit", "mac-only").replace(
            "platforms: [linux, macos]", "platforms: [macos]"
        ),
        encoding="utf-8",
    )
    (tasks_dir / "c.yaml").write_text(
        VALID.replace("local-form-submit", "linux-only").replace(
            "platforms: [linux, macos]", "platforms: [linux]"
        ),
        encoding="utf-8",
    )
    linux_tasks = load_suite_tasks(tasks_dir, platform="linux")
    assert [t.id for t in linux_tasks] == ["local-form-submit", "linux-only"]


def test_load_suite_reads_defaults(tmp_path):
    suite = tmp_path / "suite.yaml"
    suite.write_text(
        "name: computer_use\nagent: computer_use\n"
        "defaults:\n  trials: 2\n  timeout_s: 90\n  max_steps: 12\n",
        encoding="utf-8",
    )
    loaded = load_suite(suite)
    assert loaded.name == "computer_use"
    assert loaded.agent == "computer_use"
    assert loaded.defaults == {"trials": 2, "timeout_s": 90, "max_steps": 12}


def test_load_suite_defaults_optional(tmp_path):
    loaded = load_suite(_write(tmp_path, "name: x\n"))
    assert loaded.agent is None
    assert loaded.defaults == {}


def test_current_platform():
    assert current_platform() in ("macos", "linux")


# ── real suite loads cleanly ─────────────────────────────────────────

_REAL_SUITE = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "computer_use"
)


def test_real_suite_tasks_all_load_for_both_platforms():
    """Schema-validate every task YAML in the shipped computer_use suite."""
    for platform in ("macos", "linux"):
        tasks = load_suite_tasks(_REAL_SUITE / "tasks", platform=platform)
        assert len(tasks) >= 10, f"expected a full suite for {platform}, got {len(tasks)}"
        ids = [t.id for t in tasks]
        assert len(ids) == len(set(ids)), "duplicate task ids"
        for task in tasks:
            assert 1 <= task.difficulty <= 3
            assert task.instruction.strip()
            assert task.validator_command.strip()


def test_real_suite_yaml_loads():
    suite = load_suite(_REAL_SUITE / "suite.yaml")
    assert suite.name == "computer_use"
    assert suite.agent == "computer_use"
    assert suite.defaults.get("trials") == 3


def test_bench_task_is_frozen():
    task = BenchTask(
        id="x", category="app", difficulty=1, platforms=("macos",),
        instruction="i", setup="", validator_command="true",
        timeout_s=60, max_steps=10,
    )
    with pytest.raises(AttributeError):
        task.id = "y"  # type: ignore[misc]
