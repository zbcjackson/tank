"""Opt-in real Calculator image-choice loop; Box remains read-only calibration."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import importlib
import json
import platform
import plistlib
import time
from contextlib import ExitStack
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Callable, cast
from unittest.mock import patch

from benchmarks.computer_use import s4_ax
from benchmarks.computer_use.jev_image_dev import digest

ROOT = Path(__file__).resolve().parents[2]
OwnedApplication = s4_ax.OwnedApplication
CASES = (
    {"id": "jev-image-multiply", "application": "calculator", "dispatch": "ax_press",
     "repeat": 0, "max_decisions": 12, "move_window": False, "expression": "7×8", "result": "56"},
    {"id": "jev-image-add", "application": "calculator", "dispatch": "ax_press",
     "repeat": 1, "max_decisions": 12, "move_window": True, "expression": "12+34", "result": "46"},
)
MODEL = {"url": "https://api.typesafe.ai/v1/systemone", "model": "jev-1.14.0",
         "input_ceiling": 65536, "output_ceiling": 65536, "input_price": 42, "output_price": 0}


def goal(case: dict) -> dict:
    return {"schema_version": 2, "goal_id": case["id"], "scope": case["id"],
        "target": {"application": "com.apple.calculator"}, "authorization_ref": "current_task",
        "intent": f"Use Calculator buttons to calculate {case['expression']}; do not enter {case['result']} directly.",
        "objective": f"Enter {case['expression']} using buttons and evaluate it. Do not change modes or use memory.",
        "allowed_operations": ["click"], "completion": [
            {"key": "ax:value:expression", "value": case["expression"]},
            {"key": "ax:value:result", "value": case["result"]}]}


def application() -> dict:
    path = Path("/System/Applications/Calculator.app/Contents/Info.plist")
    info = plistlib.loads(path.read_bytes()) if path.exists() else {}
    return {"bundle_id": "com.apple.calculator", "version": info.get("CFBundleShortVersionString"),
            "build": info.get("CFBundleVersion"), "macos": platform.mac_ver()[0]}


def freeze_inputs() -> dict:
    from agent_computer_use import jev_image, jev_image_selector, model_selector, visual_selector
    from tank_backend.llm import decision_image
    from tank_backend.agents import resources, task_result
    from tank_backend.benchmarks import spend_http

    sources = s4_ax.freeze_inputs()["source_sha256"].copy()
    for path in (Path(__file__), ROOT / "uv.lock", *(Path(inspect.getfile(m)) for m in (
        jev_image, jev_image_selector, model_selector, visual_selector, decision_image, resources,
        task_result, spend_http))):
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"revision": "jev-image-native-1", "cases": [dict(c) for c in CASES], "model": dict(MODEL),
        "goals": {c["id"]: goal(c) for c in CASES}, "application": application(),
        "source_sha256": sources,
        "versions": {name: version(name) for name in ("typesafe-sdk", "pillow")},
        "request_limit": 26, "nano_usd_limit": 100_000_000, "token_limit": 4_000_000,
        "seconds_per_task": 120, "box_calls_per_task": 1,
        "selector": "jev-image", "advisor": "jev-image",
        "price_evidence": "https://docs.typesafe.ai/models ; 2026-10-18 ; conservative context reservation",
        "scope": "new owned Calculator process/window only; existing running Calculator refuses setup",
        "policy": "12 image selections/reviews plus 1 read-only final-frame Box per task; no retries",
        "acceptance": "independent AX final values, witnessed native button sequence, image proposal receipts and cleanup",
        "box_target": "the Equals button", "box_interior_inset": 0.1,
        "boundary": "real app wiring pilot with AX candidates and explicit goal contracts, not open planning or production adoption"}


def prepare(output: Path) -> dict:
    frozen = freeze_inputs()
    frozen["sha256"] = digest(frozen)
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    return frozen


def load_freeze(output: Path, approved: str) -> dict:
    expected = freeze_inputs()
    expected["sha256"] = digest(expected)
    if approved != expected["sha256"] or json.loads((output / "freeze.json").read_text()) != expected:
        raise ValueError("native image freeze changed; prepare a new directory")
    return expected


def buttons(expression: str) -> list[str]:
    names = {"×": "Multiply", "+": "Add"}
    return [names.get(char, char) for char in expression] + ["Equals"]


def preflight() -> None:
    """OS permission reads only; never prompt or borrow an existing app session."""
    appkit = importlib.import_module("AppKit")
    foundation = importlib.import_module("Foundation")
    quartz = importlib.import_module("Quartz")
    objc = importlib.import_module("objc")

    functions: dict[str, Callable[[], bool]] = {}
    bundle = foundation.NSBundle.bundleWithPath_(
        "/System/Library/Frameworks/ApplicationServices.framework/Frameworks/HIServices.framework")
    objc.loadBundleFunctions(bundle, functions, [("AXIsProcessTrusted", b"Z")])
    if not functions["AXIsProcessTrusted"]() or not quartz.CGPreflightScreenCaptureAccess():
        raise RuntimeError("Accessibility and screen capture permissions are required")
    if any(app.bundleIdentifier() == "com.apple.calculator"
           for app in appkit.NSWorkspace.sharedWorkspace().runningApplications()):
        raise RuntimeError("Calculator is already running; existing sessions are not borrowed")


async def run_batch(output: Path, approved: str, *, mode: str, credential: str = "") -> dict:
    import httpx2
    from agent_computer_use import create_subagent
    from agent_computer_use.channels import native
    from agent_computer_use.jev_image import JevImageProbe
    from tank_backend.agents.resources import DESKTOP_RESOURCE
    from tank_backend.agents.task_result import TaskResult
    from tank_backend.agents.task_runtime import ExecutionRecord
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentRequest
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded, TokenAllowance
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope, ModelRequest
    from tank_backend.tools import computer_ax

    frozen = load_freeze(output, approved)
    if mode not in {"fake", "live"} or mode == "live" and not credential.strip():
        raise ValueError("choose fake or provide the live Jev credential")
    for filename in ("started.json", "result.json", "calls.jsonl", "audit.jsonl", "actions.jsonl", "spend.jsonl"):
        if (output / filename).exists():
            raise FileExistsError(output / filename)
    if mode == "live":
        preflight()
    with (output / "started.json").open("x") as stream:
        json.dump({"mode": mode, "sha256": approved}, stream)
    (output / "images").mkdir()
    rows = [{"case_id": case["id"], "status": "not_run", "passed": False} for case in frozen["cases"]]
    report = {"sha256": approved, "mode": mode, "completed": False, "rows": rows}
    ledger = SpendLedger(SpendLimit(frozen["token_limit"], frozen["nano_usd_limit"]),
        request_limit=frozen["request_limit"], journal=output / "spend.jsonl")
    endpoint = MODEL["url"] if mode == "live" else "https://native-image.invalid/v1/systemone"
    contract = ContextWindowContract(endpoint, MODEL["model"], TokenAllowance(
        MODEL["input_ceiling"], MODEL["output_ceiling"], MODEL["input_price"], MODEL["output_price"]),
        frozen["price_evidence"], output_cap_required=False)

    class Policy(BenchmarkModelPolicy):
        def __init__(self) -> None:
            super().__init__(ledger, (contract,))
            self.counts = {"choice": 0, "box": 0}

        def reserve(self, call_id: str, request: ModelRequest) -> None:
            kind = "box" if "target" in request.parameters.get("questions", {}) else "choice"
            limit = 1 if kind == "box" else 12
            if self.counts[kind] >= limit or len(request.images) != 1:
                ledger.stop("native_image_call_limit")
                raise SpendLimitExceeded("native_image_call_limit")
            super().reserve(call_id, request)
            self.counts[kind] += 1

    def persist() -> None:
        report["spend"] = ledger.snapshot()
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    try:
        with ExitStack() as stack:
            journal = stack.enter_context((output / "calls.jsonl").open("x"))
            audit_file = stack.enter_context((output / "audit.jsonl").open("x"))
            actions_file = stack.enter_context((output / "actions.jsonl").open("x"))
            for case, row in zip(frozen["cases"], rows, strict=True):
                load_freeze(output, approved)
                ledger.start_trial(case["id"], SpendLimit(2_000_000, frozen["nano_usd_limit"]))
                owner = OwnedApplication(cast(s4_ax.PilotCase, dict(case)))
                context = plugin = None
                row.update(native_actions=[], box_shadow={"status": "not_run"})
                observer = s4_ax.PilotObserver()
                started = time.monotonic()
                fake_index = 0

                async def fake_http(request: httpx2.Request) -> httpx2.Response:
                    nonlocal fake_index
                    from email.parser import BytesParser
                    from email.policy import default
                    message = BytesParser(policy=default).parsebytes(
                        ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode()
                        + request.content)
                    raw = list(message.iter_parts())[0].get_payload(decode=True)
                    assert isinstance(raw, bytes)
                    payload = json.loads(raw)
                    if "target" in payload["questions"]:
                        answers = {"cardinality": {"type": "choice", "choice": "one", "confidence": 1,
                            "probabilities": {"none": 0, "one": 1, "several": 0}},
                            "target": {"type": "box", "box": {"left": .1, "top": .1,
                                "right": .2, "bottom": .2}, "confidence": .5}}
                    else:
                        criteria = payload["questions"]["next_action"]["criteria"]
                        sequence = buttons(case["expression"])
                        label = sequence[fake_index] if fake_index < len(sequence) else None
                        choice = next((k for k, v in criteria.items()
                            if isinstance(v, dict) and v.get("label") == label), "none")
                        fake_index += 1
                        answers = {"next_action": {"type": "choice", "choice": choice, "confidence": 1,
                            "probabilities": {key: float(key == choice) for key in criteria}}}
                    return httpx2.Response(200, json={"model": MODEL["model"], "answers": answers,
                        "usage": {"input_tokens": 10, "output_tokens": 5}})

                class Capture:
                    async def request(self, call_id: str, request: ModelRequest) -> None:
                        images = []
                        for asset in request.images:
                            path = output / "images" / (call_id + ".png")
                            with path.open("xb") as stream:
                                stream.write(asset.data)
                            images.append({"path": str(path.relative_to(output)), "part": asset.part,
                                "sha256": hashlib.sha256(asset.data).hexdigest(), "bytes": len(asset.data)})
                        journal.write(json.dumps({"case_id": case["id"], "call_id": call_id,
                            "request": request.parameters, "images": images,
                            "purpose": request.purpose, "headers": dict(request.headers)},
                            ensure_ascii=False) + "\n")
                        journal.flush()

                    async def response(self, call_id: str, response: dict[str, object]) -> None:
                        journal.write(json.dumps({"case_id": case["id"], "call_id": call_id,
                            "response": response}, ensure_ascii=False) + "\n")
                        journal.flush()

                async def audit(record: ExecutionRecord) -> None:
                    audit_file.write(json.dumps(asdict(record)) + "\n")
                    audit_file.flush()

                original_press = native.ax_press

                def witnessed_press(ref: computer_ax.AXElementRef) -> None:
                    api = computer_ax._load_ax()
                    error, pid = api["AXUIElementGetPid"](ref.native, None)
                    if error or pid != owner.pid:
                        raise RuntimeError("native target is outside owned process")
                    if computer_ax._attr(api, ref.native, "AXRole") != "AXButton":
                        raise RuntimeError("native target is not a Calculator button")
                    label = ""
                    for name in ("AXTitle", "AXDescription", "AXIdentifier", "AXValue"):
                        value = computer_ax._attr(api, ref.native, name)
                        if isinstance(value, str) and value:
                            label = value
                            break
                    item = {"label": str(label), "pid": pid, "status": "unknown"}
                    row["native_actions"].append(item)
                    actions_file.write(json.dumps({"case_id": case["id"], **item}) + "\n")
                    actions_file.flush()
                    original_press(ref)
                    item["status"] = "returned"
                    actions_file.write(json.dumps({"case_id": case["id"], **item}) + "\n")
                    actions_file.flush()

                async with DESKTOP_RESOURCE.acquire(time.monotonic() + frozen["seconds_per_task"]):
                    with ExitStack() as trial_stack:
                        if mode == "fake":
                            trial_stack.enter_context(s4_ax.fake_model_http(fake_http))
                        trial_stack.enter_context(patch.object(native, "ax_press", witnessed_press))
                        try:
                            row["status"] = "started"
                            config = owner.start()
                            row["binding"] = config.model_dump(mode="json")
                            row["setup_actions"] = owner.setup_actions
                            context = SubAgentContext(
                                SubAgentAuthorization(frozenset({"desktop", "network"})), SubAgentBudget(),
                                asyncio.Event(), deadline=started + frozen["seconds_per_task"],
                                max_actions=13, max_observations=64, observer=observer, audit=audit,
                                model_policy=Policy(), model_capture=Capture(),
                                model_data_scope=ModelDataScope(frozenset({"text", "image"}), 32 * 1024 * 1024))
                            context.runtime.configure_decision_model(case["id"], DecisionModelProfile(
                                endpoint, MODEL["model"], "TYPESAFE_API_KEY", images=True),
                                credential=credential if mode == "live" else "fake-native-image")
                            macos = s4_ax.macos_policy()["profiles"]["com.apple.calculator"]
                            plugin = create_subagent({"macos": {"profiles": {"com.apple.calculator": macos}},
                                "selector": "jev-image", "advisor": "jev-image"})
                            channel = plugin.controller.source
                            assert isinstance(channel, native.NativeAXChannel)
                            probe = JevImageProbe(channel, context)
                            outputs = [o async for o in plugin.run(SubAgentRequest(
                                frozen["goals"][case["id"]]["intent"], "", case["id"],
                                frozen["goals"][case["id"]]), context)]
                            row["result"] = outputs[-1].metadata["task_result"]
                            values = owner.read_values()
                            row["independent_values"] = values
                            path = [a["label"] for a in row["native_actions"] if a["status"] == "returned"]
                            row["path_verified"] = path == buttons(case["expression"])
                            proposals = {(e["candidate_set_id"], e["action_id"]) for e in observer.events
                                if e["kind"] == "computer_use_proposal" and e.get("source") == "jev_image"}
                            receipts = {(r["candidate_set_id"], r["action_id"])
                                for r in row["result"]["details"]["receipts"] if r["status"] == "sent"}
                            row["image_selected_actions"] = len(proposals & receipts)
                            row["passed"] = bool(row["result"]["status"] == "completed"
                                and values == {"expression": case["expression"], "result": case["result"]}
                                and row["path_verified"] and row["image_selected_actions"] > 0)
                            if row["result"]["status"] == "unknown":
                                ledger.stop("unknown_effect")
                            elif row["result"]["reason"] not in {
                                "goal_verified", "none", "no_progress", "advisor_unable",
                                "need_more_context", "ambiguous", "goal_progress_unverified", "invalid_decision",
                            }:
                                ledger.stop("task_operational_error")
                            if row["passed"] and ledger.snapshot()["stop_reason"] is None:
                                snapshot = channel.previous
                                assert snapshot is not None
                                before = len(row["native_actions"])
                                try:
                                    prepared, answer = await probe.assess(snapshot, state={
                                        "task": "Read-only localization; no action is authorized by this answer."},
                                        instructions=frozen["box_target"])
                                    from tank_backend.llm.decision_model import BoxResult
                                    assert isinstance(answer, BoxResult)
                                    window = native.read_window(config)
                                    candidates, incomplete = computer_ax.ax_window_candidates(
                                        window.window_id, window.display_geometry)
                                    targets = [c for c in candidates if c.role == "AXButton" and
                                        (c.title or c.description or c.identifier or c.value) == "Equals"]
                                    if incomplete or len(targets) != 1 or targets[0].frame is None:
                                        raise ValueError("independent Equals target unavailable")
                                    x, y, width, height = targets[0].frame
                                    inset = min(width, height) * frozen["box_interior_inset"]
                                    region = (x + inset, y + inset, x + width - inset, y + height - inset)
                                    point = prepared.map_box(answer.box)
                                    row["box_shadow"] = {"status": "returned", "answer": asdict(answer),
                                        "screen_point": point, "independent_interior": region,
                                        "correct": answer.cardinality.choice == "one" and
                                        region[0] <= point[0] < region[2] and region[1] <= point[1] < region[3],
                                        "native_actions_added": len(row["native_actions"]) - before}
                                    (output / "images" / (case["id"] + "-final.png")).write_bytes(prepared.source.png)
                                except Exception as exc:
                                    row["box_shadow"] = {"status": "error", "error_type": type(exc).__name__}
                                    ledger.stop("box_shadow_error")
                            row["status"] = "finished"
                        except asyncio.CancelledError:
                            row["status"] = "cancelled"
                            ledger.stop("cancelled")
                            raise
                        except Exception as exc:
                            row.update(status="error", error_type=type(exc).__name__)
                            ledger.stop("native_image_error")
                        finally:
                            cleanup = []
                            interrupted = None
                            for resource in (context.runtime if context is not None else None, plugin):
                                if resource is not None:
                                    try:
                                        await resource.aclose()
                                    except BaseException as exc:
                                        cleanup.append(type(exc).__name__)
                                        if not isinstance(exc, Exception):
                                            interrupted = exc
                            try:
                                row["application_cleanup"] = owner.close()
                            except Exception as exc:
                                row["application_cleanup"] = {"confirmed": False, "error_type": type(exc).__name__}
                            row["cleanup_confirmed"] = not cleanup and row["application_cleanup"]["confirmed"]
                            if "result" in row:
                                row["result"] = TaskResult.model_validate(row["result"]).with_cleanup(
                                    "confirmed" if row["cleanup_confirmed"] else "unknown").model_dump(mode="json")
                            row["passed"] = row["passed"] and row["cleanup_confirmed"]
                            if not row["cleanup_confirmed"]:
                                ledger.stop("cleanup_failed")
                                DESKTOP_RESOURCE.quarantine("native image pilot cleanup unconfirmed")
                            row.update(cleanup_errors=cleanup, events=observer.events,
                                elapsed_ms=(time.monotonic() - started) * 1000,
                                known_tokens=context.budget.total_tokens if context is not None else 0)
                            ledger.finish_trial()
                            persist()
                            if interrupted is not None:
                                raise interrupted
                if ledger.snapshot()["stop_reason"]:
                    break
            report["completed"] = (ledger.snapshot()["stop_reason"] is None
                and all(row["status"] == "finished" and row["cleanup_confirmed"] for row in rows))
            report["all_passed"] = report["completed"] and all(row["passed"] for row in rows)
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        ledger.stop("batch_error")
        raise
    finally:
        ledger.close()
        persist()
    return report


def main() -> None:
    import argparse
    import os
    from dotenv import dotenv_values

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", choices=("fake", "live"))
    parser.add_argument("--approved-sha256")
    args = parser.parse_args()
    if args.run is None:
        if args.approved_sha256:
            parser.error("a digest requires --run")
        frozen = prepare(args.output)
        print(json.dumps({k: frozen[k] for k in ("sha256", "request_limit", "nano_usd_limit")}))
        return
    if not args.approved_sha256:
        parser.error("execution requires a reviewed frozen digest")
    load_freeze(args.output, args.approved_sha256)
    credential = ""
    if args.run == "live":
        credential = os.environ.get("TYPESAFE_API_KEY") or dotenv_values(ROOT / "core/.env").get("TYPESAFE_API_KEY") or ""
    result = asyncio.run(run_batch(args.output, args.approved_sha256, mode=args.run, credential=credential))
    print(json.dumps({"completed": result["completed"], "all_passed": result.get("all_passed", False),
                      "spend": result["spend"]["batch"], "stop_reason": result["spend"]["stop_reason"]}))
    raise SystemExit(0 if result.get("all_passed") else 1)


if __name__ == "__main__":
    main()
