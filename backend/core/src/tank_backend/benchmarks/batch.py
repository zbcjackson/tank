"""Explicit serial benchmark schedules; durable evidence, no automatic replay."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO, TypedDict

from .comparison_contract import ComparisonContract
from .driver import SubAgentDriver
from .frozen_inputs import FrozenInputs
from .request_budget import RequestLimits
from .runner import run_suite
from .spend_http import ContextWindowContract, SpendControl
from .spend_ledger import SpendLedger, SpendLimit, SpendSnapshot
from .task import PLATFORMS, load_suite, load_suite_tasks


@dataclass(frozen=True)
class BatchTrial:
    key: str
    suite_dir: Path
    task_id: str
    agent_name: str
    config_path: Path
    platform: str
    comparison: ComparisonContract | None = None


class BatchResult(TypedDict):
    completed: list[str]
    spend: SpendSnapshot


def _record(stream: TextIO, value: object) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
    stream.flush()
    os.fsync(stream.fileno())
    directory = os.open(Path(stream.name).parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _required_files(entries: tuple[BatchTrial, ...]) -> set[Path]:
    required: set[Path] = set()
    for entry in entries:
        required.update((entry.config_path, entry.suite_dir / "suite.yaml"))
        if entry.comparison is not None:
            required.update(entry.comparison.required_files(entry.config_path))
        environment = entry.config_path.parent / ".env"
        if environment.exists():
            required.add(environment)
        required.update((entry.suite_dir / "tasks").glob("*.yaml"))
        suite = load_suite(entry.suite_dir / "suite.yaml")
        if suite.assets_dir:
            required.update(path for path in (entry.suite_dir / suite.assets_dir).rglob("*")
                            if path.is_file())
    return required


async def run_batch(
    entries: tuple[BatchTrial, ...],
    *,
    out_dir: Path,
    batch_limit: SpendLimit,
    trial_limit: SpendLimit,
    request_limits: RequestLimits,
    contracts: tuple[ContextWindowContract, ...],
    batch_request_limit: int,
    frozen_inputs: FrozenInputs,
    record_only: bool = False,
) -> BatchResult:
    """Run each explicit task/agent once, in order, sharing one durable ledger.

    An existing output directory is refused even after clean completion. This
    records interruptions for review; it cannot establish a safe desktop resume.
    Limits/contracts are caller supplied and are not provider-verified here.
    """
    if not entries or len({entry.key for entry in entries}) != len(entries):
        raise ValueError("Batch entries must be nonempty and have unique keys")
    if type(batch_request_limit) is not int or batch_request_limit < 0:
        raise ValueError("Batch request limit must be a non-negative integer")
    for entry in entries:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", entry.key):
            raise ValueError("Batch keys must be lowercase letters, digits and hyphens")
        if entry.platform not in PLATFORMS:
            raise ValueError("Unsupported batch platform")
        suite = load_suite(entry.suite_dir / "suite.yaml")
        tasks = load_suite_tasks(entry.suite_dir / "tasks", entry.platform, defaults=suite.defaults)
        if sum(task.id == entry.task_id for task in tasks) != 1:
            raise ValueError(f"Batch task must match exactly once: {entry.task_id}")
    frozen_inputs.verify(_required_files(entries))

    out_dir.mkdir(parents=True, exist_ok=False)
    directory = os.open(out_dir.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    with (out_dir / "batch-plan.json").open("x", encoding="utf-8") as plan:
        _record(plan, {
            "entries": [asdict(entry) for entry in entries],
            "batch_limit": asdict(batch_limit), "trial_limit": asdict(trial_limit),
            "request_limits": asdict(request_limits),
            "contracts": [asdict(contract) for contract in contracts],
            "batch_request_limit": batch_request_limit, "record_only": record_only,
            "frozen_inputs": asdict(frozen_inputs),
        })
    ledger = SpendLedger(
        batch_limit, journal=out_dir / "spend.jsonl", request_limit=batch_request_limit,
        record_only=record_only,
    )
    control = SpendControl(ledger, trial_limit, contracts)
    completed: list[str] = []

    def verify_inputs() -> None:
        try:
            frozen_inputs.verify()
            frozen_inputs.verify(_required_files(entries))
        except ValueError:
            ledger.stop("frozen_inputs")
            raise

    try:
        with (out_dir / "batch-events.jsonl").open("x", encoding="utf-8") as events:
            for entry in entries:
                if ledger.snapshot()["stop_reason"] is not None:
                    break
                if ledger.snapshot()["batch"]["admitted_requests"] >= batch_request_limit:
                    ledger.stop("batch_requests")
                    break
                verify_inputs()
                _record(events, {"kind": "started", "key": entry.key})
                driver = SubAgentDriver.create(
                    entry.agent_name, entry.config_path,
                    request_limits=request_limits, spend=control,
                    comparison=entry.comparison,
                )
                verify_inputs()
                report = await run_suite(
                    entry.suite_dir, lambda driver=driver: driver,
                    platform=entry.platform, trials=1,
                    out_dir=out_dir / entry.key, label=entry.key,
                    task_filter=re.compile(r"\A" + re.escape(entry.task_id) + r"\Z"),
                )
                completed.append(entry.key)
                _record(events, {"kind": "finished", "key": entry.key})
                outcomes = report.metadata.get("outcomes", [])
                if len(outcomes) != 1 or outcomes[0].get("cleanup") != "confirmed":
                    ledger.stop("cleanup_unconfirmed")
    except BaseException:
        ledger.stop("batch_interrupted")
        raise
    finally:
        try:
            ledger.close()
        finally:
            result: BatchResult = {"completed": completed, "spend": ledger.snapshot()}
            with (out_dir / "batch-result.json").open("x", encoding="utf-8") as output:
                _record(output, result)
    return result
