"""S3 v2: binary abstention, self-contained actions, cold/pooled HTTP diagnostics."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

from benchmarks.computer_use import s3_replay as v1

FIXTURES = Path(__file__).parent / "fixtures/s3-v2/cases.json"
MODES = ("cold", "pooled")


def score(
    gold: dict[str, Any], actions: list[dict[str, Any]], choice: str | None, status: str,
) -> dict[str, Any]:
    action = next((a for a in actions if a["id"] == choice), None)
    valid = status in {"returned", "rule"}
    should_act = gold.get("should_act")
    target_correct = (action["target_ref"] == gold["target_ref"]
                      if action is not None and should_act else None)
    return {
        "candidate_recall": (any(a["target_ref"] == gold["target_ref"] for a in actions)
                             if "target_ref" in gold else None),
        "actionability_correct": valid and (action is not None) == should_act,
        "target_correct": target_correct,
        "decision_correct": bool(valid and (target_correct if should_act else choice == "abstain")),
        "wrong_action": action is not None and (not should_act or not target_correct),
        "false_refusal": valid and should_act is True and choice == "abstain",
    }


class TraceProbe:
    """Store names/timestamps only. httpcore info may contain secrets and is discarded."""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.events: dict[str, float] = {}

    async def trace(self, name: str, info: dict[str, Any]) -> None:
        if name.rsplit(".", 1)[0] in {
            "connection.connect_tcp", "connection.start_tls", "http11.send_request_headers",
            "http11.send_request_body", "http11.receive_response_headers",
            "http11.receive_response_body",
        }:
            self.events[name] = (time.monotonic() - self.started) * 1000

    def summary(self) -> dict[str, Any]:
        def duration(prefix: str) -> float | None:
            start, end = self.events.get(prefix + ".started"), self.events.get(prefix + ".complete")
            return end - start if start is not None and end is not None else None

        headers = self.events.get("http11.receive_response_headers.complete")
        return {
            "connection": ("new" if "connection.connect_tcp.started" in self.events else
                           "reused" if headers is not None else "unknown"),
            "tcp_ms": duration("connection.connect_tcp"),
            "tls_ms": duration("connection.start_tls"),
            "send_headers_ms": duration("http11.send_request_headers"),
            "send_body_ms": duration("http11.send_request_body"),
            "headers_wait_ms": duration("http11.receive_response_headers"),
            "headers_complete_ms": headers,
            "body_receive_ms": duration("http11.receive_response_body"),
            "body_complete_ms": self.events.get("http11.receive_response_body.complete"),
            "events_ms": dict(self.events),
        }


class TraceLease(httpx.AsyncBaseTransport):
    """Each task borrows the experiment's pool; task shutdown never closes the pool."""

    def __init__(self, pool: httpx.AsyncBaseTransport, probe: TraceProbe) -> None:
        self.pool, self.probe = pool, probe

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.extensions["trace"] = self.probe.trace
        return await self.pool.handle_async_request(request)

    async def aclose(self) -> None:
        pass


def question(public: dict[str, Any]) -> dict[str, Any]:
    elements = {e["ref"]: e for e in public["snapshot"]["elements"]}
    options = {}
    for action in public["actions"]["actions"]:
        element = elements[action["target_ref"]]
        options[action["id"]] = {
            "operation": action["operation"], "role": element["role"], "label": element["label"],
            "value": action["value"], "ancestors": element["ancestors"],
        }
    options["abstain"] = "No uniquely justified action can be selected from the supplied evidence."
    return {
        "state": {"objective": public["goal"]["objective"], "inputs": public["goal"]["inputs"],
                  "facts": public["snapshot"]["facts"]},
        "instructions": "Choose one uniquely justified action or abstain. Use only supplied evidence. "
                        "Do not plan extra steps, open another view, or gather missing evidence. "
                        "Missing authorized identity, missing visual data or indistinguishable "
                        "targets requires abstention.",
        "criteria": options,
    }


