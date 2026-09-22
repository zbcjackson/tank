"""Explicit serial benchmark schedules; durable evidence, no automatic replay."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO, TypedDict

from .driver import SubAgentDriver
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


async def run_batch(
    entries: tuple[BatchTrial, ...],
    *,
    out_dir: Path,
    batch_limit: SpendLimit,
    trial_limit: SpendLimit,
    request_limits: RequestLimits,
    contracts: tuple[ContextWindowContract, ...],
) -> BatchResult:
    """Run each explicit task/agent once, in order, sharing one durable ledger.

    An existing output directory is refused even after clean completion. This
    records interruptions for review; it cannot establish a safe desktop resume.
    Limits/contracts are caller supplied and are not provider-verified here.
    """
    if not entries or len({entry.key for entry in entries}) != len(entries):
        raise ValueError("Batch entries must be nonempty and have unique keys")
    for entry in entries:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", entry.key):
            raise ValueError("Batch keys must be lowercase letters, digits and hyphens")
        if entry.platform not in PLATFORMS:
            raise ValueError("Unsupported batch platform")
        suite = load_suite(entry.suite_dir / "suite.yaml")
        tasks = load_suite_tasks(entry.suite_dir / "tasks", entry.platform, defaults=suite.defaults)
        if sum(task.id == entry.task_id for task in tasks) != 1:
            raise ValueError(f"Batch task must match exactly once: {entry.task_id}")

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
        })
    ledger = SpendLedger(batch_limit, journal=out_dir / "spend.jsonl")
    control = SpendControl(ledger, trial_limit, contracts)
    completed: list[str] = []
    try:
        with (out_dir / "batch-events.jsonl").open("x", encoding="utf-8") as events:
            for entry in entries:
                if ledger.snapshot()["stop_reason"] is not None:
                    break
                _record(events, {"kind": "started", "key": entry.key})
                driver = SubAgentDriver.create(
                    entry.agent_name, entry.config_path,
                    request_limits=request_limits, spend=control,
                )
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
