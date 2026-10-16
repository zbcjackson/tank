"""One owned Calculator click, with fake/live model HTTP and independent AX readback."""

from __future__ import annotations

import hashlib
import argparse
import asyncio
import inspect
import json
import os
import time
from contextlib import nullcontext
from collections.abc import Callable
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx

from tank_backend.agents import resources
from tank_backend.benchmarks import desktop_cleanup, grounding_probe
from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit
from tank_backend.llm import model_data
from tank_backend.tools import computer_observation, computer_use_common
from tank_backend.tools.computer_native import join_on_cancel, run_native

from . import a_owned_input, a_preflight as static, s5_paired as s5
from .s3_replay import digest


def freeze_inputs() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    sources = dict(s5.freeze_inputs()["source_sha256"])
    for path in (Path(__file__), root / "uv.lock", *(Path(inspect.getfile(module)) for module in
                 (a_owned_input, static, desktop_cleanup, resources, model_data,
                  computer_observation, computer_use_common, grounding_probe))):
        sources[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = {
        "revision": "a-owned-seven-1", "arm": "A-control-owned-seven",
        "model": s5.a_model_contract(), "system": static.SYSTEM,
        "target": "Calculator button 7", "image_size": list(static.SIZE),
        "case": {"id": "A-control-owned-seven", "max_completion_tokens": 2048,
                 "extra_body": {"enable_thinking": False}},
        "request_limit": 1, "nano_usd_limit": 200000000, "token_limit": 1100000,
        "seconds_per_task": 240, "seconds_per_request": static.SECONDS_PER_REQUEST,
        "output_allowance": 2048 + static.OUTPUT_USAGE_SLACK,
        "accounting": "frozen token-price estimates, not provider invoices",
        "source_sha256": sources,
        "packages": {name: version(name) for name in ("openai", "httpx", "pillow")},
        "acceptance": "one model-selected click, AX result 7, input/app cleanup confirmed",
        "scope": "fresh owned Calculator only; one request/click; no retries or adoption claim",
        "data": "new full primary-display PNG to Qwen; AX annotation stays local",
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
        raise ValueError("GUI smoke freeze changed; prepare a new directory")
    return frozen


def annotation(config: s5.native.NativeConfig) -> dict[str, Any]:
    window = s5.native.read_window(config)
    candidates, incomplete = s5.computer_ax.ax_window_candidates(
        config.window_id, window.display_geometry,
    )
    targets = [c for c in candidates if c.role == "AXButton" and c.enabled
               and (c.title or c.description or c.identifier or c.value) == "7"]
    if incomplete or len(targets) != 1 or targets[0].frame is None:
        raise ValueError("Independent button-7 annotation unavailable")
    x, y, width, height = targets[0].frame
    return {"center": [x + width // 2, y + height // 2], "radius": 20,
            "provenance": "local AX only; never sent to the live model"}


def fake_reply(target: dict[str, Any]) -> Callable[[httpx.Request], httpx.Response]:
    """Synthetic response uses local AX truth solely for fake wiring acceptance."""
    def respond(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        x, y = (round(value * 1000 / size)
                for value, size in zip(target["center"], static.SIZE))
        answer = json.dumps({"coordinate_space": "normalized_1000",
                             "image_size": list(static.SIZE), "x": x, "y": y})
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 2,
                                        "total_tokens": 9}},
        ]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content="".join(
            "data: " + json.dumps({"id": "fake-smoke", "object": "chat.completion.chunk",
                                   "created": 1, "model": model, **chunk}) + "\n\n"
            for chunk in chunks
        ) + "data: [DONE]\n\n")
    return respond


