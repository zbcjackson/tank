"""Frozen NL→desktop acceptance. Fake replaces model HTTP; live needs per-batch credentials."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import time
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, TypedDict, cast
from unittest.mock import MagicMock, patch

from agent_computer_use import (
    action_builder, advisor, agent, contracts, controller, factory, intake, observation, jev,
    model_view,
)
from agent_computer_use.channels import native
from tank_backend.tools import computer_ax, computer_native, computer_use_macos

from benchmarks.computer_use import s4_ax
from benchmarks.computer_use.s3_replay import MODELS, digest
from benchmarks.computer_use.s4_ax import (
    BUNDLES, OwnedApplication, PilotObserver, batch_may_continue, fake_model_http,
)

TEXTEDIT_BODY = "Tank NL / 中文验收\n"
FAKE_ENDPOINT = "https://s4-nl.invalid/v1/systemone"
FAKE_TEXT_ENDPOINT = "https://s4-nl-text.invalid/v1/chat/completions"


class PilotCase(TypedDict):
    id: str
    application: Literal["calculator", "textedit"]
    dispatch: Literal["ax_press", "quartz"]
    max_decisions: int
    move_window: bool
    profile: bool


CASES: tuple[PilotCase, ...] = (
    PilotCase(id="calculator-nl", application="calculator", dispatch="ax_press",
              max_decisions=14, move_window=False, profile=True),
    PilotCase(id="textedit-nl", application="textedit", dispatch="ax_press",
              max_decisions=4, move_window=False, profile=True),
    PilotCase(id="textedit-generic-nl", application="textedit", dispatch="ax_press",
              max_decisions=4, move_window=False, profile=False),
)


def task_prompt(case: PilotCase) -> str:
    if case["application"] == "calculator":
        return ("用计算器通过按键算出 7×8，让结果显示为 56。"
                "不要直接输入 56，也不要改模式或使用记忆键。")
    return (f"把 TextEdit 当前文档的正文全部替换为下面这段，不要保存或关闭窗口：\n"
            f"{TEXTEDIT_BODY}")


def task_input(case: PilotCase) -> dict[str, Any]:
    return {"target": {"application": BUNDLES[case["application"]]}}


def frozen_brief(case: PilotCase) -> dict[str, Any]:
    if case["application"] == "calculator":
        return {"application": "Calculator", "objective": "Display the product 56",
                "inputs": [], "completion": [{"type": "present", "value": "56"}]}
    return {"application": "TextEdit", "objective": "Document body matches the supplied text",
            "inputs": [{"purpose": "document body", "value": TEXTEDIT_BODY}],
            "completion": [{"type": "present", "value": TEXTEDIT_BODY}]}


def goal_from_case(case: PilotCase) -> dict[str, Any]:
    """Deterministic expansion used only to assert freeze briefs stay contract-valid."""
    from agent_computer_use.intake import TaskBrief, goal_from_brief

    return goal_from_brief(TaskBrief.from_input(frozen_brief(case)),
                           task_prompt(case)).model_dump(mode="json")


def channel_policy(case: PilotCase) -> dict[str, Any]:
    if not case["profile"]:
        return {}
    return s4_ax.channel_policy({
        "id": case["id"], "application": case["application"], "dispatch": case["dispatch"],
        "repeat": 0, "max_decisions": case["max_decisions"], "move_window": case["move_window"],
    })


def freeze_inputs() -> dict[str, Any]:
    from tank_backend.agents import subagent, task_runtime, runner, subagent_adapter, task_resources
    from tank_backend.llm import decision_model, task_decision_model, model_call, decision_profile, task_model
    from tank_backend.benchmarks import model_policy, spend_ledger
    from benchmarks.computer_use import jev_smoke
    from agent_computer_use.channels import apps as apps_channel

    root = Path(__file__).resolve().parents[2]
    paths = [Path(__file__), root / "plugins/agent-computer-use/plugin.yaml",
             *(Path(inspect.getfile(module)) for module in (
        action_builder, contracts, controller, factory, observation, native, apps_channel,
        computer_ax, computer_native, computer_use_macos, subagent, task_runtime, decision_model,
        task_decision_model, model_call, agent, jev, runner, subagent_adapter, task_resources,
        decision_profile, jev_smoke, advisor, intake, task_model, model_policy, spend_ledger,
        model_view, s4_ax,
    ))]
    data = {"revision": "s4-nl-1", "cases": list(CASES), "model": MODELS["jev"],
            "advisor_model": {**MODELS["qwen"], "output_ceiling": 2048},
            "fake_text_endpoint": FAKE_TEXT_ENDPOINT, "fake_endpoint": FAKE_ENDPOINT,
            "advisor_call_limit": 4,
            "accounting": "shared SDK-call limit; inherited conservative price estimates",
            "request_limit": sum(case["max_decisions"] for case in CASES),
            "nano_usd_limit": 250_000_000, "seconds_per_task": 120,
            "prompts": {case["id"]: task_prompt(case) for case in CASES},
            "briefs": {case["id"]: frozen_brief(case) for case in CASES},
            "task_inputs": {case["id"]: task_input(case) for case in CASES},
            "macos_policies": {case["id"]: channel_policy(case) for case in CASES},
            "scope": "owned Calculator and temporary TextEdit documents; one profile-less TextEdit",
            "acceptance": ("all three goals completed with intake details, independent AX readback, "
                           "and confirmed cleanup"),
            "stop_policy": ("known settled case failures stay in the denominator and the batch continues; "
                            "errors, unknown effects/receipts/usage, cancellation or unconfirmed cleanup "
                            "stop and retain all planned rows"),
            "source_sha256": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in paths}}
    data["sha256"] = digest(data)
    return data


def prepare(output: Path) -> dict[str, Any]:
    frozen = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    return frozen


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    frozen = freeze_inputs()
    if frozen["sha256"] != approved or json.loads((output / "freeze.json").read_text()) != frozen:
        raise ValueError("NL pilot freeze changed; prepare and approve a new recipe")
    return frozen


async def run_batch(output: Path, approved: str, *, mode: str, credential: str = "",
                    advisor_credential: str = "") -> dict[str, Any]:
    """Run a frozen recipe; fake replaces model HTTP, never the native application."""
    import httpx2 as httpx
    import httpx as text_http
    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.benchmarks.desktop_cleanup import MacOSInputCleanup
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded, TokenAllowance
    from tank_backend.config.app_config import AppConfig
    from tank_backend.llm.llm import LLM
    from tank_backend.pipeline.bus import Bus
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry
    from tank_backend.tools.manager import ToolManager
    from benchmarks.computer_use.jev_smoke import Capture

    frozen = load_freeze(output, approved)
    if mode not in {"fake", "live"} or mode == "live" and not (credential.strip() and advisor_credential.strip()):
        raise ValueError("Choose fake or provide an explicitly configured live credential")
    marker = output / "started.json"
    with marker.open("x") as stream:
        json.dump({"mode": mode, "sha256": approved}, stream)
    ledger = SpendLedger(SpendLimit(12_000_000, frozen["nano_usd_limit"]),
                         request_limit=frozen["request_limit"], journal=output / "spend.jsonl")
    registry = ExtensionRegistry()
    manifest = read_manifest_from_yaml(Path(__file__).resolve().parents[2] / "plugins/agent-computer-use/plugin.yaml")
    for extension in manifest.extensions:
        registry.register(manifest.plugin_name, extension)
    definition = AgentDefinition(
        "s4-nl", "Natural-language desktop pilot",
        "Operate only the bound application named by intake or target.",
        extension="agent-computer-use:agent", decision_model="jev", model="advisor")
    resource = DesktopResource()
    rows = [{"case_id": case["id"], "status": "not_run", "passed": False} for case in frozen["cases"]]
    active_case, fake_index, fake_received = frozen["cases"][0], 0, 0
    endpoint = frozen["model"]["url"] if mode == "live" else frozen["fake_endpoint"]
    advisor_model = frozen["advisor_model"]
    text_endpoint = advisor_model["url"] if mode == "live" else frozen["fake_text_endpoint"]
    fake_escalated = False

    async def fake_decision(request: httpx.Request) -> httpx.Response:
        nonlocal fake_index, fake_received, fake_escalated
        fake_received += 1
        payload = json.loads(request.content)
        criteria = payload["questions"]["next_action"]["criteria"]
        if active_case["application"] == "calculator":
            if not fake_escalated:
                fake_escalated = True
                choice = "escalate"
            else:
                labels = ("7", "Multiply", "8", "Equals")
                label = labels[fake_index] if fake_index < len(labels) else None
                choice = next((key for key, value in criteria.items()
                               if isinstance(value, dict) and value.get("label") == label), "none")
                fake_index += 1
        else:
            choice = next((key for key, value in criteria.items()
                           if isinstance(value, dict) and value.get("operation") == "fill"), "none")
            fake_index += 1
        return httpx.Response(200, json={"model": frozen["model"]["model"], "answers": {
            "next_action": {"type": "choice", "choice": choice, "confidence": 1,
                            "probabilities": {key: int(key == choice) for key in criteria}}},
            "usage": {"input_tokens": 12, "output_tokens": 0}})

    async def fake_text(request: text_http.Request) -> text_http.Response:
        nonlocal fake_index, fake_received
        fake_received += 1
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        schema = payload.get("response_schema", {})
        if "brief" in schema.get("properties", {}):
            content = {"kind": "brief", "brief": frozen["briefs"][active_case["id"]]}
        else:
            label = ("7", "Multiply", "8", "Equals")[min(fake_index, 3)]
            choice = next(key for key, value in payload["actions"].items()
                          if value.get("label") == label)
            fake_index += 1
            content = {"kind": "candidate", "candidate_id": choice}
        return text_http.Response(200, json={"id": "nl-text", "object": "chat.completion",
            "created": 1, "model": advisor_model["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}})

    class PilotCapture(Capture):
        async def response(self, call_id, response):
            await super().response(call_id, response)
            if "choices" in response:
                self.calls[call_id]["response"]["choices"] = response["choices"]

    class Policy(BenchmarkModelPolicy):
        def __init__(self, maximum: int):
            model = frozen["model"]
            super().__init__(ledger, (ContextWindowContract(
                endpoint, model["model"], TokenAllowance(
                    model["input_ceiling"], model["output_ceiling"], model["input_price"],
                    model["output_price"]),
                "Frozen Jev conservative token-price contract", output_cap_required=False),
                ContextWindowContract(text_endpoint, advisor_model["model"], TokenAllowance(
                    advisor_model["input_ceiling"], advisor_model["output_ceiling"],
                    advisor_model["input_price"], advisor_model["output_price"]),
                    "Inherited S3 Qwen conservative reservation; output capped at 2048")))
            self.calls = 0
            self.maximum = maximum

        def reserve(self, call_id, request):
            if self.calls >= self.maximum:
                raise SpendLimitExceeded("trial_call_limit")
            super().reserve(call_id, request)
            self.calls += 1

    report: dict[str, Any] = {"revision": frozen["revision"], "mode": mode, "sha256": approved,
                              "completed": False, "rows": rows}
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {
            "TANK_S4_JEV_KEY": credential if mode == "live" else "fake-nl-pilot"}))
        if mode == "fake":
            stack.enter_context(fake_model_http(fake_decision))
            stack.enter_context(patch("httpx.AsyncHTTPTransport",
                                      lambda *args, **kwargs: text_http.MockTransport(fake_text)))
        try:
            for case, row in zip(frozen["cases"], rows, strict=True):
                load_freeze(output, approved)
                active_case, fake_index, fake_escalated = case, 0, False
                owner = OwnedApplication(cast(s4_ax.PilotCase, {
                    "id": case["id"], "application": case["application"],
                    "dispatch": case["dispatch"], "repeat": 0,
                    "max_decisions": case["max_decisions"], "move_window": case["move_window"],
                }))
                capture, audits = PilotCapture(), []
                observer = PilotObserver()
                ledger.start_trial(case["id"], SpendLimit(4_000_000, frozen["nano_usd_limit"]))
                started = time.monotonic()
                row.update(status="started", dispatch=case["dispatch"], profile=case["profile"])

                async def audit(record):
                    audits.append(asdict(record))

                try:
                    config = owner.start()
                    row["binding"] = config.model_dump(mode="json")
                    row["setup_actions"] = owner.setup_actions
                    app_config = AppConfig.from_raw_dict({
                        "llm": {"default": {"model": "unused", "api_key": "unused",
                                            "base_url": "https://unused.invalid/v1"},
                                "advisor": {"model": advisor_model["model"],
                                    "api_key": advisor_credential if mode == "live" else "fake-advisor",
                                    "base_url": text_endpoint.removesuffix("/chat/completions"),
                                    "max_tokens": advisor_model["output_ceiling"], "temperature": 0,
                                    "extra_body": {"enable_thinking": False}}},
                        "decision_models": {"jev": {"url": endpoint,
                            "model": frozen["model"]["model"], "credential_env": "TANK_S4_JEV_KEY"}},
                        "subagents": {"agent-computer-use:agent": {"config": {
                            "macos": channel_policy(case), "selector": "jev", "advisor": "llm",
                            "intake": "llm"}}},
                    })
                    runner = AgentRunner(MagicMock(spec=LLM), MagicMock(spec=ToolManager), Bus(),
                        ToolApprovalPolicy(computer_mode="allow"), PendingToolCallStore(),
                        {definition.name: definition}, registry=registry, app_config=app_config,
                        desktop_resource=resource)
                    outputs = [item async for item in runner.run_agent(
                        definition, [{"role": "user", "content": task_prompt(case)}],
                        task_id=case["id"], task_input=task_input(case),
                        authorization=SubAgentAuthorization(frozenset({"desktop", "network"})),
                        model_policy=Policy(case["max_decisions"]), model_capture=capture,
                        audit=audit, observer=observer,
                        max_actions=case["max_decisions"] + 1,
                        max_observations=1 + 3 * case["max_decisions"],
                        deadline=time.monotonic() + frozen["seconds_per_task"],
                        desktop_cleanup=MacOSInputCleanup(),
                    )]
                    result = next(item.metadata["task_result"] for item in outputs
                                  if "task_result" in item.metadata)
                    row["result"] = result
                    values = owner.read_values()
                    row["independent_values"] = values
                    if case["application"] == "calculator":
                        valid = values.get("expression") == "7×8" and values.get("result") == "56"
                    else:
                        valid = values.get("document") == TEXTEDIT_BODY
                    row["passed"] = bool(
                        valid and result["status"] == "completed"
                        and result["cleanup"] == "confirmed"
                        and "intake" in result.get("details", {}))
                    row["status"] = "finished"
                except asyncio.CancelledError:
                    ledger.stop("cancelled")
                    row["status"] = "cancelled"
                    raise
                except Exception as exc:
                    row.update(status="error", error_type=type(exc).__name__, error=str(exc))
                finally:
                    try:
                        row["application_cleanup"] = owner.close()
                    except Exception as exc:
                        row["application_cleanup"] = {"confirmed": False, "error": str(exc)}
                    row["passed"] = row.get("passed", False) and row["application_cleanup"]["confirmed"]
                    row.update(calls=list(capture.calls.values()), audit=audits, events=observer.events,
                               elapsed_ms=(time.monotonic() - started) * 1000)
                    ledger.finish_trial()
                    (output / "result.json").write_text(
                        json.dumps({**report, "spend": ledger.snapshot()}, ensure_ascii=False,
                                   indent=2) + "\n")
                print(json.dumps({"case_id": case["id"], "status": row["status"], "passed": row["passed"],
                                  "model_calls": len(row.get("calls", [])), "error": row.get("error")}),
                      flush=True)
                if not batch_may_continue(row, ledger.snapshot()["stop_reason"]):
                    ledger.stop("nl_case_failed")
                    break
            report["completed"] = all(row["passed"] for row in rows)
        finally:
            report["spend"] = ledger.snapshot()
            report["fake_http_requests"] = fake_received
            report["external_model_requests"] = (
                sum(len(r.get("calls", [])) for r in rows) if mode == "live" else 0)
            ledger.close()
            (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", choices=("fake", "live"))
    parser.add_argument("--approved-sha256")
    args = parser.parse_args()
    if args.run is None:
        print(json.dumps({k: v for k, v in prepare(args.output).items()
                          if k in {"sha256", "request_limit", "nano_usd_limit", "revision"}}))
    else:
        if not args.approved_sha256:
            parser.error("Execution requires the frozen recipe digest")
        load_freeze(args.output, args.approved_sha256)
        credential = advisor_credential = ""
        if args.run == "live":
            from dotenv import dotenv_values
            env = dotenv_values(Path(__file__).resolve().parents[2] / "core/.env")
            credential = os.environ.get("TYPESAFE_API_KEY") or env.get("TYPESAFE_API_KEY") or ""
            advisor_credential = os.environ.get("BAILIAN_API_KEY") or env.get("BAILIAN_API_KEY") or ""
        result = asyncio.run(run_batch(args.output, args.approved_sha256, mode=args.run,
                                       credential=credential, advisor_credential=advisor_credential))
        raise SystemExit(0 if result["completed"] else 1)
