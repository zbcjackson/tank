"""Explicit, paid opt-in: three synthetic Chromium tasks, at most one Jev send each."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from tank_backend.llm.model_data import ModelRequest
from dotenv import load_dotenv

from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.resources import DesktopResource
from tank_backend.agents.runner import AgentRunner
from tank_backend.agents.subagent import SubAgentAuthorization
from tank_backend.agents.task_runtime import ExecutionRecord
from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
from tank_backend.benchmarks.spend_http import ContextWindowContract
from tank_backend.benchmarks.spend_ledger import (
    SpendLedger, SpendLimit, SpendLimitExceeded, TokenAllowance,
)
from tank_backend.config.app_config import AppConfig
from tank_backend.llm.llm import LLM
from tank_backend.pipeline.bus import Bus
from tank_backend.plugin.manifest import read_manifest_from_yaml
from tank_backend.plugin.registry import ExtensionRegistry
from tank_backend.tools.manager import ToolManager

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
CASES = (
    {"name": "english", "target": "Store document", "buttons": ["Save", "Cancel"],
     "expected_status": "completed"},
    {"name": "chinese", "target": "保存文档", "buttons": ["保存", "取消"],
     "expected_status": "completed"},
    {"name": "no-target", "target": "Save document", "buttons": ["Cancel", "Delete"],
     "expected_status": "stopped"},
)


class OneCallPolicy(BenchmarkModelPolicy):
    def __init__(self, ledger: SpendLedger) -> None:
        super().__init__(ledger, (ContextWindowContract(
            ENDPOINT, MODEL, TokenAllowance(65536, 65536, 42, 0),
            "TypeSafe models docs 2026-10-03; conservative smoke reservation",
            output_cap_required=False,
        ),))
        self.calls = 0

    def reserve(self, call_id: str, request: ModelRequest) -> None:
        if self.calls:
            self.ledger.stop("smoke_case_requests")
            raise SpendLimitExceeded("smoke_case_requests")
        super().reserve(call_id, request)
        self.calls += 1


class Capture:
    def __init__(self) -> None:
        self.calls: dict[str, dict[str, Any]] = {}

    async def request(self, call_id: str, request: ModelRequest) -> None:
        # Only synthetic JSON, never authorization headers or environment values.
        self.calls[call_id] = {
            "capture_level": "model_call",
            "request": request.parameters,
            "request_sha256": hashlib.sha256(json.dumps(request.parameters, sort_keys=True).encode()).hexdigest(),
        }

    async def response(self, call_id: str, response: dict[str, Any]) -> None:
        if "choice" in response:
            response = {"model": self.calls[call_id]["request"]["model"],
                        "answers": {"next_action": {"type": "choice", "choice": response["choice"],
                            "confidence": response["confidence"], "probabilities": response["probabilities"]}},
                        "usage": {"input_tokens": response["input_tokens"],
                                  "output_tokens": response["output_tokens"]}}
        self.calls[call_id]["capture_status"] = "returned"
        data = response
        self.calls[call_id]["response"] = {
            key: data.get(key) for key in ("model", "answers", "usage")
        }


def goal(case: dict[str, Any]) -> dict[str, Any]:
    fact = {"key": "status:Result", "value": "saved"}
    return {'objective': case['target'], 'scope': 'smoke', 'completion': [fact], 'schema_version': 2, 'goal_id': 'goal', 'intent': case['target'], 'authorization_ref': 'current_task', 'allowed_operations': ['click', 'fill']}


async def run_smoke(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    report: dict[str, Any] = {
        "endpoint": ENDPOINT, "model": MODEL, "request_limit": 3,
        "reserved_usd_limit": 0.01, "synthetic_only": True, "cases": [],
    }
    (output / "freeze.json").write_text(json.dumps({
        **report, "cases": CASES,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2))
    ledger = SpendLedger(SpendLimit(393216, 10_000_000), request_limit=3,
                         journal=output / "spend.jsonl")
    registry = ExtensionRegistry()
    manifest = read_manifest_from_yaml(
        Path(__file__).resolve().parents[2] / "plugins/agent-computer-use/plugin.yaml",
    )
    for extension in manifest.extensions:
        registry.register(manifest.plugin_name, extension)
    definition = AgentDefinition("smoke", "", "Synthetic save task",
                                 extension="agent-computer-use:agent", decision_model="jev")
    active_case = CASES[0]

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\r\n\r\n")
            buttons = "".join(
                f'<button onclick="document.querySelector(\'[role=status]\').textContent = '
                f"'{('saved' if index == 0 and active_case['name'] != 'no-target' else 'wrong')}'"
                f'">{html.escape(label)}</button>'
                for index, label in enumerate(active_case["buttons"])
            )
            body = ('<form onsubmit="event.preventDefault()">' + buttons +
                    '<div role="status" aria-label="Result">empty</div></form>').encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                         + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
    config = AppConfig.from_raw_dict({
        "llm": {"default": {"api_key": "unused", "model": "unused",
                             "base_url": "https://unused.invalid/v1"}},
        "decision_models": {"jev": {"url": ENDPOINT,
                                "model": MODEL, "credential_env": "TYPESAFE_API_KEY"}},
        "subagents": {"agent-computer-use:agent": {"config": {
            "browser": {"scope": "smoke", "url": url}, "selector": "jev",
        }}},
    })
    # No parent LLM/tools execute: only the real extension, Runner and Chromium are exercised.
    runner = AgentRunner(MagicMock(spec=LLM), MagicMock(spec=ToolManager), Bus(),
                        ToolApprovalPolicy(computer_mode="allow"), PendingToolCallStore(),
                        {definition.name: definition}, registry=registry, app_config=config,
                        desktop_resource=DesktopResource())
    try:
        for case in CASES:
            active_case = case
            ledger.start_trial(str(case["name"]), SpendLimit(131072, 3_000_000))
            capture, audits = Capture(), []

            async def audit(record: ExecutionRecord) -> None:
                audits.append(asdict(record))

            started = time.monotonic()
            result: dict[str, Any] = {"name": case["name"], "passed": False}
            try:
                outputs = [out async for out in runner.run_agent(
                    definition, [], task_id=f"smoke-{case['name']}", task_input=goal(case),
                    authorization=SubAgentAuthorization(frozenset({"desktop", "network"})),
                    deadline=time.monotonic() + 45, model_policy=OneCallPolicy(ledger),
                    model_capture=capture, audit=audit, max_actions=1, max_observations=3,
                )]
                terminal = next(out.metadata["task_result"] for out in outputs
                                if "task_result" in out.metadata)
                result["result"] = terminal
                result["passed"] = (
                    terminal["status"] == case["expected_status"]
                    and terminal["cleanup"] == "confirmed" and len(capture.calls) == 1
                    and (case["name"] != "no-target" or (
                        terminal["reason"] == "none" and not terminal["details"]["receipts"]
                        and next(iter(capture.calls.values()))["response"]["answers"]
                        ["next_action"]["choice"] == "none"
                    ))
                )
            except Exception as exc:
                result["error_type"] = type(exc).__name__
            result.update(elapsed_ms=(time.monotonic() - started) * 1000,
                          calls=capture.calls, audits=audits)
            report["cases"].append(result)
            if not result["passed"]:
                break
            ledger.finish_trial()
    finally:
        server.close()
        await server.wait_closed()
        report["spend"] = ledger.snapshot()
        ledger.close()
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true", required=True)
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[2] / "core/.env")
    outcome = asyncio.run(run_smoke(args.output))
    print(json.dumps({"cases": [{"name": c["name"], "passed": c["passed"]}
                                for c in outcome["cases"]], "spend": outcome["spend"]["batch"]}))
    raise SystemExit(0 if len(outcome["cases"]) == 3 and all(
        c["passed"] for c in outcome["cases"]
    ) else 1)
