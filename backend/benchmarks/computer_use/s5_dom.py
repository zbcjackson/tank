"""S5 DOM paired pilot: current-host H vs J on workflow fixtures.

Same task family as the S3 strategy pilot, re-measured with the S4-era host
(semantic history, compact view, dynamic focus) and the text Advisor enabled
on both arms. Descriptive policy evidence only, never production adoption.
"""

from __future__ import annotations

from . import call_metrics
from .call_metrics import count_attempts

from tank_backend.llm.decision_profile import DecisionModelProfile

import asyncio
import hashlib
import inspect
import json
import time
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any, TextIO, cast

from tank_backend.llm.model_data import ModelRequest
from agent_computer_use import (
    action_builder,
    advisor,
    agent,
    contracts,
    controller,
    factory,
    jev,
    model_selector,
    model_view,
)
from agent_computer_use.channels import dom
from tank_backend.agents import subagent, task_runtime
from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentContext,
    SubAgentRequest,
)
from tank_backend.agents.task_runtime import ExecutionRecord
from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
from tank_backend.benchmarks.spend_http import ContextWindowContract
from tank_backend.benchmarks.spend_ledger import (
    SpendLedger,
    SpendLimit,
    SpendLimitExceeded,
    SpendSnapshot,
    TokenAllowance,
)
from tank_backend.llm import task_model
from tank_backend.llm.profile import LLMProfile

from benchmarks.computer_use import s3_replay as v1
from benchmarks.computer_use import s3_strategy

DATA = s3_strategy.DATA
MODELS = s3_strategy.MODELS
ARMS = ("H", "J")
ADVISOR_CALL_LIMIT = 4


def arm_config(arm: str) -> dict[str, Any]:
    """Both arms share the channel, Advisor and candidate policy; only the
    selector differs, keeping H vs J a single-variable comparison."""
    return {"selector": "llm" if arm == "H" else "jev-fallback", "advisor": "llm"}


def freeze_inputs() -> dict[str, Any]:
    cases = json.loads(DATA.read_text())
    if len(cases) != 8 or len({c["id"] for c in cases}) != 8:
        raise ValueError("Expected eight unique workflow slices")
    for case in cases:
        contracts.GoalContract.from_input(case["goal"])
    sources = v1.code_hashes()
    for module in (
        action_builder,
        advisor,
        agent,
        contracts,
        controller,
        factory,
        jev,
        model_selector,
        model_view,
        dom,
        subagent,
        task_runtime,
        task_model,
        s3_strategy,
        call_metrics,
    ):
        path = Path(inspect.getfile(module))
        sources[str(path.relative_to(Path(__file__).resolve().parents[2]))] = (
            hashlib.sha256(path.read_bytes()).hexdigest()
        )
    sources[Path(__file__).name] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    sources["cases.json"] = hashlib.sha256(DATA.read_bytes()).hexdigest()
    request_limit = sum(
        3 * (2 * (case["max_decisions"] + ADVISOR_CALL_LIMIT) + case["max_decisions"])
        for case in cases
    )
    f = {
        "revision": "s5-dom-1",
        "cases": cases,
        "arms": list(ARMS),
        "arm_configs": {arm: arm_config(arm) for arm in ARMS},
        "models": MODELS,
        "advisor_call_limit": ADVISOR_CALL_LIMIT,
        "schedule": [
            {"case_id": c["id"], "repeat": repeat, "arm": arm}
            for repeat in range(3)
            for index, c in enumerate(cases)
            for arm in (ARMS if (repeat + index) % 2 == 0 else ARMS[::-1])
        ],
        "request_limit": request_limit,
        "nano_usd_limit": 300_000_000,
        "source_sha256": sources,
        "f_parameters": {"temperature": 0, "max_tokens": 128, "enable_thinking": False},
        "lifecycle": "fresh isolated browser and lazy task-owned clients per trial; no warmups/retries",
        "playwright": version("playwright"),
        "httpx": version("httpx"),
        "httpx2": version("httpx2"),
        "typesafe-sdk": version("typesafe-sdk"),
        "httpcore": version("httpcore"),
        "scope": (
            "S3 workflow fixtures with the current host and the text Advisor on "
            "both arms; supplied structured goals; policy evidence only, no "
            "production-adoption claim"
        ),
        "decision_rule": {
            "minimum_gain": 0.10,
            "minimum_selector_f_avoided": 1,
            "success_regression_allowed": 0,
            "unexpected_actions_allowed": 0,
            "all_predeclared_outcomes_required": True,
            "benefit": (
                "time improves >=10% without cost regression OR cost improves "
                ">=10% without time regression"
            ),
            "interpretation": (
                "descriptive paired pilot of the Jev-first policy on the "
                "current host; adoption requires a separately frozen "
                "confirmatory experiment"
            ),
        },
        "stop_policy": "operational failure stops; known semantic errors on fully observed disposable fixtures are recorded and continue",
    }
    f["sha256"] = v1.digest(f)
    return f