async def run_batch(
    output: Path, approved: str, *, mode: str, credential: str = "",
) -> dict[str, Any]:
    frozen = load_freeze(output, approved)
    if mode not in {"fake", "live"} or (mode == "live" and not credential.strip()):
        raise ValueError("Choose fake/live and provide live credentials")
    with (output / "started.json").open("x") as marker:
        json.dump({"mode": mode, "sha256": approved}, marker)
    ledger = SpendLedger(SpendLimit(frozen["token_limit"], frozen["nano_usd_limit"]),
                         request_limit=1, journal=output / "spend.jsonl")
    row: dict[str, Any] = {"id": frozen["case"]["id"], "status": "not_run"}
    report: dict[str, Any] = {"sha256": approved, "mode": mode, "arm": frozen["arm"],
                              "row": row, "passed": False, "click_attempted": False,
                              "click_returned": False, "status": "not_run"}
    resource = resources.DESKTOP_RESOURCE
    current = asyncio.current_task()
    deadline = time.monotonic() + frozen["seconds_per_task"]

    def check() -> None:
        if current is not None and current.cancelling():
            raise RuntimeError("GUI smoke cancelled")
        if time.monotonic() >= deadline:
            raise TimeoutError("GUI smoke deadline")

    try:
        async with resource.acquire(deadline):
            cleanup = desktop_cleanup.MacOSInputCleanup()
            owner = s5.OwnedApplication({**s5.TASKS[0], "expression": "7", "result": "7",
                                         "dispatch": "quartz", "move_window": False})
            input_started = False
            try:
                await cleanup.begin()
                input_started = True
                check()
                # NSWorkspace completion and NSRunLoop setup stay on the main thread,
                # as in the existing owner. Its launch/cleanup waits are bounded.
                config = owner.start()
                report["binding"] = config.model_dump(mode="json")
                report["setup_actions"] = owner.setup_actions
                check()
                if owner.read_values_once().get("result") != "0":
                    raise ValueError("Initial AX result is not zero")
                guard = a_owned_input.OwnedInputGuard(config, check=check)
                frame, png = await run_native(guard.observe)
                if frame.image_size != static.SIZE:
                    raise ValueError("Smoke requires a 1920x1080 primary display")
                target = await run_native(annotation, config)
                (output / "frame.png").write_bytes(png)
                (output / "observation.json").write_text(json.dumps(asdict(frame), indent=2))
                trial = {**frozen, "image_sha256": frame.image_sha256, "annotation": target}
                (output / "case.json").write_text(json.dumps(target, indent=2))
                load_freeze(output, approved)
                check()
                with (patch.object(static, "_fake", fake_reply(target))
                      if mode == "fake" else nullcontext()):
                    async with asyncio.timeout_at(deadline):
                        await static.run_trial(output, trial, png, frozen["case"], ledger, row,
                                               mode=mode, credential=credential)
                if ledger.snapshot()["stop_reason"] is not None:
                    raise RuntimeError("Model call did not settle within its contract")
                if not row.get("schema_valid") or row.get("abstained"):
                    report["status"] = "no_action"
                else:
                    load_freeze(output, approved)
                    check()
                    # Local annotation is diagnostic only, never an oracle action filter.
                    report["click_attempted"] = True
                    await run_native(guard.click, frame.frame_id, *row["point"])
                    report["click_returned"] = True
                    check()
                    for _ in range(5):
                        await asyncio.sleep(0.1)
                        check()
                        s5.native.read_window(config)
                        report["independent_values"] = owner.read_values_once()
                        if report["independent_values"].get("result") != "0":
                            break
                    report["status"] = "finished"
            finally:
                async def finish() -> None:
                    try:
                        if input_started:
                            report["input_cleanup"] = await cleanup.finish()
                    except Exception as exc:
                        report["input_cleanup"] = {"confirmed": False,
                                                    "error": type(exc).__name__}
                    finally:
                        try:
                            report["application_cleanup"] = owner.close()
                        except Exception as exc:
                            report["application_cleanup"] = {"confirmed": False,
                                                              "error": type(exc).__name__}
                        if ((input_started and not report.get("input_cleanup", {}).get("confirmed"))
                                or not report["application_cleanup"].get("confirmed")):
                            resource.quarantine("GUI smoke cleanup unconfirmed")
                await join_on_cancel(finish())
    except (Exception, asyncio.CancelledError) as exc:
        report.update(status="cancelled" if isinstance(exc, asyncio.CancelledError) else "error",
                      error=type(exc).__name__, error_detail=str(exc))
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        try:
            ledger.close()
        except Exception as exc:
            report.update(status="error", ledger_error=type(exc).__name__)
            raise
        finally:
            report["spend"] = ledger.snapshot()
            report["passed"] = bool(
                report["status"] == "finished" and report["click_returned"]
                and report.get("independent_values", {}).get("result") == "7"
                and report.get("input_cleanup", {}).get("confirmed")
                and report.get("application_cleanup", {}).get("confirmed")
                and report["spend"]["stop_reason"] is None
            )
            count = sum(r["status"] != "not_sent" for r in report["spend"]["requests"].values())
            report["external_model_requests"] = count if mode == "live" else 0
            report["fake_http_requests"] = count if mode == "fake" else 0
            report["verdict"] = ("fake_wiring_only" if mode == "fake" and report["passed"] else
                                 "one_click_smoke_passed" if report["passed"] else "not_passed")
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
    print(json.dumps({key: report[key] for key in (
        "status", "passed", "verdict", "external_model_requests", "fake_http_requests")}))


if __name__ == "__main__":
    asyncio.run(main())