def freeze_inputs() -> dict[str, Any]:
    import hashlib
    from importlib.metadata import version

    source = json.loads(FIXTURES.read_text())
    cases = []
    for item in source["cases"]:
        public = v1.public_case(item)
        cases.append({key: value for key, value in item.items() if key not in {"goal", "snapshot"}}
                     | {"public": public, "question": question(public)})
    hashes = v1.code_hashes() | {Path(__file__).name: hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    data = {"revision": source["revision"], "cases": cases, "models": v1.MODELS,
            "purpose": "paired diagnostics on revised known scenarios; not a fresh blind holdout",
            "fit_thresholds": False,
            "modes": MODES, "nano_usd_limit": 250_000_000,
            "request_limit": sum(c["public"]["actions"]["reason"] == "jev_eligible"
                                 and not c["public"]["actions"]["truncated"] for c in cases) * 4,
            "code_hashes": hashes, "dataset_sha256": hashlib.sha256(FIXTURES.read_bytes()).hexdigest(),
            "httpx": version("httpx"), "httpcore": version("httpcore"),
            "http2": False, "keepalive_expiry_seconds": 60, "warmup_requests": 0}
    data = json.loads(json.dumps(data))
    data["sha256"] = v1.digest(data)
    return data


def prepare(output: Path) -> dict[str, Any]:
    data = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    data = json.loads((output / "freeze.json").read_text())
    if data != freeze_inputs() or data["sha256"] != approved:
        raise ValueError("Frozen v2 inputs, implementation or HTTP versions changed")
    return data


def parse_response(arm: str, data: dict[str, Any], options: dict[str, Any]) -> tuple[str, float | None]:
    if arm == "qwen":
        return v1.parse_qwen(data, options, v1.MODELS[arm]["model"]), None
    import math
    from benchmarks.computer_use.legacy_json_model import probability

    answers = data.get("answers")
    if (data.get("model") != v1.MODELS[arm]["model"] or not isinstance(answers, dict)
            or set(answers) != {"next_action"} or not isinstance(answers["next_action"], dict)):
        raise ValueError("invalid Jev response")
    answer = answers["next_action"]
    choice, probabilities = answer.get("choice"), answer.get("probabilities")
    if (answer.get("type") != "choice" or not isinstance(choice, str) or choice not in options
            or not probability(answer.get("confidence")) or not isinstance(probabilities, dict)
            or set(probabilities) != set(options)
            or not all(probability(p) for p in probabilities.values())
            or not math.isclose(sum(probabilities.values()), 1, abs_tol=0.02)
            or probabilities[choice] != max(probabilities.values())):
        raise ValueError("invalid Jev choice")
    return choice, float(probabilities["abstain"])


def payload(arm: str, q: dict[str, Any]) -> dict[str, Any]:
    if arm == "jev":
        return {"model": v1.MODELS[arm]["model"], "state": q["state"], "questions": {
            "next_action": {"type": "choice", "instructions": q["instructions"],
                            "criteria": q["criteria"]},
        }}
    return {"model": v1.MODELS[arm]["model"], "max_tokens": 128, "temperature": 0,
            "enable_thinking": False, "messages": [
                {"role": "system", "content": 'Return only JSON {"choice":"option id"}. '
                                                'Choose an offered action or abstain; execute nothing.'},
                {"role": "user", "content": json.dumps(q, ensure_ascii=False, sort_keys=True)},
            ]}


async def call_once(
    case: dict[str, Any], row: dict[str, Any], pool: httpx.AsyncBaseTransport,
    credential: str, policy: Any, audit_file: Any,
) -> bool:
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.agents.task_runtime import ExecutionRecord
    from benchmarks.computer_use.legacy_json_model import TaskJSONModel
    from dataclasses import asdict

    async def audit(record: ExecutionRecord) -> None:
        await asyncio.to_thread(v1.append_json, audit_file, asdict(record))

    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(),
                          asyncio.Event(), deadline=time.monotonic() + 45,
                          model_policy=policy, audit=audit)
    arm = row["arm"]
    config = v1.MODELS[arm]
    probe = TraceProbe()
    client = TaskJSONModel(row["trial"], ctx, config["url"], config["model"], credential,
                          transport=TraceLease(pool, probe))
    ctx.runtime.own("raw-replay", client.aclose)
    row["request"] = payload(arm, case["question"])
    try:
        data = await client.request(row["request"])
        row["response"] = data
        row["choice"], row["p_abstain"] = parse_response(arm, data, case["question"]["criteria"])
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
        await ctx.runtime.aclose()
    if ctx.runtime.audit_failed:
        policy.ledger.stop("audit_failed")
    return bool(ctx.budget.unknown_calls or policy.ledger.snapshot()["stop_reason"])


