"""Offline-first 2x2 refusal diagnostics; v1/v2 evidence is never rewritten."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from benchmarks.computer_use import s3_replay as v1
from benchmarks.computer_use import s3_replay_v2 as v2

CONDITIONS = Path(__file__).parent / "fixtures/s3-v3/conditions.json"
VARIANTS = ("legacy", "broad_minimal", "scoped_minimal", "broad_enriched", "scoped_enriched")
CONTRASTS = {
    "host_contract": ("broad_minimal", "legacy"),
    "scoped_under_minimal": ("scoped_minimal", "broad_minimal"),
    "scoped_under_enriched": ("scoped_enriched", "broad_enriched"),
    "facts_under_broad": ("broad_enriched", "broad_minimal"),
    "facts_under_scoped": ("scoped_enriched", "scoped_minimal"),
}
HOST_CONTRACT = {
    "proposal_scope_authorized": True,
    "scope": "current synthetic task only",
    "output_effect": "proposal_only",
    "meaning": "Approval permits a proposal; it does not identify the correct target or supply business facts.",
}
SCOPED = (
    "The host has checked proposal authorization; do not re-evaluate that grant. "
    "It does not establish business identity or make any candidate correct. "
    "Match the objective and supplied facts to one uniquely justified offered action, or abstain. "
    "Explicitly missing target identity, unavailable required visual evidence, or indistinguishable "
    "targets requires abstention. Do not invent external requirements unrelated to this mapping. "
    "Do not plan extra steps, open another view, or gather missing evidence."
)


def reject_oracle_markers(value: object) -> None:
    if isinstance(value, dict):
        if {"gold", "should_act", "target_ref", "candidate_id"} & value.keys():
            raise ValueError("business evidence contains oracle markers")
        for child in value.values():
            reject_oracle_markers(child)
    elif isinstance(value, list):
        for child in value:
            reject_oracle_markers(child)


def questions(public: dict[str, Any], business: dict[str, Any]) -> dict[str, Any]:
    reject_oracle_markers(business)
    base = v2.question(public)
    result = {"legacy": copy.deepcopy(base)}
    base["state"]["host_contract"] = copy.deepcopy(HOST_CONTRACT)
    for variant in VARIANTS[1:]:
        q = copy.deepcopy(base)
        if variant.startswith("scoped"):
            q["instructions"] = SCOPED
        if variant.endswith("enriched"):
            q["state"]["business_state"] = copy.deepcopy(business)
        result[variant] = q
    return result


def freeze_inputs() -> dict[str, Any]:
    base = v2.freeze_inputs()
    source = json.loads(CONDITIONS.read_text())
    ids = [c["id"] for c in source["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate diagnostic scenario")
    by_id = {c["id"]: c for c in base["cases"]}
    cases = []
    for item in source["cases"]:
        c = copy.deepcopy(by_id[item["id"]])
        if c["public"]["actions"]["reason"] != "jev_eligible" or c["public"]["actions"]["truncated"]:
            raise ValueError("V3 requires model-eligible diagnostic scenarios")
        c.pop("question")
        c["questions"] = questions(c["public"], item["business_state"])
        cases.append(c)
    f = {"revision": source["revision"], "base_v2_digest": base["sha256"],
         "cases": cases, "variants": VARIANTS, "models": base["models"],
         "contrasts": CONTRASTS,
         "httpx": base["httpx"], "httpcore": base["httpcore"],
         "http2": False, "keepalive_expiry_seconds": 60, "warmup_requests": 0,
         "request_limit": len(cases) * len(VARIANTS) * 2, "nano_usd_limit": 250_000_000,
         "conditions_sha256": hashlib.sha256(CONDITIONS.read_bytes()).hexdigest(),
         "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         "fit_thresholds": False,
         "purpose": "known selected scenarios; prompt x business-evidence diagnostic, not blind validation"}
    f = json.loads(json.dumps(f))
    f["sha256"] = v1.digest(f)
    return f


def prepare(output: Path) -> dict[str, Any]:
    f = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(f, ensure_ascii=False, indent=2))
    return f


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    f = json.loads((output / "freeze.json").read_text())
    if f != freeze_inputs() or f["sha256"] != approved:
        raise ValueError("Frozen v3 recipe, evidence or implementation changed")
    return f


def score(case: dict[str, Any], variant: str, choice: str | None, status: str) -> dict[str, Any]:
    valid = status == "returned"
    positive = case["gold"]["should_act"]
    action = next((a for a in case["public"]["actions"]["actions"] if a["id"] == choice), None)
    abstain = valid and choice == "abstain"
    matched = valid and action is not None and action["target_ref"] == case["gold"].get("target_ref")
    return {
        "intended_positive": positive,
        "positive_action": positive and matched,
        "positive_abstain": positive and abstain,
        "wrong_target": valid and positive and action is not None and not matched,
        "negative_action": valid and not positive and action is not None,
        "negative_abstain": not positive and abstain,
        "enriched_positive_refusal": positive and variant.endswith("enriched") and abstain,
        "evidence_acceptable": bool(valid and (
            (matched or (abstain and not variant.endswith("enriched"))) if positive else abstain
        )),
    }


def schedule(index: int) -> list[tuple[str, str]]:
    shift = index % len(VARIANTS)
    variants = VARIANTS[shift:] + VARIANTS[:shift]
    return [(variant, arm) for variant in variants
            for arm in (("jev", "qwen") if (index + VARIANTS.index(variant)) % 2 == 0
                        else ("qwen", "jev"))]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from statistics import median

    result = {}
    for variant in VARIANTS:
        for arm in ("jev", "qwen"):
            group = [r for r in rows if r["variant"] == variant and r["arm"] == arm]
            reused = [r for r in group if r["status"] == "returned"
                      and r["timing"]["connection"] == "reused"]
            result[f"{variant}/{arm}"] = {
                "planned_n": len(group), "positive_n": sum(r["intended_positive"] for r in group),
                "negative_n": sum(not r["intended_positive"] for r in group),
                **{key: sum(r[key] for r in group) for key in (
                    "positive_action", "positive_abstain", "wrong_target", "negative_action",
                    "negative_abstain", "enriched_positive_refusal", "evidence_acceptable",
                )},
                "returned_n": sum(r["status"] == "returned" for r in group),
                "invalid_n": sum(r["status"] == "invalid" for r in group),
                "not_run_n": sum(r["status"] == "not_run" for r in group),
                "reused_n": len(reused),
                "median_reused_ms": median(r["total_ms"] for r in reused) if reused else None,
            }
    return result


def contrasts(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows or any(r["status"] != "returned" for r in rows):
        return None
    cases = {r["case_id"] for r in rows}
    keys = {(r["case_id"], r["arm"], r["variant"]) for r in rows}
    expected = {(case, arm, variant) for case in cases
                for arm in ("jev", "qwen") for variant in VARIANTS}
    if keys != expected or len(rows) != len(keys):
        return None
    result = {}
    for arm in ("jev", "qwen"):
        totals = {variant: {metric: sum(int(r[metric]) for r in rows
                                       if r["arm"] == arm and r["variant"] == variant)
                            for metric in ("positive_action", "negative_action", "wrong_target")}
                  for variant in VARIANTS}
        result[arm] = {name: {"case_pairs": len(cases), **{
            metric + "_delta": totals[after][metric] - totals[before][metric]
            for metric in totals[after]
        }} for name, (after, before) in CONTRASTS.items()}
        result[arm]["interaction"] = {"case_pairs": len(cases), **{
            metric + "_delta": totals["scoped_enriched"][metric] - totals["scoped_minimal"][metric]
            - totals["broad_enriched"][metric] + totals["broad_minimal"][metric]
            for metric in totals["scoped_enriched"]
        }}
    return result


async def run_replay(output: Path, approved: str, credentials: dict[str, str]) -> dict[str, Any]:
    from contextlib import ExitStack
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance

    f = load_freeze(output, approved)
    if set(credentials) != {"jev", "qwen"} or not all(v.strip() for v in credentials.values()):
        raise ValueError("Both model credentials required")
    ledger = SpendLedger(SpendLimit(150_000_000, f["nano_usd_limit"]),
                         request_limit=f["request_limit"], journal=output / "spend.jsonl")
    policy = BenchmarkModelPolicy(ledger, tuple(ContextWindowContract(
        c["url"], c["model"], TokenAllowance(c["input_ceiling"], c["output_ceiling"],
                                          c["input_price"], c["output_price"]),
        "Previously frozen official ceilings and conservative prices", output_cap_required=arm == "qwen",
    ) for arm, c in f["models"].items()))
    pools: dict[str, httpx.AsyncBaseTransport] = {}
    rows: list[dict[str, Any]] = []
    report: dict[str, Any] = {"freeze_sha256": approved, "rows": rows, "completed": False}
    stop = False
    try:
        with ExitStack() as files:
            audit = files.enter_context((output / "audit.jsonl").open("x"))
            journal = files.enter_context((output / "rows.jsonl").open("x"))
            for index, case in enumerate(f["cases"]):
                for variant, arm in schedule(index):
                    row = {"case_id": case["id"], "variant": variant, "arm": arm,
                           "trial": f"{case['id']}-{variant}-{arm}",
                           "public_sha256": v1.digest(case["questions"][variant]),
                           "status": "not_run", "choice": None, "usage": {}, "timing": {}}
                    if not stop:
                        ledger.start_trial(row["trial"], SpendLimit(2_000_000, f["nano_usd_limit"]))
                        if arm not in pools:
                            pools[arm] = httpx.AsyncHTTPTransport(
                                retries=0, trust_env=False, http2=False,
                                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1,
                                                   keepalive_expiry=60),
                            )
                        try:
                            stop = await v2.call_once({"question": case["questions"][variant]},
                                                      row, pools[arm], credentials[arm], policy, audit)
                        except BaseException:
                            row.update(score(case, variant, row["choice"], row["status"]))
                            rows.append(row)
                            v1.append_json(journal, row)
                            raise
                        if not stop:
                            ledger.finish_trial()
                    row.update(score(case, variant, row["choice"], row["status"]))
                    rows.append(row)
                    v1.append_json(journal, row)
            report["completed"] = not stop
    finally:
        cleanup_errors = []
        for pool in pools.values():
            try:
                await pool.aclose()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
                ledger.stop("cleanup_failed")
                report["completed"] = False
        report.update(cleanup_errors=cleanup_errors, spend=ledger.snapshot(),
                      summary=summarize(rows), contrasts=contrasts(rows))
        ledger.close()
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
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
        f = prepare(args.output)
        print(json.dumps({"sha256": f["sha256"], "request_limit": f["request_limit"],
                          "max_usd": 0.25, "real_requests": 0}))
    else:
        if not args.approved_sha256:
            parser.error("live requires separately approved v3 digest")
        load_freeze(args.output, args.approved_sha256)
        from dotenv import load_dotenv
        from tank_backend.config.app_config import AppConfig

        backend = Path(__file__).resolve().parents[2]
        load_dotenv(backend / "core/.env")
        profile = AppConfig.load(backend / "core/config.yaml").llm_profiles["computer_use"]
        if (profile.model != v1.MODELS["qwen"]["model"]
                or profile.base_url.rstrip("/") + "/chat/completions" != v1.MODELS["qwen"]["url"]):
            raise ValueError("Comparison profile differs from frozen recipe")
        result = asyncio.run(run_replay(args.output, args.approved_sha256, {
            "jev": os.environ.get("TYPESAFE_API_KEY", ""), "qwen": profile.api_key,
        }))
        print(json.dumps({"completed": result["completed"], "spend": result["spend"]["batch"],
                          "stop_reason": result["spend"]["stop_reason"]}))
        raise SystemExit(0 if result["completed"] else 1)