def prepare(output: Path) -> dict[str, Any]:
    f = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(
        json.dumps(f, ensure_ascii=False, indent=2) + "\n"
    )
    return f


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    f = freeze_inputs()
    if json.loads((output / "freeze.json").read_text()) != f or f["sha256"] != approved:
        raise ValueError("S5 DOM recipe changed; freeze and approve again")
    return f


class Policy(BenchmarkModelPolicy):
    def __init__(self, ledger: SpendLedger, arm: str, decisions: int) -> None:
        super().__init__(
            ledger,
            tuple(
                ContextWindowContract(
                    m["url"],
                    m["model"],
                    TokenAllowance(
                        m["input_ceiling"],
                        m["output_ceiling"],
                        m["input_price"],
                        m["output_price"],
                    ),
                    "Historical frozen conservative contracts",
                    output_cap_required=name == "f",
                )
                for name, m in MODELS.items()
            ),
        )
        self.limits = {
            "jev": decisions * int(arm == "J"),
            "f": decisions + ADVISOR_CALL_LIMIT,
        }
        self.counts: Counter[str] = Counter()

    def reserve(self, call_id: str, request: ModelRequest) -> None:
        name = next(
            (n for n, m in MODELS.items() if m["url"] == str(request.url)), "unknown"
        )
        if self.counts[name] >= self.limits.get(name, 0):
            self.ledger.stop("trial_call_limit")
            raise SpendLimitExceeded("trial_call_limit")
        super().reserve(call_id, request)
        self.counts[name] += 1


async def run_trial(
    case: dict[str, Any],
    row: dict[str, Any],
    url: str,
    credentials: dict[str, str],
    ledger: SpendLedger,
    audit_file: TextIO,
) -> None:
    started = time.monotonic()
    instance = factory.create_subagent(
        {"browser": {"scope": "strategy", "url": url}, **arm_config(row["arm"])}
    )
    browser = cast(dom.ManagedChromiumChannel, instance.controller.source)
    capture, events = s3_strategy.Capture(), s3_strategy.Events()

    async def audit(record: ExecutionRecord) -> None:
        await asyncio.to_thread(v1.append_json, audit_file, asdict(record))

    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop", "network"})),
        SubAgentBudget(),
        asyncio.Event(),
        deadline=time.monotonic() + 60,
        model_policy=Policy(ledger, row["arm"], case["max_decisions"]),
        model_capture=capture,
        observer=events,
        audit=audit,
        max_actions=2,
        max_observations=5,
    )
    row["status"] = "started"
    try:
        f = MODELS["f"]
        ctx.runtime.configure_model(
            row["trial"],
            LLMProfile(
                "f",
                credentials["f"],
                f["model"],
                f["url"].removesuffix("/chat/completions"),
                temperature=0,
                max_tokens=128,
                extra_body={"enable_thinking": False},
            ),
        )
        if row["arm"] == "J":
            j = MODELS["jev"]
            ctx.runtime.configure_decision_model(
                row["trial"],
                DecisionModelProfile(j["url"], j["model"], "jev"),
                credential=credentials["jev"],
            )
        async for event in instance.run(
            SubAgentRequest("bounded workflow", "", row["trial"], case["goal"]), ctx
        ):
            if "task_result" in event.metadata:
                row["result"] = event.metadata["task_result"]
        if browser.page is not None:
            row["page_events"] = await browser.page.evaluate("window.events")
            row["page_result"] = await browser.page.get_by_role(
                "status", name="Result", exact=True
            ).text_content()
        if browser.previous is not None:
            row["last_snapshot"] = contracts.snapshot_json(browser.previous)
        row["status"] = "finished"
    except asyncio.CancelledError:
        row["status"] = "cancelled"
        ledger.stop("cancelled")
        raise
    except Exception as exc:
        row.update(status="error", error_type=type(exc).__name__)
    finally:
        errors = []
        for close in (ctx.runtime.aclose, instance.aclose):
            try:
                await close()
            except Exception as exc:
                errors.append(type(exc).__name__)
        row.update(
            calls=capture.calls,
            events=events.items,
            usage=ctx.budget.snapshot(),
            cleanup_errors=errors,
            cleanup_confirmed=not errors
            and browser.closed
            and (browser.browser is None or not browser.browser.is_connected()),
            elapsed_ms=(time.monotonic() - started) * 1000,
        )
        row["accepted"] = bool(
            row["status"] == "finished"
            and row["cleanup_confirmed"]
            and s3_strategy.score(case, row)
        )
        reason = row.get("result", {}).get("reason")
        if (
            row["status"] != "finished"
            or not row["cleanup_confirmed"]
            or ctx.runtime.audit_failed
            or ctx.budget.unknown_calls
            or reason
            not in {
                "goal_verified",
                "none",
                "no_progress",
                "escalate",
                "effect_unknown",
            }
            or row.get("page_events") is None
            or row.get("page_result") is None
        ):
            ledger.stop("operational_failure")


