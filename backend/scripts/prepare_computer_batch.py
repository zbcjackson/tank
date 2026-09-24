"""Offline proposal CLI plus explicitly authorized, fixed single-pilot APIs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from tank_backend.agents.definition import load_agent_definitions
from tank_backend.benchmarks.comparison_contract import ComparisonContract
from tank_backend.benchmarks.frozen_inputs import FrozenFile, FrozenInputs
from tank_backend.benchmarks.task import load_suite, load_suite_tasks
from tank_backend.config import AppConfig

if TYPE_CHECKING:
    from tank_backend.benchmarks.batch import BatchResult

BACKEND = Path(__file__).resolve().parents[1]
SUITE = BACKEND / "benchmarks/computer_use"
# Mirrors the pair rounds in _spec(); core execution refuses anything else.
CORE_PHASES = ("pair-1", "pair-2", "pair-3")
BLOCKERS = [
    "independent_scoring",
    "real_environment_and_physical_cleanup", "pilot_acceptance_before_core",
    "live_endpoint_and_image_scope_authorization",
]


def _relative(path: Path) -> str:
    return os.path.relpath(path.resolve(), BACKEND)


def _spec(freeze: Path) -> dict[str, Any]:
    rounds = [
        ("pilot", ["A-control", "B-protocol-only", "A", "B-host-only", "B-combined",
                   "B-pixels-only"]),
        ("pair-1", ["A", "B-combined", "C", "D"]),
        ("pair-2", ["B-combined", "C", "D", "A"]),
        ("pair-3", ["C", "D", "A", "B-combined"]),
    ]
    trials = []
    for phase, variants in rounds:
        for variant in variants:
            locator = 15 if variant in {"C", "D"} else 0
            trials.append({
                "key": f"{phase}-{variant.lower()}", "phase": phase, "variant": variant,
                "suite_dir": _relative(SUITE), "task_id": "calc-open", "platform": "macos",
                "agent_name": "computer_use",
                "config_path": _relative(freeze / "runtime" / variant.lower() / "config.yaml"),
                "request_limits": {"planner": 16, "locator": locator, "total": 16 + locator},
                "tokens": 300000, "timeout_s": 120, "max_steps": 15,
            })
    return {
        "schema_version": 3, "live_authorized": False, "record_only": True,
        "input_cleanup": True,
        "freeze_dir": _relative(freeze), "budget_nano_usd": 8000000000,
        "batch_tokens": 5400000, "batch_requests": 378,
        "core_requires_pilot_acceptance": True, "trials": trials,
    }


def _required(freeze: Path) -> tuple[set[Path], FrozenInputs]:
    manifest = json.loads((freeze / "manifest.json").read_text())
    evidence = FrozenInputs(tuple(
        FrozenFile(root / name, digest)
        for group, root in (("sources", BACKEND), ("artifacts", freeze))
        for name, digest in manifest[group].items()
    ), trees=(freeze / "runtime",))
    required = {item.path for item in evidence.files}
    required.update({freeze / "manifest.json", Path(__file__), SUITE / "suite.yaml"})
    for directory in (SUITE / "tasks", SUITE / "assets"):
        required.update(path for path in directory.rglob("*") if path.is_file())
    return required, evidence


def preflight(freeze: Path, proposal_path: Path) -> dict[str, Any]:
    """Verify saved pins and resolved inputs without clients, shell, IME or scoring."""
    proposal = json.loads(proposal_path.read_text())
    pins = proposal.pop("files")
    if proposal != _spec(freeze):
        raise ValueError("Batch proposal differs from the fixed M5 schedule or limits")
    required, evidence = _required(freeze)
    frozen = FrozenInputs(tuple(FrozenFile(BACKEND / name, digest) for name, digest in pins.items()))
    frozen.verify(required)
    evidence.verify()
    suite = load_suite(SUITE / "suite.yaml")
    tasks = [task for task in load_suite_tasks(SUITE / "tasks", "macos", suite.defaults)
             if task.id == "calc-open"]
    if len(tasks) != 1:
        raise ValueError("Batch proposal requires exactly one Calculator task")
    task = tasks[0]
    if (task.timeout_s, task.max_steps, task.gui_only, task.scoring) != (120, 15, True, "strict"):
        raise ValueError("Batch proposal Calculator task limits/scoring mismatch")
    for variant in dict.fromkeys(row["variant"] for row in proposal["trials"]):
        runtime = freeze / "runtime" / variant.lower()
        if (runtime / ".env").exists():
            raise ValueError("Offline proposal does not accept adjacent credential files")
        with patch.dict(os.environ, {"M5_DASHSCOPE_API_KEY": "offline-placeholder"}):
            config = AppConfig.load(runtime / "config.yaml")
        definition = load_agent_definitions([runtime / "agents"])["computer_use"]
        ComparisonContract(freeze, variant).verify(config, definition)
    rows = proposal["trials"]
    totals = {
        "trials": len(rows),
        "planner_requests": sum(row["request_limits"]["planner"] for row in rows),
        "locator_requests": sum(row["request_limits"]["locator"] for row in rows),
        "max_locator_requests": sum(row["request_limits"]["locator"] for row in rows
                                    if row["variant"] == "D"),
        "http_requests": sum(row["request_limits"]["total"] for row in rows),
        "tokens": sum(row["tokens"] for row in rows),
        "task_seconds": sum(row["timeout_s"] for row in rows),
    }
    return {
        "offline_checks_passed": True, "live_ready": False, "totals": totals,
        "blockers": BLOCKERS, "checked_files": len(pins),
        "token_cost_gate": "disabled", "effective_agent_token_budget": 0,
        "input_cleanup": True,
    }


async def execute_a_control(
    freeze: Path, proposal_path: Path, output: Path, *, live_authorized: bool = False,
) -> BatchResult:
    """Run only the scheduled A-control pilot; never advance to another entry."""
    return await _execute_pilot(
        freeze, proposal_path, output, pilot_index=0, live_authorized=live_authorized,
    )


async def execute_b_protocol_only(
    freeze: Path, proposal_path: Path, output: Path, *, live_authorized: bool = False,
) -> BatchResult:
    """Run only the scheduled B-protocol-only pilot; no other entry is executed."""
    return await _execute_pilot(
        freeze, proposal_path, output, pilot_index=1, live_authorized=live_authorized,
    )


async def execute_a(
    freeze: Path, proposal_path: Path, output: Path, *, live_authorized: bool = False,
) -> BatchResult:
    """Run only the scheduled A pilot; no other entry is executed."""
    return await _execute_pilot(
        freeze, proposal_path, output, pilot_index=2, live_authorized=live_authorized,
    )


async def execute_b_host_only(
    freeze: Path, proposal_path: Path, output: Path, *, live_authorized: bool = False,
) -> BatchResult:
    """Run only the scheduled B-host-only pilot; no other entry is executed."""
    return await _execute_pilot(
        freeze, proposal_path, output, pilot_index=3, live_authorized=live_authorized,
    )


async def execute_b_combined(
    freeze: Path, proposal_path: Path, output: Path, *, live_authorized: bool = False,
) -> BatchResult:
    """Run only the scheduled B-combined pilot; no other entry is executed."""
    return await _execute_pilot(
        freeze, proposal_path, output, pilot_index=4, live_authorized=live_authorized,
    )


async def execute_b_pixels_only(
    freeze: Path, proposal_path: Path, output: Path, *, live_authorized: bool = False,
) -> BatchResult:
    """Run only the scheduled B-pixels-only pilot; no other entry is executed."""
    return await _execute_pilot(
        freeze, proposal_path, output, pilot_index=5, live_authorized=live_authorized,
    )


async def execute_core_trials(
    freeze: Path, proposal_path: Path, output: Path, *, live_authorized: bool = False,
    pilot_acceptance: str | None = None,
) -> list[BatchResult]:
    """Run the scheduled paired core trials, in order, one batch each.

    Each pair is A/B-combined/C/D in the declared rotation, which is what makes
    the comparison paired rather than grouped. C and D allow locator requests on
    top of the planner ones, so every row keeps its own request limits: one batch
    per row is the only shape that can carry per-row limits today. The desktop
    takeover stays with the caller; this API neither prepares nor restores it.
    """
    if live_authorized is not True:
        raise ValueError("Explicit live screenshot/endpoint authorization is required")
    if not pilot_acceptance:
        raise ValueError("Core trials require a recorded pilot acceptance decision")
    proposal_bytes = proposal_path.read_bytes()
    preflight(freeze, proposal_path)
    if proposal_path.read_bytes() != proposal_bytes:
        raise ValueError("Proposal changed during preflight")
    proposal = json.loads(proposal_bytes)
    if proposal.get("core_requires_pilot_acceptance") is not True:
        raise ValueError("Proposal does not bind core trials to pilot acceptance")
    rows = [row for row in proposal["trials"] if row["phase"] in CORE_PHASES]
    expected = [row for row in _spec(freeze)["trials"] if row["phase"] in CORE_PHASES]
    if len(rows) != len(expected):
        raise ValueError(f"Expected {len(expected)} scheduled core trials, found {len(rows)}")
    files = tuple(FrozenFile(BACKEND / name, digest)
                  for name, digest in proposal["files"].items())
    files += (FrozenFile(proposal_path, hashlib.sha256(proposal_bytes).hexdigest()),)
    from tank_backend.benchmarks.batch import BatchTrial, run_batch
    from tank_backend.benchmarks.request_budget import RequestLimits
    from tank_backend.benchmarks.spend_ledger import SpendLimit

    results: list[BatchResult] = []
    output.mkdir(parents=True, exist_ok=False)
    for row in rows:
        trial_dir = output / row["key"]
        results.append(await run_batch(
            (BatchTrial(row["key"], BACKEND / row["suite_dir"], row["task_id"],
                        row["agent_name"], BACKEND / row["config_path"], row["platform"],
                        ComparisonContract(freeze, row["variant"])),),
            out_dir=trial_dir,
            batch_limit=SpendLimit(row["tokens"], proposal["budget_nano_usd"]),
            trial_limit=SpendLimit(row["tokens"], proposal["budget_nano_usd"]),
            request_limits=RequestLimits(**row["request_limits"]), contracts=(),
            batch_request_limit=row["request_limits"]["total"],
            frozen_inputs=FrozenInputs(files, trees=(freeze / "runtime",)),
            record_only=True, input_cleanup=True,
        ))
    (output / "core-result.json").write_text(json.dumps(
        {"pilot_acceptance": pilot_acceptance, "completed": [row["key"] for row in rows],
         "batches": results}, indent=2, default=str) + "\n")
    return results


async def _execute_pilot(
    freeze: Path, proposal_path: Path, output: Path, *, pilot_index: int, live_authorized: bool,
) -> BatchResult:
    """Run exactly one pilot after caller approval and controlled-desktop setup.

    This API neither obtains screenshot consent nor prepares/restores the desktop.
    The CLI stays offline. There is no automatic next pilot or core transition.
    """
    if live_authorized is not True:
        raise ValueError("Explicit live screenshot/endpoint authorization is required")
    proposal_bytes = proposal_path.read_bytes()
    preflight(freeze, proposal_path)
    if proposal_path.read_bytes() != proposal_bytes:
        raise ValueError("Proposal changed during preflight")
    proposal = json.loads(proposal_bytes)
    # Each fixed public entry point selects one row; preflight binds the schedule.
    row = proposal["trials"][pilot_index]
    files = tuple(FrozenFile(BACKEND / name, digest)
                  for name, digest in proposal["files"].items())
    files += (FrozenFile(proposal_path, hashlib.sha256(proposal_bytes).hexdigest()),)
    from tank_backend.benchmarks.batch import BatchTrial, run_batch
    from tank_backend.benchmarks.request_budget import RequestLimits
    from tank_backend.benchmarks.spend_ledger import SpendLimit

    return await run_batch(
        (BatchTrial(row["key"], BACKEND / row["suite_dir"], row["task_id"],
                    row["agent_name"], BACKEND / row["config_path"], row["platform"],
                    ComparisonContract(freeze, row["variant"])),),
        out_dir=output,
        batch_limit=SpendLimit(row["tokens"], proposal["budget_nano_usd"]),
        trial_limit=SpendLimit(row["tokens"], proposal["budget_nano_usd"]),
        request_limits=RequestLimits(**row["request_limits"]), contracts=(),
        batch_request_limit=row["request_limits"]["total"],
        frozen_inputs=FrozenInputs(files, trees=(freeze / "runtime",)),
        record_only=True, input_cleanup=True,
    )


def prepare(freeze: Path, output: Path) -> None:
    required, evidence = _required(freeze)
    evidence.verify()
    proposal = _spec(freeze)
    proposal["files"] = {
        _relative(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(required)
    }
    output.mkdir(parents=True, exist_ok=False)
    path = output / "proposal.json"
    path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    report = preflight(freeze, path)
    (output / "preflight.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--check", type=Path)
    args = parser.parse_args()
    if args.check:
        print(json.dumps(preflight(args.freeze, args.check), indent=2))
    else:
        prepare(args.freeze, args.output)
