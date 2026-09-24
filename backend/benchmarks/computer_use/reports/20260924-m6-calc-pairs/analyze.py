"""M6 calc batch analysis: per-request planner/locator usage + failure classes."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path("/tmp/tank-m6-calc-20260924-live/trials")
OUT = Path("backend/benchmarks/computer_use/reports/20260924-m6-calc-pairs")

ARM_ORDER = ["m6-pair-1-a", "m6-pair-1-b-combined", "m6-pair-1-c", "m6-pair-1-d",
             "m6-pair-2-b-combined", "m6-pair-2-c", "m6-pair-2-d", "m6-pair-2-a",
             "m6-pair-3-c", "m6-pair-3-d", "m6-pair-3-a", "m6-pair-3-b-combined"]


def classify(report: dict, gate_blocks: int, dispatches: list[dict]) -> str:
    """One primary failure class per failed trial (business vs coordinate vs flow)."""
    outcome = report["outcomes"][0]
    display = outcome.get("assessment", {}).get("display", {}) or {}
    expression = display.get("expression")
    result = display.get("result")
    failed_clicks = sum(1 for d in dispatches if not d["succeeded"])
    if outcome.get("success"):
        return "passed"
    if failed_clicks and not expression and result in (None, "0"):
        return "coordinate/locate-error (clicks failed, no input landed)"
    if expression == "7×8" and result != "56":
        return "flow-incomplete (expression entered, = not verified)"
    if result == "56" and not expression:
        return "input-path (result without expression line: paste path)"
    if result in ("78",):
        return "input-semantics (operator key ignored/missing)"
    if result in ("7", "7×", "7×8", "0"):
        return "flow-incomplete (partial input, steps exhausted)"
    return "unclassified"


def main() -> None:
    rows = []
    for arm in ARM_ORDER:
        trial_dir = next((ROOT / arm / arm / "trials" / "calc-open").glob("1"))
        report = json.loads((trial_dir.parents[2] / "report.json").read_text())["metadata"]
        outcome = report["outcomes"][0]
        requests, settles, dispatches, gate_text = {}, {}, [], 0
        outputs = []
        for line in (trial_dir / "trace.jsonl").read_text().splitlines():
            event = json.loads(line)
            kind = event.get("kind")
            if kind == "http_request":
                requests[event["request_id"]] = {
                    "role": "locator" if event.get("grounding_call_id") else "planner",
                    "model": event.get("model"),
                    "images": len(event.get("image_sha256") or []),
                }
            elif kind == "spend_settled":
                record = event.get("record") or {}
                settles[event["request_id"]] = {
                    "in": record.get("input_tokens"), "out": record.get("output_tokens"),
                }
            elif kind == "desktop_dispatch":
                dispatches.append({"name": event.get("name"),
                                   "succeeded": event.get("succeeded"),
                                   "in_batch": event.get("in_batch")})
            if "input blocked" in line:
                gate_text += 1
        per_request = []
        for rid, meta in requests.items():
            usage = settles.get(rid, {})
            per_request.append({"role": meta["role"], "model": meta["model"],
                                "images": meta["images"], **usage})
        planner_in = sum(r["in"] or 0 for r in per_request if r["role"] == "planner")
        planner_out = sum(r["out"] or 0 for r in per_request if r["role"] == "planner")
        locator_in = sum(r["in"] or 0 for r in per_request if r["role"] == "locator")
        locator_out = sum(r["out"] or 0 for r in per_request if r["role"] == "locator")
        rows.append({
            "trial": arm, "variant": report["comparison_contract"]["variant"],
            "passed": outcome.get("success"),
            "stop_reason": outcome.get("stop_reason"),
            "display": outcome.get("assessment", {}).get("display"),
            "input_trace_complete": outcome.get("assessment", {}).get("input_trace_complete"),
            "requests": len(per_request),
            "planner_requests": sum(1 for r in per_request if r["role"] == "planner"),
            "locator_requests": sum(1 for r in per_request if r["role"] == "locator"),
            "planner_tokens": planner_in + planner_out,
            "locator_tokens": locator_in + locator_out,
            "total_tokens": planner_in + planner_out + locator_in + locator_out,
            "dispatches": dispatches,
            "gate_blocked": gate_text,
            "failure_class": classify(report, gate_text, dispatches),
            "per_request": per_request,
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    print(f"{'trial':24s} {'res':4s} {'reqs':>4s} {'loc':>3s} {'plan_tok':>8s} {'loc_tok':>7s}  class")
    for row in rows:
        print(f"{row['trial']:24s} {'PASS' if row['passed'] else 'FAIL':4s} "
              f"{row['requests']:4d} {row['locator_requests']:3d} "
              f"{row['planner_tokens']:8d} {row['locator_tokens']:7d}  {row['failure_class']}")
    by_arm = {}
    for row in rows:
        by_arm.setdefault(row["variant"], []).append(row)
    print()
    for arm, items in by_arm.items():
        passed = sum(1 for i in items if i["passed"])
        tokens = sum(i["total_tokens"] for i in items)
        print(f"{arm:14s} {passed}/{len(items)}  avg_tokens={tokens // len(items)}  "
              f"classes={dict(Counter(i['failure_class'] for i in items))}")
    print(f"\ntotal tokens: {sum(r['total_tokens'] for r in rows)}; "
          f"total requests: {sum(r['requests'] for r in rows)}; "
          f"gate blocks: {sum(r['gate_blocked'] for r in rows)}")


if __name__ == "__main__":
    main()