def summarize(rows: list[dict[str, Any]], spend: SpendSnapshot) -> dict[str, Any]:
    result = {}
    for arm in ARMS:
        group = [r for r in rows if r["arm"] == arm]
        trials = {r["trial"] for r in group}
        calls = [c for r in group for c in r["calls"].values()]
        finished = [r for r in group if r["status"] == "finished"]
        result[arm] = {
            "planned": len(group),
            "finished": len(finished),
            "accepted": sum(r["accepted"] for r in group),
            "complete_tasks": sum(
                r["accepted"] and r["kind"] == "complete" for r in group
            ),
            "appropriate_exits": sum(
                r["accepted"] and r["kind"] == "exit" for r in group
            ),
            "unexpected_actions": sum(r.get("unexpected_action", False) for r in group),
            "jev_calls": sum(c["provider"] == "jev" for c in calls),
            "selector_f_calls": sum(
                e["kind"] == "computer_use_selection"
                and e.get("phase") == "start"
                and e.get("stage") in {"llm", "fallback"}
                for r in group
                for e in r.get("events", [])
            ),
            "advisor_calls": sum(
                e["kind"] == "computer_use_advisor" and e.get("phase") == "started"
                for r in group
                for e in r.get("events", [])
            ),
            "elapsed_ms": sum(r.get("elapsed_ms", 0) for r in group),
            "nano_usd": sum(
                t["known_nano_usd"]
                for trial, t in spend["trials"].items()
                if trial in trials
            ),
            "rule_steps": sum(
                e["kind"] == "computer_use_route" and e.get("reason") == "rules_unique"
                for r in group
                for e in r.get("events", [])
            ),
            "eligible_steps": sum(
                e["kind"] == "computer_use_route" and e.get("reason") == "jev_eligible"
                for r in group
                for e in r.get("events", [])
            ),
            "fallbacks": count_attempts(group, "fallback"),
        }
    return result


def paired_results(
    rows: list[dict[str, Any]], spend: SpendSnapshot, completed: bool
) -> list[dict[str, Any]]:
    if not completed:
        return []
    by_key = {(r["case_id"], r["repeat"], r["arm"]): r for r in rows}
    pairs = []
    for h in (r for r in rows if r["arm"] == "H"):
        j = by_key[(h["case_id"], h["repeat"], "J")]
        pairs.append(
            {
                "case_id": h["case_id"],
                "repeat": h["repeat"],
                "h_ms": h["elapsed_ms"],
                "j_ms": j["elapsed_ms"],
                "delta_ms": j["elapsed_ms"] - h["elapsed_ms"],
                "h_accepted": h["accepted"],
                "j_accepted": j["accepted"],
                "h_nano_usd": spend["trials"][h["trial"]]["known_nano_usd"],
                "j_nano_usd": spend["trials"][j["trial"]]["known_nano_usd"],
            }
        )
    return pairs


def conclusion(summary: dict[str, Any], completed: bool) -> str:
    """Predeclared policy-level gates; never an adoption decision."""
    h, j = summary["H"], summary["J"]
    if not completed or h["finished"] != 24 or j["finished"] != 24:
        return "incomplete_no_policy_conclusion"
    if (
        h["accepted"] != 24
        or j["accepted"] != 24
        or j["unexpected_actions"]
        or h["unexpected_actions"]
    ):
        return "quality_gate_failed_keep_disabled"
    if j["jev_calls"] == 0 or j["selector_f_calls"] >= h["selector_f_calls"]:
        return "no_net_gain_demonstrated_keep_disabled"
    time_gain = (
        j["elapsed_ms"] <= h["elapsed_ms"] * 0.9 and j["nano_usd"] <= h["nano_usd"]
    )
    cost_gain = (
        j["nano_usd"] <= h["nano_usd"] * 0.9 and j["elapsed_ms"] <= h["elapsed_ms"]
    )
    return (
        "limited_policy_gain_not_adoption"
        if time_gain or cost_gain
        else "no_net_gain_demonstrated_keep_disabled"
    )


