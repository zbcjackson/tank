"""Frozen, opt-in Jev acceptance on owned local Chromium pages; no user profile."""

from __future__ import annotations

from tank_backend.llm.decision_profile import DecisionModelProfile

import asyncio
import hashlib
import inspect
import json
import time
from contextlib import ExitStack
from collections.abc import Callable
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any, TextIO, cast

from agent_computer_use import action_builder, agent, contracts, controller, factory, jev
from agent_computer_use.channels import dom
from tank_backend.agents import subagent, task_runtime
from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest
from tank_backend.agents.task_runtime import ExecutionRecord
from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit

from benchmarks.computer_use import jev_smoke as smoke
from benchmarks.computer_use import s3_replay as v1

SOURCE = Path(__file__).parent / "fixtures/s3-dom/cases.json"
LAYOUTS = ("toolbar", "table", "dialog")
SCENARIOS = ("sufficient", "missing", "conflicting", "stale", "no_effect")


def freeze_inputs() -> dict[str, Any]:
    cases = []
    hashes = v1.code_hashes()
    for module in (agent, contracts, controller, factory, jev, dom, action_builder, subagent, task_runtime, smoke):
        path = Path(inspect.getfile(module))
        hashes[str(path.relative_to(Path(__file__).resolve().parents[2]))] = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes[Path(__file__).name] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    from agent_computer_use.contracts import GoalContract

    cases = json.loads(SOURCE.read_text())
    expected = {f"{layout}-{scenario}" for scenario in SCENARIOS for layout in LAYOUTS}
    if len(cases) != len(expected) or {case["id"] for case in cases} != expected:
        raise ValueError("Expected the complete DOM fixture matrix")
    for case in cases:
        GoalContract.from_input(case["goal"])
    hashes["source/cases.json"] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    f = {"revision": "s3-dom-live-goal-2", "cases": cases, "source_sha256": hashes,
         "model": v1.MODELS["jev"], "request_limit": 15, "nano_usd_limit": 50_000_000,
         "requests_per_case": 1, "max_actions": 1, "max_observations": 4,
         "playwright": version("playwright"), "httpx": version("httpx"), "httpcore": version("httpcore"),
         "purpose": "real isolated Chromium plus Jev; three controlled layouts, not production validation",
         "stop_policy": "stop on first acceptance failure, unknown usage, audit or cleanup failure",
         "latency_scope": "per-case wall time includes browser lifecycle; not a model latency comparison"}
    f["sha256"] = v1.digest(f)
    return f


def prepare(output: Path) -> dict[str, Any]:
    f = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(f, ensure_ascii=False, indent=2) + "\n")
    return f


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    f = freeze_inputs()
    if f != json.loads((output / "freeze.json").read_text()) or f["sha256"] != approved:
        raise ValueError("DOM batch recipe changed; freeze and approve again")
    return f


class Capture(smoke.Capture):
    def __init__(self, browser: dom.ManagedChromiumChannel, stale: bool) -> None:
        super().__init__()
        self.browser, self.stale = browser, stale
        self.mutation_applied = False

    async def response(self, call_id: str, response: dict[str, Any]) -> None:
        await super().response(call_id, response)
        if self.stale:
            assert self.browser.page is not None
            await self.browser.page.locator("button").evaluate_all(
                "els => els.forEach(el => el.replaceWith(el.cloneNode(true)))")
            self.mutation_applied = True


def accepted(case: dict[str, Any], row: dict[str, Any]) -> bool:
    if len(row["calls"]) != 1 or "result" not in row:
        return False
    call = next(iter(row["calls"].values()))
    result = row["result"]
    try:
        choice = call["response"]["answers"]["next_action"]["choice"]
        request = call["request"]
        criterion = request["questions"]["next_action"]["criteria"][choice]
        selected = (next(e["label"] for e in request["state"]["snapshot"]["elements"]
                         if e["ref"] == criterion["target_ref"]) if isinstance(criterion, dict) else None)
        receipts = result["details"]["receipts"]
        if case["scenario"] in ("missing", "conflicting"):
            return (choice in ("need_more_context", "ambiguous") and result["status"] == "stopped"
                    and result["reason"] == "jev_eligible" and not receipts
                    and row["page_clicks"] == [] and row["page_result"] == "idle")
        if selected != f"执行 {case['expected_slot']}":
            return False
        if case["scenario"] == "stale":
            return (row["mutation_applied"] and result["reason"] == "stale_reference"
                    and result["status"] == "stopped" and not receipts
                    and row["page_clicks"] == [] and row["page_result"] == "idle")
        common = (len(receipts) == 1 and receipts[0]["status"] == "sent"
                  and row["page_clicks"] == [case["expected_slot"]]
                  and row["last_snapshot"]["observation_id"] != request["state"]["snapshot"]["observation_id"])
        if case["scenario"] == "no_effect":
            return (common and result["status"] == "unknown" and result["reason"] == "effect_unknown"
                    and result["details"]["pending_effect"] and row["page_result"] == "idle")
        return (common and result["status"] == "completed" and result["reason"] == "goal_verified"
                and row["page_result"] == "selected:K7")
    except (KeyError, TypeError, StopIteration):
        return False


