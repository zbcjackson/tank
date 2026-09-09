"""Benchmark task definitions: YAML schema, loading, platform overrides."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CATEGORIES = ("app", "settings", "file", "form", "browser", "typing", "multi-window")
PLATFORMS = ("macos", "linux")


class TaskError(Exception):
    """Raised when a task or suite YAML is invalid."""


def current_platform() -> str:
    """The platform the benchmark is running on."""
    return "macos" if sys.platform == "darwin" else "linux"


@dataclass(frozen=True)
class BenchTask:
    """One benchmark task, resolved for a specific platform."""

    id: str
    category: str
    difficulty: int
    platforms: tuple[str, ...]
    instruction: str
    validator_command: str
    setup: str = ""
    teardown: str = ""
    timeout_s: int = 180
    max_steps: int = 30


@dataclass(frozen=True)
class SuiteConfig:
    """Per-suite configuration from ``suite.yaml``."""

    name: str
    agent: str | None = None
    description: str = ""
    defaults: dict[str, Any] = field(default_factory=dict)
    assets_dir: str | None = None
    server_port: int = 8901


def _validator_command(validator: Any, where: str) -> str:
    if not isinstance(validator, dict):
        raise TaskError(f"{where}: validator must be a mapping with kind+command")
    kind = validator.get("kind", "shell")
    if kind != "shell":
        raise TaskError(f"{where}: validator kind must be 'shell' (got {kind!r})")
    command = validator.get("command")
    if not command or not isinstance(command, str):
        raise TaskError(f"{where}: validator.command is required")
    return command


def load_task(
    path: Path,
    platform: str,
    defaults: dict[str, Any] | None = None,
) -> BenchTask:
    """Load and validate one task YAML, resolving platform overrides.

    ``<field>_<platform>`` keys (``instruction_macos``, ``setup_linux``,
    ``validator_macos``, …) override the base value for that platform.
    """
    where = path.name
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise TaskError(f"{where}: invalid YAML: {e}") from e
    if not isinstance(raw, dict):
        raise TaskError(f"{where}: task file must be a YAML mapping")

    def pick(base: str) -> Any:
        return raw.get(f"{base}_{platform}", raw.get(base))

    task_id = raw.get("id")
    if not task_id or not isinstance(task_id, str):
        raise TaskError(f"{where}: 'id' is required")

    category = raw.get("category")
    if category not in CATEGORIES:
        raise TaskError(
            f"{where}: category must be one of {CATEGORIES} (got {category!r})"
        )

    difficulty = raw.get("difficulty")
    if difficulty not in (1, 2, 3):
        raise TaskError(f"{where}: difficulty must be 1-3 (got {difficulty!r})")

    platforms = raw.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        raise TaskError(f"{where}: platforms must be a non-empty list")
    unknown = [p for p in platforms if p not in PLATFORMS]
    if unknown:
        raise TaskError(f"{where}: unknown platforms {unknown} (known: {PLATFORMS})")

    instruction = pick("instruction")
    if not instruction or not isinstance(instruction, str):
        raise TaskError(f"{where}: 'instruction' is required")

    validator = pick("validator")
    validator_command = _validator_command(validator, where)

    merged = {"timeout_s": 180, "max_steps": 30, **(defaults or {})}
    timeout_s = raw.get("timeout_s", merged["timeout_s"])
    max_steps = raw.get("max_steps", merged["max_steps"])

    setup = pick("setup") or ""
    teardown = pick("teardown") or ""

    return BenchTask(
        id=task_id,
        category=category,
        difficulty=int(difficulty),
        platforms=tuple(platforms),
        instruction=instruction,
        validator_command=validator_command,
        setup=str(setup),
        teardown=str(teardown),
        timeout_s=int(timeout_s),
        max_steps=int(max_steps),
    )


def load_suite_tasks(
    tasks_dir: Path,
    platform: str,
    defaults: dict[str, Any] | None = None,
) -> list[BenchTask]:
    """Load all task YAMLs in a directory, skipping other-platform tasks.

    Files are processed in sorted order for deterministic runs.
    """
    tasks: list[BenchTask] = []
    for path in sorted(tasks_dir.glob("*.yaml")):
        task = load_task(path, platform=platform, defaults=defaults)
        if platform in task.platforms:
            tasks.append(task)
    return tasks


def load_suite(suite_path: Path) -> SuiteConfig:
    """Load ``suite.yaml`` (name required; everything else optional)."""
    try:
        raw = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise TaskError(f"{suite_path.name}: invalid YAML: {e}") from e
    if not isinstance(raw, dict) or not raw.get("name"):
        raise TaskError(f"{suite_path.name}: 'name' is required")
    defaults_raw = raw.get("defaults") or {}
    if not isinstance(defaults_raw, dict):
        raise TaskError(f"{suite_path.name}: defaults must be a mapping")
    return SuiteConfig(
        name=str(raw["name"]),
        agent=raw.get("agent"),
        description=str(raw.get("description", "")),
        defaults=dict(defaults_raw),
        assets_dir=raw.get("assets"),
        server_port=int(raw.get("server_port", 8901)),
    )