async def run_replay(output: Path, approved: str, credentials: dict[str, str]) -> dict[str, Any]:
    from contextlib import ExitStack
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance

    f = load_freeze(output, approved)
    if set(credentials) != {"jev", "qwen"} or not all(v.strip() for v in credentials.values()):
        raise ValueError("Both credentials required")
    ledger = SpendLedger(SpendLimit(100_000_000, f["nano_usd_limit"]),
                         request_limit=f["request_limit"], journal=output / "spend.jsonl")
    policy = BenchmarkModelPolicy(ledger, tuple(ContextWindowContract(
        c["url"], c["model"], TokenAllowance(c["input_ceiling"], c["output_ceiling"],
                                          c["input_price"], c["output_price"]),
        "v1 official ceilings/upper prices reused; no new price assumption",
        output_cap_required=arm == "qwen",
    ) for arm, c in v1.MODELS.items()))
    pools: dict[str, httpx.AsyncBaseTransport] = {}
    rows: list[dict[str, Any]] = []
    report: dict[str, Any] = {"freeze_sha256": approved, "rows": rows, "completed": False}
    stop = False
    try:
        with ExitStack() as files:
            audit = files.enter_context((output / "audit.jsonl").open("x"))
            journal = files.enter_context((output / "rows.jsonl").open("x"))
            for index, case in enumerate(f["cases"]):
                modes = MODES if index % 2 == 0 else tuple(reversed(MODES))
                arms = ("rules", "jev", "qwen") if index % 2 == 0 else ("rules", "qwen", "jev")
                actions = case["public"]["actions"]
                for mode in modes:
                    for arm in arms:
                        row = {"case_id": case["id"], "category": case["category"],
                               "split": case["split"], "mode": mode, "arm": arm,
                               "trial": f"{case['id']}-{mode}-{arm}",
                               "public_sha256": v1.digest(case["question"]),
                               "model_eligible": actions["reason"] == "jev_eligible" and not actions["truncated"],
                               "status": "not_run", "choice": None, "usage": {}, "timing": {}}
                        if actions["reason"] == "rules_unique":
                            row.update(status="rule", choice=actions["actions"][0]["id"])
                        elif not row["model_eligible"]:
                            row.update(status="host_blocked", reason=actions["reason"])
                        elif arm == "rules":
                            row.update(status="rule", choice="abstain")
                        elif not stop:
                            ledger.start_trial(row["trial"], SpendLimit(2_000_000, f["nano_usd_limit"]))
                            setup = time.monotonic()
                            pool = pools.get(arm) if mode == "pooled" else None
                            if pool is None:
                                pool = httpx.AsyncHTTPTransport(
                                    retries=0, trust_env=False, http2=False,
                                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=1,
                                                       keepalive_expiry=60),
                                )
                                if mode == "pooled":
                                    pools[arm] = pool
                            row["pool_setup_ms"] = (time.monotonic() - setup) * 1000
                            try:
                                try:
                                    stop = await call_once(case, row, pool, credentials[arm], policy, audit)
                                finally:
                                    if mode == "cold":
                                        try:
                                            await pool.aclose()
                                        except Exception:
                                            row["cleanup"] = "unknown"
                                            ledger.stop("cleanup_failed")
                                            stop = True
                            except BaseException:
                                row.update(score(case["gold"], actions["actions"],
                                                 row["choice"], row["status"]))
                                rows.append(row)
                                v1.append_json(journal, row)
                                raise
                            if not stop:
                                ledger.finish_trial()
                        row.update(score(case["gold"], actions["actions"], row["choice"], row["status"]))
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
        report.update(cleanup_errors=cleanup_errors, spend=ledger.snapshot(), summary=summarize(rows))
        ledger.close()
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from statistics import median

    def middle(values: list[float]) -> float | None:
        return median(values) if values else None

    result = {}
    for split in ("calibration", "holdout"):
        for mode in MODES:
            for arm in ("rules", "jev", "qwen"):
                group = [r for r in rows if (r["split"], r["mode"], r["arm"]) == (split, mode, arm)]
                eligible = [r for r in group if r["model_eligible"]]
                returned = [r for r in eligible if r["status"] == "returned"]
                reused = [r for r in returned if r["timing"]["connection"] == "reused"]
                result[f"{split}/{mode}/{arm}"] = {
                    "scheduled_n": len(group), "eligible_n": len(eligible),
                    "host_blocked_n": sum(r["status"] == "host_blocked" for r in group),
                    "not_run_n": sum(r["status"] == "not_run" for r in eligible),
                    "invalid_n": sum(r["status"] == "invalid" for r in eligible),
                    "decision_correct_n": sum(r["decision_correct"] is True for r in eligible),
                    "actionability_correct_n": sum(r["actionability_correct"] is True for r in eligible),
                    "target_correct_n": sum(r["target_correct"] is True for r in eligible),
                    "wrong_action_n": sum(r["wrong_action"] for r in eligible),
                    "false_refusal_n": sum(r["false_refusal"] for r in eligible),
                    "returned_n": len(returned), "reused_n": len(reused),
                    "median_total_ms": middle([r["total_ms"] for r in returned]),
                    "median_reused_total_ms": middle([r["total_ms"] for r in reused]),
                    "phases": {field: {
                        "n": sum(r["timing"].get(field) is not None for r in returned),
                        "median_ms": middle([r["timing"][field] for r in returned
                                             if r["timing"].get(field) is not None]),
                    } for field in ("tcp_ms", "tls_ms", "send_headers_ms", "send_body_ms",
                                    "headers_wait_ms", "headers_complete_ms", "body_receive_ms",
                                    "body_complete_ms")},
                }
    return result


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
        print(json.dumps({"sha256": f["sha256"], "cases": len(f["cases"]),
                          "request_limit": f["request_limit"], "max_usd": 0.25, "real_requests": 0}))
    else:
        if not args.approved_sha256:
            parser.error("live requires separately approved v2 digest")
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
