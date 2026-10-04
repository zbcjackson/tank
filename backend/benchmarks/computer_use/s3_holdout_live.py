"""Frozen, separately authorized execution of the synthetic selector holdout."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import ExitStack
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from statistics import median
from typing import Any, TextIO

import httpx
from agent_computer_use.contracts import ActionSet
from pydantic import TypeAdapter
from tank_backend.llm.jev_model import JevChoiceRoute
from benchmarks.computer_use.legacy_json_model import parse_choice
from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
from tank_backend.agents.task_runtime import ExecutionRecord
from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
from tank_backend.benchmarks.spend_http import ContextWindowContract
from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance
from tank_backend.llm.model_transport import TaskModelTransport

from benchmarks.computer_use import s3_holdout as dataset
from benchmarks.computer_use import s3_replay as v1
from benchmarks.computer_use import s3_replay_v2 as v2

# Dynamic mappings below are JSON report/request artifacts, not domain objects.
def freeze_inputs() -> dict[str, Any]:
    f = json.loads(json.dumps(dataset.freeze_inputs()))
    f["base_preparation_sha256"] = f.pop("sha256")
    f.update(revision="s3-holdout-live-1", preparation_only=False,
             httpx=version("httpx"), httpcore=version("httpcore"),
             http2=False, keepalive_expiry_seconds=60, warmup_requests=0)
    for source in (Path(__file__), Path(v2.__file__)):
        f["source_hashes"][source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    f["sha256"] = v1.digest(f)
    return f


def prepare(output: Path) -> dict[str, Any]:
    f = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(f, ensure_ascii=False, indent=2) + "\n")
    return f


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    f = freeze_inputs()
    if json.loads((output / "freeze.json").read_text()) != f or f["sha256"] != approved:
        raise ValueError("Executable holdout recipe changed; new freeze and approval required")
    return f


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for arm in dataset.ARMS:
        for condition in dataset.CONDITIONS:
            group = [r for r in rows if r["arm"] == arm and r["condition"] == condition]
            reused = [r["total_ms"] for r in group if r["status"] == "returned"
                      and r["timing"].get("connection") == "reused"]
            result[f"{arm}/{condition}"] = {
                "planned_n": len(group),
                **{status + "_n": sum(r["status"] == status for r in group)
                   for status in ("returned", "invalid", "cancelled", "not_run")},
                **{key: sum(r[key] for r in group) for key in (
                    "correct", "intended_action", "wrong_target", "negative_action", "positive_refusal")},
                "refusal_types": {control: sum(r["refusal_type"] == control for r in group)
                                  for control in ("none", "ambiguous", "need_more_context", "escalate")},
                "reused_n": len(reused), "median_reused_ms": median(reused) if reused else None,
            }
    return result


def contrasts(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if len(rows) != 48 or any(r["status"] != "returned" for r in rows):
        return None
    cases = {r["case_id"] for r in rows}
    if len(cases) != 24 or {(r["case_id"], r["arm"]) for r in rows} != {
        (case, arm) for case in cases for arm in dataset.ARMS
    }:
        return None
    summary = summarize(rows)
    return {condition: {"case_pairs": 6, **{
        key + "_delta": summary[f"contract/{condition}"][key] - summary[f"legacy/{condition}"][key]
        for key in ("correct", "intended_action", "wrong_target", "negative_action", "positive_refusal")
    }} for condition in dataset.CONDITIONS}


async def call_once(
    row: dict[str, Any], payload: dict[str, object], actions: ActionSet,
    expected: dataset.Expected, pool: httpx.AsyncBaseTransport, credential: str,
    policy: BenchmarkModelPolicy, audit_file: TextIO,
) -> bool:
    async def audit(record: ExecutionRecord) -> None:
        await asyncio.to_thread(v1.append_json, audit_file, asdict(record))

    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(),
                          asyncio.Event(), deadline=time.monotonic() + 45,
                          model_policy=policy, audit=audit)
    config = v1.MODELS["jev"]
    probe = v2.TraceProbe()
    route = JevChoiceRoute(config["url"], config["model"], "jev")
    transport = TaskModelTransport(row["trial"], ctx, routes=(route,),
                                   credentials={"jev": credential}, inner=v2.TraceLease(pool, probe))
    client = httpx.AsyncClient(transport=transport, timeout=30, trust_env=False, follow_redirects=False)
    ctx.runtime.own("http-client", client.aclose)
    decision = None
    row["request"] = payload
    try:
        response = await client.post(config["url"], json=payload)
        row["response"] = response.json()
        decision = parse_choice(row["response"], actions, config["model"])
        row["choice"] = decision.candidate_id if decision.choice == "candidate" else decision.choice
        row["status"] = "returned"
    except asyncio.CancelledError:
        row["status"] = "cancelled"
        raise
    except Exception as exc:
        row.update(status="invalid", error_type=type(exc).__name__)
    finally:
        row["total_ms"] = (time.monotonic() - probe.started) * 1000
        row["timing"] = probe.summary()
        row["usage"] = ctx.budget.snapshot()
        row.update(dataset.score(expected, actions, decision, row["status"]))
        await ctx.runtime.aclose()
    if ctx.runtime.audit_failed:
        policy.ledger.stop("audit_failed")
    return bool(ctx.budget.unknown_calls or policy.ledger.snapshot()["stop_reason"])


async def run_replay(output: Path, approved: str, credential: str) -> dict[str, Any]:
    f = load_freeze(output, approved)
    if not credential.strip():
        raise ValueError("Jev credential required")
    for name in ("spend.jsonl", "audit.jsonl", "rows.jsonl", "result.json"):
        if (output / name).exists():
            raise FileExistsError(output / name)
    frozen_cases = {c["id"]: c for c in f["cases"]}
    actions = {}
    labels = {}
    for case_id, case in frozen_cases.items():
        request = case["requests"]["contract"]
        criteria = request["questions"]["next_action"]["criteria"]
        actions[case_id] = TypeAdapter(ActionSet).validate_json(json.dumps({
            "binding": request["state"]["binding"], "reason": "jev_eligible",
            "actions": [value for value in criteria.values() if isinstance(value, dict)],
        }))
        labels[case_id] = dataset.Expected.model_validate_json(json.dumps(case["gold"]))
    rows = [{"case_id": item["case_id"], "arm": item["arm"],
             "condition": frozen_cases[item["case_id"]]["condition"],
             "trial": f"{item['case_id']}-{item['arm']}", "choice": None, "timing": {}, "usage": {},
             **dataset.score(labels[item["case_id"]], actions[item["case_id"]], None, "not_run")}
            for item in f["schedule"]]
    report: dict[str, Any] = {"freeze_sha256": approved, "rows": rows, "completed": False}
    ledger = SpendLedger(SpendLimit(150_000_000, f["nano_usd_limit"]),
                         request_limit=f["request_limit"], journal=output / "spend.jsonl")
    config = f["model"]
    policy = BenchmarkModelPolicy(ledger, (ContextWindowContract(
        config["url"], config["model"],
        TokenAllowance(config["input_ceiling"], config["output_ceiling"],
                       config["input_price"], config["output_price"]),
        "Historical frozen Jev ceilings/prices; see dataset protocol", output_cap_required=False,
    ),))
    pool = None
    written = 0
    cleanup_errors = []
    try:
        with ExitStack() as files:
            audit = files.enter_context((output / "audit.jsonl").open("x"))
            journal = files.enter_context((output / "rows.jsonl").open("x"))
            try:
                pool = httpx.AsyncHTTPTransport(
                    retries=0, trust_env=False, http2=False,
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=1, keepalive_expiry=60))
                for row in rows:
                    ledger.start_trial(row["trial"], SpendLimit(2_000_000, f["nano_usd_limit"]))
                    payload = frozen_cases[row["case_id"]]["requests"][row["arm"]]
                    stop = await call_once(row, payload, actions[row["case_id"]], labels[row["case_id"]],
                                           pool, credential, policy, audit)
                    v1.append_json(journal, row)
                    written += 1
                    if stop:
                        break
                    ledger.finish_trial()
                else:
                    report["completed"] = True
            finally:
                for row in rows[written:]:
                    v1.append_json(journal, row)
    finally:
        if pool is not None:
            try:
                await pool.aclose()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
                ledger.stop("cleanup_failed")
                report["completed"] = False
        report.update(cleanup_errors=cleanup_errors, spend=ledger.snapshot(),
                      summary=summarize(rows), contrasts=contrasts(rows))
        ledger.close()
        with (output / "result.json").open("x") as result_file:
            result_file.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approved-sha256")
    args = parser.parse_args()
    if not args.live:
        if args.approved_sha256:
            parser.error("approval requires --live")
        frozen = prepare(args.output)
        print(json.dumps({"sha256": frozen["sha256"], "request_limit": 48,
                          "max_usd": 0.25, "real_requests": 0}))
    else:
        if not args.approved_sha256:
            parser.error("live requires separately approved executable digest")
        load_freeze(args.output, args.approved_sha256)
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[2] / "core/.env")
        result = asyncio.run(run_replay(args.output, args.approved_sha256,
                                       os.environ.get("TYPESAFE_API_KEY", "")))
        print(json.dumps({"completed": result["completed"], "spend": result["spend"]["batch"],
                          "stop_reason": result["spend"]["stop_reason"]}))
        raise SystemExit(0 if result["completed"] else 1)
