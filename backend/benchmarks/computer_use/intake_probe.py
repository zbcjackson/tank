"""Frozen, text-only old/new intake prompt comparison. No desktop or Jev calls."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import os
import time
from contextlib import nullcontext
from importlib.metadata import version
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx

from agent_computer_use import intake
from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest
from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
from tank_backend.benchmarks.spend_http import ContextWindowContract
from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance
from tank_backend.llm import model_data
from tank_backend.llm.llm import LLM
from tank_backend.llm.profile import LLMProfile
from tank_backend.tools.computer_native import join_on_cancel

from . import s5_paired
from .jev_smoke import Capture
from .s3_replay import digest

FIXTURES = Path(__file__).parent / "fixtures/s5-intake"


def freeze_inputs() -> dict[str, Any]:
    cases = json.loads((FIXTURES / "cases.json").read_text())
    legacy = (FIXTURES / "legacy-system.txt").read_text()
    messages = {}
    for case in cases:
        current = intake.intake_messages(SubAgentRequest(case["request"], case["context"], case["id"]),
                                         case["application"])
        messages[case["id"]] = {"revised": current,
                                "legacy": [{"role": "system", "content": legacy}, current[1]]}
    schedule = []
    for repeat in range(3):
        for index, case in enumerate(cases):
            order = ("legacy", "revised") if (repeat + index) % 2 == 0 else ("revised", "legacy")
            schedule.extend({"id": f"{repeat}-{case['id']}-{arm}", "case_id": case["id"],
                             "arm": arm, "repeat": repeat} for arm in order)
    root = Path(__file__).resolve().parents[2]
    sources = dict(s5_paired.freeze_inputs()["source_sha256"])
    for path in (Path(__file__), root / "uv.lock", Path(inspect.getfile(model_data)),
                 Path(inspect.getfile(LLM)), Path(inspect.getfile(LLMProfile)),
                 *sorted(FIXTURES.glob("*.json")), FIXTURES / "legacy-system.txt"):
        sources[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = {
        "revision": "s5-intake-prompts-1", "cases": cases, "messages": messages,
        "schedule": schedule, "model": {**s5_paired.MODELS["qwen"], "output_ceiling": 2048},
        "output_allowance": 2058, "request_limit": 12, "token_limit": 12_000_000,
        "nano_usd_limit": 250_000_000, "seconds_per_request": 60,
        "source_sha256": sources,
        "packages": {name: version(name) for name in ("openai", "httpx", "pydantic")},
        "accounting": "frozen historical price estimates, not provider invoices",
        "gate": "complete known batch and revised 6/6 strict -> prepare new GUI validation only",
        "stop_policy": "known parse/semantic failures continue; model/runtime/unknown/bound errors stop",
        "scope": "synthetic task text and application-only context to Qwen; no desktop/images/Jev",
        "comparison": "same current schema/parser/context on both arms; only system prompt differs",
    }
    return {**frozen, "sha256": digest(frozen)}


def prepare(output: Path) -> dict[str, Any]:
    frozen = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2))
    return frozen


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    frozen = freeze_inputs()
    if frozen["sha256"] != approved or json.loads((output / "freeze.json").read_text()) != frozen:
        raise ValueError("Intake probe freeze changed; prepare a new directory")
    return frozen


def score(brief: intake.TaskBrief | str, case: dict[str, Any]) -> bool:
    if not isinstance(brief, intake.TaskBrief) or brief.application != case["application"]:
        return False
    if [(c.type, c.value) for c in brief.completion] != [("present", case["expected"])]:
        return False
    return (not brief.inputs if case["id"] == "calculator" else
            len(brief.inputs) == 1 and brief.inputs[0].value == case["expected"])


def fake_text(case: dict[str, Any], row: dict[str, Any]) -> str:
    if case["id"] == "calculator" and row["arm"] == "legacy":
        failures = json.loads((FIXTURES / "recorded-failures.json").read_text())["replies"]
        return failures[row["repeat"]]["text"]
    return json.dumps({"kind": "brief", "brief": {
        "application": case["application"], "objective": case["request"],
        "inputs": [] if case["id"] == "calculator" else [
            {"purpose": "document body", "value": case["expected"]}],
        "completion": [{"type": "present", "value": case["expected"]}],
    }})


async def run_batch(output: Path, approved: str, *, mode: str, credential: str = "") -> dict[str, Any]:
    frozen = load_freeze(output, approved)
    if mode not in {"fake", "live"} or (mode == "live" and not credential.strip()):
        raise ValueError("Choose fake/live and provide live credentials")
    with (output / "started.json").open("x") as marker:
        json.dump({"mode": mode, "sha256": approved}, marker)
    ledger = SpendLedger(SpendLimit(frozen["token_limit"], frozen["nano_usd_limit"]),
                         request_limit=12, journal=output / "spend.jsonl")
    rows = [{**job, "status": "not_run", "strict": False} for job in frozen["schedule"]]
    report: dict[str, Any] = {"sha256": approved, "mode": mode, "completed": False,
                              "rows": rows, "gui_operations": 0}
    cases = {case["id"]: case for case in frozen["cases"]}
    model = frozen["model"]
    try:
        for row in rows:
            load_freeze(output, approved)
            case = cases[row["case_id"]]
            capture = Capture()
            ledger.start_trial(row["id"], SpendLimit(1_100_000, 200_000_000))
            ctx = SubAgentContext(
                SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
                deadline=time.monotonic() + frozen["seconds_per_request"], model_capture=capture,
                model_policy=BenchmarkModelPolicy(ledger, (ContextWindowContract(
                    model["url"], model["model"], TokenAllowance(model["input_ceiling"],
                    frozen["output_allowance"], model["input_price"], model["output_price"]),
                    frozen["accounting"]),)),
            )
            ctx.runtime.configure_model(row["id"], LLMProfile(
                "text", credential if mode == "live" else "offline-intake", model["model"],
                model["url"].removesuffix("/chat/completions"), max_tokens=2048,
                temperature=0, extra_body={"enable_thinking": False},
            ))
            started = time.monotonic()
            row["status"] = "error"

            def fake(request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, json={"id": "intake-fake", "object": "chat.completion",
                    "created": 1, "model": model["model"], "choices": [{"index": 0,
                        "finish_reason": "stop", "message": {"role": "assistant",
                            "content": fake_text(case, row)}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}})

            try:
                with (patch("httpx.AsyncHTTPTransport", lambda *a, **kw: httpx.MockTransport(fake))
                      if mode == "fake" else nullcontext()):
                    assert ctx.runtime.model is not None
                    async with asyncio.timeout(frozen["seconds_per_request"]):
                        text = await ctx.runtime.model.complete(frozen["messages"][case["id"]][row["arm"]])
                row["text"] = text
                try:
                    brief = intake.parse_brief(text, f"{case['request']}\n{case['context']}")
                    row["parsed"] = brief.model_dump(mode="json") if isinstance(brief, intake.TaskBrief) else brief
                    row["strict"] = score(brief, case)
                except ValueError:
                    row["parsed"] = "invalid_intake"
                row["status"] = "finished"
            except (Exception, asyncio.CancelledError) as exc:
                row["error"] = type(exc).__name__
                ledger.stop("request_failed")
                if isinstance(exc, asyncio.CancelledError):
                    raise
            finally:
                try:
                    await join_on_cancel(ctx.runtime.aclose())
                except (Exception, asyncio.CancelledError) as exc:
                    row.update(status="error", cleanup_error=type(exc).__name__)
                    raise
                finally:
                    row["seconds"] = time.monotonic() - started
                    row["calls"] = capture.calls
                    ledger.finish_trial()
                    report["spend"] = ledger.snapshot()
                    (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            if ledger.snapshot()["stop_reason"] is not None:
                break
        report["completed"] = ledger.snapshot()["stop_reason"] is None and all(
            row["status"] == "finished" for row in rows)
    finally:
        try:
            ledger.close()
        except Exception:
            report["completed"] = False
            raise
        finally:
            report["spend"] = ledger.snapshot()
            report["completed"] = report["completed"] and report["spend"]["stop_reason"] is None
            report["summary"] = {arm: {case_id: sum(r["strict"] for r in rows
                if r["arm"] == arm and r["case_id"] == case_id) for case_id in cases}
                for arm in ("legacy", "revised")}
            qualified = all(r["strict"] for r in rows if r["arm"] == "revised")
            report["verdict"] = ("incomplete_no_conclusion" if not report["completed"] else
                "fake_wiring_only" if mode == "fake" else
                "prepare_gui_validation" if qualified else "revised_prompt_not_qualified")
            count = sum(r["status"] != "not_sent" for r in report["spend"]["requests"].values())
            report["external_model_requests"] = count if mode == "live" else 0
            report["fake_http_requests"] = count if mode == "fake" else 0
            (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("fake", "live"))
    parser.add_argument("--approved-sha256")
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare(args.output)["sha256"])
        return
    if not args.mode or not args.approved_sha256:
        parser.error("run requires --mode and --approved-sha256")
    if args.mode == "live":
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[2] / "core/.env")
    report = await run_batch(args.output, args.approved_sha256, mode=args.mode,
                             credential=os.environ.get("BAILIAN_API_KEY", ""))
    print(json.dumps({key: report[key] for key in ("completed", "verdict",
                     "external_model_requests", "fake_http_requests", "gui_operations")}))


if __name__ == "__main__":
    asyncio.run(main())