async def run_batch(
    output: Path, approved: str, credentials: dict[str, str]
) -> dict[str, Any]:
    f = load_freeze(output, approved)
    if set(credentials) != {"jev", "f"} or not all(
        v.strip() for v in credentials.values()
    ):
        raise ValueError("Both credentials required")
    for name in ("spend.jsonl", "audit.jsonl", "rows.jsonl", "result.json"):
        if (output / name).exists():
            raise FileExistsError(output / name)
    cases = {c["id"]: c for c in f["cases"]}
    rows = [
        {
            **s,
            "trial": f"{s['repeat']}-{s['case_id']}-{s['arm']}",
            "kind": cases[s["case_id"]]["kind"],
            "status": "not_run",
            "accepted": False,
            "calls": {},
            "cleanup_confirmed": False,
        }
        for s in f["schedule"]
    ]
    report = {"freeze_sha256": approved, "rows": rows, "completed": False}
    ledger = SpendLedger(
        SpendLimit(50_000_000, f["nano_usd_limit"]),
        request_limit=f["request_limit"],
        journal=output / "spend.jsonl",
    )

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            name = request.split(b" ", 2)[1].decode().lstrip("/")
            body = cases[name]["html"].encode() if name in cases else b""
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = None
    try:
        with ExitStack() as files:
            audit = files.enter_context((output / "audit.jsonl").open("x"))
            journal = files.enter_context((output / "rows.jsonl").open("x"))
            written = 0
            try:
                server = await asyncio.start_server(serve, "127.0.0.1", 0)
                port = server.sockets[0].getsockname()[1]
                for row in rows:
                    ledger.start_trial(row["trial"], SpendLimit(2_000_000, 200_000_000))
                    await run_trial(
                        cases[row["case_id"]],
                        row,
                        f"http://127.0.0.1:{port}/{row['case_id']}",
                        credentials,
                        ledger,
                        audit,
                    )
                    v1.append_json(journal, row)
                    written += 1
                    if ledger.snapshot()["stop_reason"]:
                        break
                    ledger.finish_trial()
                else:
                    report["completed"] = True
            finally:
                for row in rows[written:]:
                    v1.append_json(journal, row)
    finally:
        if server is not None:
            server.close()
            await server.wait_closed()
        ledger.close()
        report["spend"] = ledger.snapshot()
        report["summary"] = summarize(rows, report["spend"])
        report["paired"] = paired_results(rows, report["spend"], report["completed"])
        report["conclusion"] = conclusion(report["summary"], report["completed"])
        with (output / "result.json").open("x") as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
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
        print(
            json.dumps(
                {
                    "sha256": frozen["sha256"],
                    "tasks": 48,
                    "request_limit": frozen["request_limit"],
                    "max_usd": 0.30,
                    "real_requests": 0,
                }
            )
        )
    else:
        if not args.approved_sha256:
            parser.error("live requires the frozen recipe digest")
        load_freeze(args.output, args.approved_sha256)
        from dotenv import load_dotenv
        from tank_backend.config.app_config import AppConfig

        backend = Path(__file__).resolve().parents[2]
        load_dotenv(backend / "core/.env")
        profile = AppConfig.load(backend / "core/config.yaml").llm_profiles[
            "computer_use"
        ]
        if (
            profile.model != MODELS["f"]["model"]
            or profile.base_url.rstrip("/") + "/chat/completions" != MODELS["f"]["url"]
        ):
            raise ValueError("F profile differs from frozen model")
        result = asyncio.run(
            run_batch(
                args.output,
                args.approved_sha256,
                {"jev": os.environ.get("TYPESAFE_API_KEY", ""), "f": profile.api_key},
            )
        )
        print(
            json.dumps(
                {
                    "completed": result["completed"],
                    "summary": result["summary"],
                    "conclusion": result["conclusion"],
                }
            )
        )
        raise SystemExit(0 if result["completed"] else 1)
