"""M6 item-3/6 analysis: per-task A vs C results + failure taxonomy."""

from __future__ import annotations

import glob
import json
from collections import Counter
from pathlib import Path

ROOT = Path("/tmp")
REPORTS = Path("backend/benchmarks/computer_use/reports/20260924-m6-task-pairs")
TASKS = ["open-settings", "browser-navigate", "local-form", "typing-fidelity",
         "file-ops", "terminal-write", "settings-toggle", "editor-save",
         "links-history", "multi-select-copy", "drag-file", "small-text-code",
         "window-copy"]


def trial_dirs(task: str):
    return sorted((ROOT / f"tank-m6-{task}-20260925-live" / "trials").glob("*/"))


def load_trial(trial_dir: Path):
    key = trial_dir.name
    inner = trial_dir / key
    report = json.loads((inner / "report.json").read_text())["metadata"]
    trace = inner / "trials" / report["outcomes"][0].get("task", key.rsplit("-", 2)[0]) / "1" \
        if False else None
    requests, settles, dispatches, blocked = {}, {}, [], 0
    trace_files = list((inner / "trials").glob("*/1/trace.jsonl"))
    trace = trace_files[0] if trace_files else None
    if trace:
        for line in trace.read_text().splitlines():
            event = json.loads(line)
            kind = event.get("kind")
            if kind == "http_request":
                requests[event["request_id"]] = {
                    "role": "locator" if event.get("grounding_call_id") else "planner"}
            elif kind == "spend_settled":
                record = event.get("record") or {}
                settles[event["request_id"]] = {
                    "in": record.get("input_tokens"), "out": record.get("output_tokens")}
            elif kind == "desktop_dispatch":
                dispatches.append({"name": event.get("name"),
                                   "succeeded": event.get("succeeded")})
            if "input blocked" in line:
                blocked += 1
    planner = sum((r["in"] or 0) + (r["out"] or 0)
                  for rid, r in settles.items()
                  if requests.get(rid, {}).get("role") == "planner")
    locator = sum((r["in"] or 0) + (r["out"] or 0)
                  for rid, r in settles.items()
                  if requests.get(rid, {}).get("role") == "locator")
    return report, {"planner_tokens": planner, "locator_tokens": locator,
                    "requests": len(requests),
                    "locator_requests": sum(1 for r in requests.values()
                                            if r["role"] == "locator"),
                    "dispatches": dispatches, "gate_blocked": blocked}


def classify(report: dict, extra: dict) -> str:
    outcome = report["outcomes"][0]
    task = outcome.get("task", "")
    if outcome.get("success"):
        return "passed"
    stop = outcome.get("stop_reason") or ""
    if stop == "budget":
        return "budget-stop"
    if stop == "timeout":
        return "timeout"
    failed = [d for d in extra["dispatches"] if not d["succeeded"]]
    names = Counter(d["name"] for d in failed)
    if extra["gate_blocked"] >= 2 and failed:
        return "coordinate/out-of-window (gate-blocked clicks)"
    if names.get("launch_app"):
        return "app-launch-failed"
    if outcome.get("cleanup") == "unconfirmed":
        return "cleanup-failed"
    return "task-incomplete (flow/steps exhausted within limits)"


def main() -> None:
    rows = []
    for task in TASKS:
        for trial_dir in trial_dirs(task):
            report, extra = load_trial(trial_dir)
            outcome = report["outcomes"][0]
            rows.append({
                "task": task, "trial": trial_dir.name,
                "variant": report["comparison_contract"]["variant"],
                "passed": outcome.get("success"),
                "stop_reason": outcome.get("stop_reason"),
                "scoring": outcome.get("scoring"),
                "steps": json.loads(json.dumps(outcome)) and None,
                "class": classify(report, extra), **extra,
            })
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "analysis.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(f"{'task':20s} {'A':>6s} {'C':>6s}  {'A tok':>8s} {'C tok':>8s}  dominant failures")
    totals = Counter()
    for task in TASKS:
        items = [r for r in rows if r["task"] == task]
        a = [r for r in items if r["variant"] == "A"]
        c = [r for r in items if r["variant"] == "C"]
        a_pass = sum(1 for r in a if r["passed"])
        c_pass = sum(1 for r in c if r["passed"])
        a_tok = sum(r["planner_tokens"] + r["locator_tokens"] for r in a) // max(1, len(a))
        c_tok = sum(r["planner_tokens"] + r["locator_tokens"] for r in c) // max(1, len(c))
        fails = Counter(r["class"] for r in items if not r["passed"])
        for k, v in fails.items():
            totals[k] += v
        dom = ", ".join(f"{k}×{v}" for k, v in fails.most_common(2)) or "-"
        print(f"{task:20s} {a_pass}/{len(a):<4d} {c_pass}/{len(c):<4d}  {a_tok:8d} {c_tok:8d}  {dom}")
    a_all = [r for r in rows if r["variant"] == "A"]
    c_all = [r for r in rows if r["variant"] == "C"]
    strict_rows = [r for r in rows if r["scoring"] == "strict"]
    print(f"\nstrict only: A {sum(1 for r in strict_rows if r['variant']=='A' and r['passed'])}/"
          f"{sum(1 for r in strict_rows if r['variant']=='A')}  "
          f"C {sum(1 for r in strict_rows if r['variant']=='C' and r['passed'])}/"
          f"{sum(1 for r in strict_rows if r['variant']=='C')}")
    print(f"all rows: A {sum(1 for r in a_all if r['passed'])}/{len(a_all)}  "
          f"C {sum(1 for r in c_all if r['passed'])}/{len(c_all)}")
    print("failure taxonomy:", dict(totals))
    print("tokens total:", sum(r["planner_tokens"] + r["locator_tokens"] for r in rows),
          "| requests:", sum(r["requests"] for r in rows),
          "| gate blocks:", sum(r["gate_blocked"] for r in rows))


if __name__ == "__main__":
    main()