async def run_case(
    case: dict[str, Any], row: dict[str, Any], url: str, credential: str,
    ledger: SpendLedger, audit_file: TextIO,
    acceptance: Callable[[dict[str, Any], dict[str, Any]], bool] = accepted,
) -> None:
    instance = factory.create_subagent({"browser": {"scope": "managed-page", "url": url}, "selector": "jev"})
    browser = cast(dom.ManagedChromiumChannel, instance.controller.source)
    capture = Capture(browser, case["scenario"] == "stale")

    async def audit(record: ExecutionRecord) -> None:
        await asyncio.to_thread(v1.append_json, audit_file, asdict(record))

    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"desktop", "network"})), SubAgentBudget(),
                          asyncio.Event(), deadline=time.monotonic() + 45, model_capture=capture,
                          model_policy=smoke.OneCallPolicy(ledger), audit=audit,
                          max_actions=1, max_observations=4)
    started = time.monotonic()
    row["status"] = "started"
    try:
        ctx.runtime.configure_decision_model(case["id"], DecisionModelProfile(smoke.ENDPOINT, smoke.MODEL, "jev"),
                                         credential=credential)
        async for event in instance.run(SubAgentRequest("local DOM acceptance", "", case["id"], case["goal"]), ctx):
            if "task_result" in event.metadata:
                row["result"] = event.metadata["task_result"]
        row["status"] = "finished"
        if browser.page is not None and not browser.page.is_closed():
            row["page_clicks"] = await browser.page.evaluate("window.clicks")
            row["page_result"] = await browser.page.get_by_role("status", name="Result", exact=True).text_content()
        if browser.previous is not None:
            row["last_snapshot"] = contracts.snapshot_json(browser.previous)
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
        row.update(calls=capture.calls, mutation_applied=capture.mutation_applied,
                   usage=ctx.budget.snapshot(), cleanup_errors=errors,
                   cleanup_confirmed=not errors and browser.closed and
                   (browser.browser is None or not browser.browser.is_connected()),
                   elapsed_ms=(time.monotonic() - started) * 1000)
        row["passed"] = bool(row["status"] == "finished" and row["cleanup_confirmed"] and acceptance(case, row))
        if ctx.runtime.audit_failed:
            ledger.stop("audit_failed")
        if not row["cleanup_confirmed"]:
            ledger.stop("cleanup_failed")
        if not row["passed"] or ctx.budget.unknown_calls:
            ledger.stop("case_failed")


async def run_batch(output: Path, approved: str, credential: str) -> dict[str, Any]:
    f = load_freeze(output, approved)
    return await execute_frozen_batch(output, f, credential)


async def execute_frozen_batch(
    output: Path, f: dict[str, Any], credential: str,
    acceptance: Callable[[dict[str, Any], dict[str, Any]], bool] = accepted,
) -> dict[str, Any]:
    """Execute a caller-validated recipe; the explicit evaluator is pinned by its entry point."""
    if not credential.strip():
        raise ValueError("Jev credential required")
    for name in ("spend.jsonl", "audit.jsonl", "rows.jsonl", "result.json"):
        if (output / name).exists():
            raise FileExistsError(output / name)
    cases = {c["id"]: c for c in f["cases"]}
    rows = [{"id": c["id"], "layout": c["layout"], "scenario": c["scenario"],
             "status": "not_run", "passed": False, "calls": {}, "cleanup_confirmed": False}
            for c in f["cases"]]
    report: dict[str, Any] = {"freeze_sha256": f["sha256"], "rows": rows, "completed": False}
    ledger = SpendLedger(SpendLimit(2_000_000, f["nano_usd_limit"]), request_limit=f["request_limit"],
                         journal=output / "spend.jsonl")

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            name = request.split(b" ", 2)[1].decode().lstrip("/")
            body = cases[name]["html"].encode() if name in cases else b""
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                         + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
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
                    ledger.start_trial(row["id"], SpendLimit(131072, 3_000_000))
                    await run_case(cases[row["id"]], row, f"http://127.0.0.1:{port}/{row['id']}",
                                   credential, ledger, audit, acceptance)
                    v1.append_json(journal, row)
                    written += 1
                    if ledger.snapshot()["stop_reason"] or not row["passed"]:
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
        report["spend"] = ledger.snapshot()
        report["summary"] = {"planned": len(rows), "passed": sum(r["passed"] for r in rows),
                             "not_run": sum(r["status"] == "not_run" for r in rows)}
        ledger.close()
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
        print(json.dumps({"sha256": frozen["sha256"], "request_limit": 15, "max_usd": 0.05, "real_requests": 0}))
    else:
        if not args.approved_sha256:
            parser.error("live requires a separately approved digest")
        load_freeze(args.output, args.approved_sha256)
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[2] / "core/.env")
        result = asyncio.run(run_batch(args.output, args.approved_sha256, os.environ.get("TYPESAFE_API_KEY", "")))
        print(json.dumps({"completed": result["completed"], "summary": result["summary"], "spend": result["spend"]["batch"]}))
        raise SystemExit(0 if result["completed"] else 1)
