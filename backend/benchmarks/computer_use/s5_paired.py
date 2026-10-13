"""S5 paired native pilot: frozen production baseline (A) vs plugin host arms (H, J).

Preparation never accesses the desktop or a model. One schedule, one ledger,
three arms; scoring reads only independent AX evidence, never model claims.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import asyncio
import os
import time
from contextlib import ExitStack
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, TypedDict, cast
from unittest.mock import MagicMock, patch

from agent_computer_use import (
    action_builder,
    advisor,
    agent,
    contracts,
    controller,
    factory,
    intake,
    jev,
    model_selector,
    model_view,
    observation,
)
from agent_computer_use.channels import native

from tank_backend.benchmarks.spend_ledger import SpendSnapshot
from tank_backend.tools import computer_ax, computer_native, computer_use_macos

from benchmarks.computer_use import s4_ax, s4_nl
from benchmarks.computer_use.s3_replay import MODELS, digest

FAKE_ENDPOINT = "https://s5-jev.invalid/v1/systemone"
FAKE_TEXT_ENDPOINT = "https://s5-text.invalid/v1/chat/completions"

BUNDLES = s4_ax.BUNDLES
ARMS = ("A", "H", "J")
TEXTEDIT_BODY = s4_nl.TEXTEDIT_BODY
A_REQUEST_LIMIT = 20
ADVISOR_CALL_LIMIT = 4


class PilotTask(TypedDict):
    id: str
    application: str
    dispatch: str
    repeat: int
    max_decisions: int
    move_window: bool


TASK_SHAPES: tuple[tuple[str, str, str, int], ...] = (
    ("calculator-ax_press", "calculator", "ax_press", 14),
    ("calculator-quartz", "calculator", "quartz", 14),
    ("textedit", "textedit", "ax_press", 4),
)

TASKS: tuple[PilotTask, ...] = tuple(
    PilotTask(
        id=f"{name}-{repeat}",
        application=application,
        dispatch=dispatch,
        repeat=repeat,
        max_decisions=decisions,
        move_window=repeat == 1,
    )
    for name, application, dispatch, decisions in TASK_SHAPES
    for repeat in range(3)
)


def task_prompt(task: PilotTask) -> str:
    """One natural-language sentence per task, shared verbatim by all three arms."""
    if task["application"] == "calculator":
        return (
            "用计算器通过按键算出 7×8，让结果显示为 56。"
            "不要直接输入 56，也不要改模式或使用记忆键。"
        )
    return (
        f"把 TextEdit 当前文档的正文全部替换为下面这段，不要保存或关闭窗口：\n"
        f"{TEXTEDIT_BODY}"
    )


def task_input(task: PilotTask) -> dict[str, Any]:
    return {"target": {"application": BUNDLES[task["application"]]}}


def frozen_brief(task: PilotTask) -> dict[str, Any]:
    if task["application"] == "calculator":
        return {
            "application": "Calculator",
            "objective": "Display the product 56",
            "inputs": [],
            "completion": [{"type": "present", "value": "56"}],
        }
    return {
        "application": "TextEdit",
        "objective": "Document body matches the supplied text",
        "inputs": [{"purpose": "document body", "value": TEXTEDIT_BODY}],
        "completion": [{"type": "present", "value": TEXTEDIT_BODY}],
    }


def channel_policy(task: PilotTask) -> dict[str, Any]:
    return s4_ax.channel_policy(cast(s4_ax.PilotCase, dict(task)))


ARM_CONFIGS: dict[str, dict[str, Any]] = {
    "H": {"selector": "llm", "advisor": "llm", "intake": "llm"},
    "J": {"selector": "jev-fallback", "advisor": "llm", "intake": "llm"},
}

A_CONFIG: dict[str, Any] = {
    "agent": "computer_use",
    "config": "core/config.yaml",
    "input_cleanup": True,
    "max_steps": 15,
    "request_limits": {
        "planner": A_REQUEST_LIMIT,
        "locator": A_REQUEST_LIMIT,
        "total": A_REQUEST_LIMIT,
    },
}


def a_model_contract() -> dict[str, Any]:
    """Pin the production computer_use profile (model, URL and output cap, never keys)."""
    import yaml

    root = Path(__file__).resolve().parents[2]
    profile = yaml.safe_load((root / A_CONFIG["config"]).read_text())["llm"][
        "computer_use"
    ]
    qwen = MODELS["qwen"]
    return {
        "model": profile["model"],
        "url": profile["base_url"].rstrip("/") + "/chat/completions",
        "input_ceiling": qwen["input_ceiling"],
        "output_ceiling": int(profile.get("max_tokens", 4096)),
        "input_price": qwen["input_price"],
        "output_price": qwen["output_price"],
    }


def score_case(application: str, values: dict[str, str]) -> tuple[bool, bool, bool]:
    """Independent strict/partial/violation verdicts from AX readback only."""
    if application == "calculator":
        expression, result = values.get("expression", ""), values.get("result", "")
        strict = expression == "7×8" and result == "56"
        partial = expression == "7×8" and result != "56"
        violation = result == "56" and expression not in {"7×8", ""}
        return strict, partial, violation
    body = TEXTEDIT_BODY
    document = values.get("document", "")
    strict = document == body
    partial = not strict and body in document
    return strict, partial, False


def schedule() -> list[dict[str, str]]:
    """Rotate the three-arm first mover per (repeat, task) block."""
    plan: list[dict[str, str]] = []
    grouped: dict[int, list[PilotTask]] = {}
    for task in TASKS:
        grouped.setdefault(task["repeat"], []).append(task)
    for repeat in sorted(grouped):
        for index, task in enumerate(grouped[repeat]):
            offset = (repeat + index) % len(ARMS)
            rotated = ARMS[offset:] + ARMS[:offset]
            plan.extend(
                {"task_id": task["id"], "repeat": str(repeat), "arm": arm}
                for arm in rotated
            )
    return plan


def freeze_inputs() -> dict[str, Any]:
    from tank_backend.agents import (
        subagent,
        task_runtime,
        runner,
        subagent_adapter,
        task_resources,
    )
    from tank_backend.benchmarks import (
        driver,
        model_policy,
        request_budget,
        spend_http,
        spend_ledger,
        trace,
    )
    from tank_backend.llm import (
        decision_model,
        task_decision_model,
        model_call,
        decision_profile,
        task_model,
    )
    from benchmarks.computer_use import jev_smoke
    from agent_computer_use.channels import apps as apps_channel

    root = Path(__file__).resolve().parents[2]
    paths = [
        Path(__file__),
        root / "plugins/agent-computer-use/plugin.yaml",
        root / "agents/computer_use.md",
        Path(s4_ax.__file__),
        Path(s4_nl.__file__),
        *(
            Path(inspect.getfile(module))
            for module in (
                action_builder,
                contracts,
                controller,
                factory,
                intake,
                model_selector,
                observation,
                native,
                apps_channel,
                computer_ax,
                computer_native,
                computer_use_macos,
                subagent,
                task_runtime,
                decision_model,
                task_decision_model,
                model_call,
                agent,
                jev,
                runner,
                subagent_adapter,
                task_resources,
                decision_profile,
                jev_smoke,
                advisor,
                task_model,
                model_view,
                driver,
                request_budget,
                spend_http,
                spend_ledger,
                trace,
                model_policy,
            )
        ),
    ]
    per_task_requests = {
        "A": A_REQUEST_LIMIT,
        "H": lambda task: task["max_decisions"] + ADVISOR_CALL_LIMIT + 1,
        "J": lambda task: task["max_decisions"] + ADVISOR_CALL_LIMIT + 1,
    }
    request_limit = sum(
        per_task_requests[arm]
        if isinstance(per_task_requests[arm], int)
        else per_task_requests[arm](task)
        for task in TASKS
        for arm in ARMS
    )
    data = {
        "revision": "s5-paired-1",
        "arms": list(ARMS),
        "tasks": list(TASKS),
        "schedule": schedule(),
        "prompts": {task["id"]: task_prompt(task) for task in TASKS},
        "task_inputs": {task["id"]: task_input(task) for task in TASKS},
        "briefs": {task["id"]: frozen_brief(task) for task in TASKS},
        "macos_policies": {task["id"]: channel_policy(task) for task in TASKS},
        "arm_configs": ARM_CONFIGS,
        "a_config": A_CONFIG,
        "models": {
            "jev": MODELS["jev"],
            "qwen": {**MODELS["qwen"], "output_ceiling": 2048},
            "a": a_model_contract(),
        },
        "fake_endpoint": FAKE_ENDPOINT,
        "fake_text_endpoint": FAKE_TEXT_ENDPOINT,
        "advisor_call_limit": ADVISOR_CALL_LIMIT,
        "request_limit": request_limit,
        "nano_usd_limit": 2_000_000_000,
        "trial_limits": {"tokens": 4_000_000, "nano_usd": 250_000_000},
        "seconds_per_task": 240,
        "accounting": (
            "one durable ledger shared by all arms; frozen conservative "
            "price estimates, not provider invoices"
        ),
        "scoring": (
            "strict/partial/violation from independent fresh AX readback after "
            "each trial; never the model's own completion claim"
        ),
        "scope": (
            "owned fresh Calculator instances and temporary TextEdit documents on "
            "the primary display; one natural-language prompt shared by all arms"
        ),
        "decision_rule": {
            "kind": "descriptive_pilot",
            "n_per_task": 3,
            "first_mover": "rotated across arms per (repeat, task) block",
            "statement": (
                "the pilot reports per-arm strict/partial quality, model calls, "
                "tokens, cost and wall time; any adoption decision belongs to a "
                "separately frozen confirmatory experiment"
            ),
        },
        "stop_policy": (
            "known settled task failures stay in the denominator and the batch "
            "continues; errors, unknown effects/receipts/usage, cancellation or "
            "unconfirmed cleanup stop and retain all planned rows"
        ),
        "source_sha256": {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
    }
    data["sha256"] = digest(data)
    return data


def prepare(output: Path) -> dict[str, Any]:
    frozen = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2) + "\n"
    )
    return frozen


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    frozen = freeze_inputs()
    if (
        frozen["sha256"] != approved
        or json.loads((output / "freeze.json").read_text()) != frozen
    ):
        raise ValueError("S5 pilot freeze changed; prepare and freeze a new recipe")
    return frozen


def settled(row: dict[str, Any], stop_reason: str | None) -> bool:
    """Known task failures continue the batch; anything unresolved stops it."""
    if stop_reason is not None or row["status"] != "finished":
        return False
    if not row.get("application_cleanup", {}).get("confirmed"):
        return False
    if row["arm"] == "A":
        driver_result = row["driver"]
        return (
            driver_result["cleanup"] == "confirmed"
            and not driver_result["unknown_calls"]
            and driver_result["stop_reason"]
            not in {"error", "request_limit", "cancelled"}
        )
    result = row.get("result")
    if result is None:
        return False
    # An unverified in-trial effect becomes a settled known failure once the
    # independent readback saw the final state and cleanup confirmed the owned
    # app: trials are isolated, so nothing is replayed or carried forward.
    unknown_settled = (
        result["status"] == "unknown"
        and result["reason"] == "effect_unknown"
        and row.get("independent_values") is not None
    )
    return (
        (result["status"] != "unknown" or unknown_settled)
        and result["reason"] not in {"backend_error", "cancelled"}
        and result["cleanup"] == "confirmed"
        and all(
            receipt["status"] != "unknown" for receipt in result["details"]["receipts"]
        )
    )


class PilotObserver:
    """Persist bounded routing/selection metadata, never SDK messages or headers."""

    KEYS = (
        "task_id",
        "call_id",
        "phase",
        "stage",
        "status",
        "choice",
        "reason",
        "prompt_tokens",
        "completion_tokens",
        "elapsed_ms",
        "error_type",
        "http_status",
        "cause_type",
        "call_number",
        "observation_id",
        "advice_kind",
        "source",
        "model_choice",
        "action_id",
        "candidate_set_id",
        "goal_version",
    )
    KINDS = {
        "decision_error",
        "computer_use_error",
        "model_call",
        "computer_use_advisor",
        "computer_use_proposal",
        "computer_use_selection",
        "computer_use_route",
    }

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def on_event(self, kind: str, metadata: dict[str, Any]) -> None:
        if kind not in self.KINDS:
            return
        self.events.append(
            {
                "kind": kind,
                **{
                    key: value
                    for key, value in metadata.items()
                    if key in self.KEYS
                    and (value is None or type(value) in (str, int, float))
                },
            }
        )


def summarize(rows: list[dict[str, Any]], spend: SpendSnapshot) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for arm in ARMS:
        group = [row for row in rows if row["arm"] == arm]
        trials = {row["spend_trial"] for row in group if row.get("spend_trial")}
        calls = [call for row in group for call in row.get("calls", {}).values()]
        result[arm] = {
            "planned": len(group),
            "finished": sum(row["status"] == "finished" for row in group),
            "strict": sum(bool(row.get("strict")) for row in group),
            "partial": sum(bool(row.get("partial")) for row in group),
            "rule_violations": sum(bool(row.get("rule_violation")) for row in group),
            "passed": sum(bool(row.get("passed")) for row in group),
            "jev_calls": sum(call["provider"] == "jev" for call in calls),
            "text_calls": sum(call["provider"] != "jev" for call in calls)
            + sum(row.get("driver", {}).get("llm_calls", 0) for row in group),
            "elapsed_ms": sum(row.get("elapsed_ms", 0) for row in group),
            "nano_usd": sum(
                trial["known_nano_usd"]
                for name, trial in spend.get("trials", {}).items()
                if name in trials
            ),
            "intake_calls": sum(
                bool(row.get("result", {}).get("details", {}).get("intake"))
                for row in group
            ),
            "fallbacks": sum(
                event.get("kind") == "computer_use_selection"
                and event.get("stage") == "fallback"
                for row in group
                for event in row.get("events", [])
            ),
            "screenshots": sum(
                row.get("driver", {}).get("screenshots", 0) for row in group
            ),
            "non_gui_tools": sorted(
                {
                    tool
                    for row in group
                    for tool in row.get("driver", {}).get("non_gui_tools", ())
                }
            ),
        }
    result["direction"] = {
        "j_cost_below_a": result["J"]["nano_usd"] < result["A"]["nano_usd"],
        "j_time_below_a": result["J"]["elapsed_ms"] < result["A"]["elapsed_ms"],
        "h_cost_below_a": result["H"]["nano_usd"] < result["A"]["nano_usd"],
        "h_time_below_a": result["H"]["elapsed_ms"] < result["A"]["elapsed_ms"],
        "interpretation": "descriptive only; adoption requires a frozen confirmatory experiment",
    }
    return result


def paired_results(
    rows: list[dict[str, Any]], spend: SpendSnapshot, completed: bool
) -> list[dict[str, Any]]:
    if not completed:
        return []
    by_key = {(row["task_id"], row["repeat"], row["arm"]): row for row in rows}
    pairs = []
    for a_row in (row for row in rows if row["arm"] == "A"):
        key = (a_row["task_id"], a_row["repeat"])
        group = {arm: by_key[(*key, arm)] for arm in ARMS}
        pairs.append(
            {
                "task_id": a_row["task_id"],
                "repeat": a_row["repeat"],
                **{f"{arm.lower()}_strict": group[arm]["strict"] for arm in ARMS},
                **{f"{arm.lower()}_ms": group[arm]["elapsed_ms"] for arm in ARMS},
                **{
                    f"{arm.lower()}_nano_usd": spend["trials"][
                        group[arm]["spend_trial"]
                    ]["known_nano_usd"]
                    for arm in ARMS
                },
            }
        )
    return pairs


def conclusion(summary: dict[str, Any], *, completed: bool) -> str:
    if not completed:
        return "incomplete_no_pilot_conclusion"
    return "pilot_descriptive_only_needs_confirmatory_freeze"


class OwnedApplication(s4_ax.OwnedApplication):
    """s4_ax owner adapted to S5 task dicts; still owns launch, readback, cleanup."""

    def __init__(self, task: PilotTask) -> None:
        super().__init__(cast(s4_ax.PilotCase, dict(task)))
        self.task = task

    def read_values(self) -> dict[str, str]:
        """Re-activate the owned app before readback.

        Arm A legitimately defocuses the target (misgrounded clicks, focus
        handoffs); the s4_ax foreground invariant would misread that as a
        fatal error after a settled trial. The pilot owns this app instance,
        so activation stays inside owned resources.
        """
        if self.app is not None and computer_ax.ax_focused_pid() != self.pid:
            self.app.activateWithOptions_(0)
            s4_ax.pump(0.1)
        return super().read_values()


def _a_driver_result(result: Any) -> dict[str, Any]:
    return {
        "final_text": result.final_text,
        "steps": result.steps,
        "wall_s": result.wall_s,
        "tokens": result.tokens,
        "screenshots": result.screenshots,
        "timed_out": result.timed_out,
        "error": result.error,
        "llm_calls": result.llm_calls,
        "llm_ttft_s": result.llm_ttft_s,
        "llm_call_s": result.llm_call_s,
        "llm_total_s": result.llm_total_s,
        "stop_reason": result.stop_reason,
        "cleanup": result.cleanup,
        "primitives": result.primitives,
        "model_turns": result.model_turns,
        "unknown_calls": result.unknown_calls,
        "non_gui_tools": list(result.non_gui_tools),
    }


def create_a_driver(a_control: Any) -> Any:
    from tank_backend.benchmarks.driver import SubAgentDriver
    from tank_backend.benchmarks.request_budget import RequestLimits

    limits = A_CONFIG["request_limits"]
    return SubAgentDriver.create(
        A_CONFIG["agent"],
        Path(__file__).resolve().parents[2] / A_CONFIG["config"],
        request_limits=RequestLimits(**limits),
        spend=a_control,
        input_cleanup=A_CONFIG["input_cleanup"],
    )


async def run_batch(
    output: Path,
    approved: str,
    *,
    mode: str,
    credential: str = "",
    advisor_credential: str = "",
) -> dict[str, Any]:
    """Run one frozen schedule; fake replaces model HTTP, never the native application."""
    import httpx2 as httpx
    import httpx as text_http
    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.agents.resources import DesktopResource
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.benchmarks.desktop_cleanup import MacOSInputCleanup
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract, SpendControl
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )
    from tank_backend.benchmarks.trace import TraceSink
    from tank_backend.config.app_config import AppConfig
    from tank_backend.llm.llm import LLM
    from tank_backend.pipeline.bus import Bus
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry
    from tank_backend.tools.manager import ToolManager
    from benchmarks.computer_use.jev_smoke import Capture

    frozen = load_freeze(output, approved)
    if (
        mode not in {"fake", "live"}
        or mode == "live"
        and not (credential.strip() and advisor_credential.strip())
    ):
        raise ValueError(
            "Choose fake or provide an explicitly configured live credential"
        )
    marker = output / "started.json"
    with marker.open("x") as stream:
        json.dump({"mode": mode, "sha256": approved}, stream)
    for name in ("rows.jsonl", "audit.jsonl", "result.json"):
        if (output / name).exists():
            raise FileExistsError(output / name)
    ledger = SpendLedger(
        SpendLimit(30_000_000, frozen["nano_usd_limit"]),
        request_limit=frozen["request_limit"],
        journal=output / "spend.jsonl",
    )
    registry = ExtensionRegistry()
    manifest = read_manifest_from_yaml(
        Path(__file__).resolve().parents[2] / "plugins/agent-computer-use/plugin.yaml"
    )
    for extension in manifest.extensions:
        registry.register(manifest.plugin_name, extension)
    definitions: dict[str, AgentDefinition] = {}
    for arm in ("H", "J"):
        definition = AgentDefinition(
            f"s5-{arm.lower()}",
            "S5 paired pilot",
            "Operate only the bound application named by intake or target.",
            extension="agent-computer-use:agent",
            model="advisor",
        )
        if arm == "J":
            definition = replace(definition, decision_model="jev")
        definitions[arm] = definition
    resource = DesktopResource()
    tasks: dict[str, PilotTask] = {item["id"]: item for item in frozen["tasks"]}
    rows = [
        {
            **entry,
            "trial": f"{entry['repeat']}-{entry['task_id']}-{entry['arm']}",
            "status": "not_run",
            "strict": False,
            "partial": False,
            "rule_violation": False,
            "passed": False,
        }
        for entry in frozen["schedule"]
    ]
    active_task: PilotTask = next(iter(tasks.values()))
    fake_index, fake_received, fake_escalated = 0, 0, False
    jev_endpoint = (
        frozen["models"]["jev"]["url"] if mode == "live" else frozen["fake_endpoint"]
    )
    text_model = frozen["models"]["qwen"]
    text_endpoint = (
        text_model["url"] if mode == "live" else frozen["fake_text_endpoint"]
    )
    a_model = frozen["models"]["a"]

    async def fake_decision(request: httpx.Request) -> httpx.Response:
        nonlocal fake_index, fake_received, fake_escalated
        fake_received += 1
        payload = json.loads(request.content)
        criteria = payload["questions"]["next_action"]["criteria"]
        if active_task["application"] == "calculator":
            if not fake_escalated:
                fake_escalated = True
                choice = "escalate"
            else:
                labels = ("7", "Multiply", "8", "Equals")
                label = labels[fake_index] if fake_index < len(labels) else None
                choice = next(
                    (
                        key
                        for key, value in criteria.items()
                        if isinstance(value, dict) and value.get("label") == label
                    ),
                    "none",
                )
                fake_index += 1
        else:
            choice = next(
                (
                    key
                    for key, value in criteria.items()
                    if isinstance(value, dict) and value.get("operation") == "fill"
                ),
                "none",
            )
            fake_index += 1
        return httpx.Response(
            200,
            json={
                "model": frozen["models"]["jev"]["model"],
                "answers": {
                    "next_action": {
                        "type": "choice",
                        "choice": choice,
                        "confidence": 1,
                        "probabilities": {key: int(key == choice) for key in criteria},
                    }
                },
                "usage": {"input_tokens": 12, "output_tokens": 0},
            },
        )

    async def fake_text(request: text_http.Request) -> text_http.Response:
        nonlocal fake_index, fake_received
        fake_received += 1
        payload = json.loads(request.content)
        if "tools" in payload:
            chunk = {
                "id": "s5-offline",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": payload["model"],
                "choices": [
                    {"index": 0, "delta": {"content": "done"}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                },
            }
            return text_http.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode(),
            )
        body = json.loads(payload["messages"][1]["content"])
        schema = body.get("response_schema", {})
        if "brief" in schema.get("properties", {}):
            content: dict[str, Any] = {
                "kind": "brief",
                "brief": frozen["briefs"][active_task["id"]],
            }
        elif "questions" in body:
            # Text selector fallback answers the same choice question as Jev.
            criteria = body["questions"]["next_action"]["criteria"]
            if active_task["application"] == "calculator":
                label = ("7", "Multiply", "8", "Equals")[min(fake_index, 3)]
                fake_index += 1
                key = next(
                    (
                        name
                        for name, value in criteria.items()
                        if isinstance(value, dict) and value.get("label") == label
                    ),
                    "none",
                )
            else:
                fake_index += 1
                key = next(
                    (
                        name
                        for name, value in criteria.items()
                        if isinstance(value, dict) and value.get("operation") == "fill"
                    ),
                    "none",
                )
            content = {"choice": key}
        else:
            label = ("7", "Multiply", "8", "Equals")[min(fake_index, 3)]
            choice = next(
                key
                for key, value in body["actions"].items()
                if value.get("label") == label
            )
            fake_index += 1
            content = {"kind": "candidate", "candidate_id": choice}
        return text_http.Response(
            200,
            json={
                "id": "s5-text",
                "object": "chat.completion",
                "created": 1,
                "model": text_model["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(content),
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                },
            },
        )

    class PilotCapture(Capture):
        async def request(self, call_id, request):
            await super().request(call_id, request)
            self.calls[call_id]["provider"] = (
                "jev" if str(request.url) == jev_endpoint else "text"
            )

        async def response(self, call_id, response):
            await super().response(call_id, response)
            if "choices" in response:
                self.calls[call_id]["response"]["choices"] = response["choices"]

    class Policy(BenchmarkModelPolicy):
        def __init__(self, task: PilotTask, arm: str):
            jev_model = frozen["models"]["jev"]
            super().__init__(
                ledger,
                (
                    ContextWindowContract(
                        jev_endpoint,
                        jev_model["model"],
                        TokenAllowance(
                            jev_model["input_ceiling"],
                            jev_model["output_ceiling"],
                            jev_model["input_price"],
                            jev_model["output_price"],
                        ),
                        "Frozen Jev conservative token-price contract",
                        output_cap_required=False,
                    ),
                    ContextWindowContract(
                        text_endpoint,
                        text_model["model"],
                        TokenAllowance(
                            text_model["input_ceiling"],
                            text_model["output_ceiling"],
                            text_model["input_price"],
                            text_model["output_price"],
                        ),
                        "Inherited S3 Qwen conservative reservation; output capped at 2048",
                    ),
                ),
            )
            self.limits = {
                "jev": task["max_decisions"] * int(arm == "J"),
                "text": task["max_decisions"] + frozen["advisor_call_limit"] + 1,
            }
            self.counts: Counter[str] = Counter()

        def reserve(self, call_id, request):
            name = "jev" if str(request.url) == jev_endpoint else "text"
            if self.counts[name] >= self.limits[name]:
                self.ledger.stop("trial_call_limit")
                raise SpendLimitExceeded("trial_call_limit")
            super().reserve(call_id, request)
            self.counts[name] += 1

    a_control = SpendControl(
        ledger,
        SpendLimit(
            frozen["trial_limits"]["tokens"], frozen["trial_limits"]["nano_usd"]
        ),
        (
            ContextWindowContract(
                a_model["url"],
                a_model["model"],
                TokenAllowance(
                    a_model["input_ceiling"],
                    a_model["output_ceiling"],
                    a_model["input_price"],
                    a_model["output_price"],
                ),
                "Production computer_use profile pin; conservative reservation",
            ),
        ),
    )
    a_driver = None
    report: dict[str, Any] = {
        "revision": frozen["revision"],
        "mode": mode,
        "sha256": approved,
        "completed": False,
        "rows": rows,
    }

    async def audit_record(record: Any) -> None:
        audits.append(asdict(record))

    with ExitStack() as stack:
        stack.enter_context(
            patch.dict(
                os.environ,
                {"TANK_S4_JEV_KEY": credential if mode == "live" else "fake-s5-pilot"},
            )
        )
        if mode == "fake":
            stack.enter_context(s4_ax.fake_model_http(fake_decision))
            # Patch both namespaces: SDK-built httpx clients resolve the default
            # transport through httpx._client, not the package re-export.
            for target in (
                "httpx.AsyncHTTPTransport",
                "httpx._client.AsyncHTTPTransport",
            ):
                stack.enter_context(
                    patch(
                        target,
                        lambda *args, **kwargs: text_http.MockTransport(fake_text),
                    )
                )
        journal = stack.enter_context((output / "rows.jsonl").open("x"))
        audits_file = stack.enter_context((output / "audit.jsonl").open("x"))
        written = 0
        try:
            for row in rows:
                load_freeze(output, approved)
                task = tasks[row["task_id"]]
                active_task, fake_index, fake_escalated = task, 0, False
                owner = OwnedApplication(task)
                capture, audits = PilotCapture(), []
                observer = PilotObserver()
                started = time.monotonic()
                row.update(status="started", arm_config=ARM_CONFIGS.get(row["arm"]))
                if row["arm"] != "A":
                    ledger.start_trial(
                        row["trial"],
                        SpendLimit(
                            frozen["trial_limits"]["tokens"],
                            frozen["trial_limits"]["nano_usd"],
                        ),
                    )
                try:
                    config = owner.start()
                    row["binding"] = config.model_dump(mode="json")
                    row["setup_actions"] = owner.setup_actions
                    if row["arm"] == "A":
                        if a_driver is None:
                            a_driver = create_a_driver(a_control)
                        trace = TraceSink(output / "trials" / row["trial"])
                        driver_result = await a_driver.run(
                            frozen["prompts"][task["id"]],
                            trace,
                            timeout_s=frozen["seconds_per_task"],
                            max_steps=A_CONFIG["max_steps"],
                        )
                        row["driver"] = _a_driver_result(driver_result)
                        row["spend_trial"] = str(
                            (output / "trials" / row["trial"]).resolve()
                        )
                        row["model_action_executed"] = driver_result.primitives > 0
                    else:
                        app_config = AppConfig.from_raw_dict(
                            {
                                "llm": {
                                    "default": {
                                        "model": "unused",
                                        "api_key": "unused",
                                        "base_url": "https://unused.invalid/v1",
                                    },
                                    "advisor": {
                                        "model": text_model["model"],
                                        "api_key": advisor_credential
                                        if mode == "live"
                                        else "fake-advisor",
                                        "base_url": text_endpoint.removesuffix(
                                            "/chat/completions"
                                        ),
                                        "max_tokens": text_model["output_ceiling"],
                                        "temperature": 0,
                                        "extra_body": {"enable_thinking": False},
                                    },
                                },
                                "decision_models": {
                                    "jev": {
                                        "url": jev_endpoint,
                                        "model": frozen["models"]["jev"]["model"],
                                        "credential_env": "TANK_S4_JEV_KEY",
                                    }
                                },
                                "subagents": {
                                    "agent-computer-use:agent": {
                                        "config": {
                                            "macos": frozen["macos_policies"][
                                                task["id"]
                                            ],
                                            **ARM_CONFIGS[row["arm"]],
                                        }
                                    }
                                },
                            }
                        )
                        runner = AgentRunner(
                            MagicMock(spec=LLM),
                            MagicMock(spec=ToolManager),
                            Bus(),
                            ToolApprovalPolicy(computer_mode="allow"),
                            PendingToolCallStore(),
                            {
                                definition.name: definition
                                for definition in definitions.values()
                            },
                            registry=registry,
                            app_config=app_config,
                            desktop_resource=resource,
                        )
                        outputs = [
                            item
                            async for item in runner.run_agent(
                                definitions[row["arm"]],
                                [
                                    {
                                        "role": "user",
                                        "content": frozen["prompts"][task["id"]],
                                    }
                                ],
                                task_id=row["trial"],
                                task_input=frozen["task_inputs"][task["id"]],
                                authorization=SubAgentAuthorization(
                                    frozenset({"desktop", "network"})
                                ),
                                model_policy=Policy(task, row["arm"]),
                                model_capture=capture,
                                audit=audit_record,
                                observer=observer,
                                max_actions=task["max_decisions"] + 1,
                                max_observations=1 + 3 * task["max_decisions"],
                                deadline=time.monotonic() + frozen["seconds_per_task"],
                                desktop_cleanup=MacOSInputCleanup(),
                            )
                        ]
                        result = next(
                            item.metadata["task_result"]
                            for item in outputs
                            if "task_result" in item.metadata
                        )
                        row["result"] = result
                        row["spend_trial"] = row["trial"]
                        proposals = {
                            (event.get("candidate_set_id"), event.get("action_id"))
                            for event in observer.events
                            if event["kind"] == "computer_use_proposal"
                            and event.get("action_id")
                        }
                        executed = {
                            (r["candidate_set_id"], r["action_id"])
                            for r in result["details"]["receipts"]
                            if r["status"] != "not_sent"
                        }
                        row["model_action_executed"] = bool(proposals & executed)
                    values = owner.read_values()
                    row["independent_values"] = values
                    row["strict"], row["partial"], row["rule_violation"] = score_case(
                        task["application"], values
                    )
                    row["status"] = "finished"
                except asyncio.CancelledError:
                    ledger.stop("cancelled")
                    row["status"] = "cancelled"
                    raise
                except Exception as exc:
                    row.update(
                        status="error", error_type=type(exc).__name__, error=str(exc)
                    )
                finally:
                    try:
                        row["application_cleanup"] = owner.close()
                    except Exception as exc:
                        row["application_cleanup"] = {
                            "confirmed": False,
                            "error": str(exc),
                        }
                    settled_now = settled(row, ledger.snapshot()["stop_reason"])
                    if row["arm"] != "A":
                        ledger.finish_trial()
                    row["passed"] = bool(
                        row["status"] == "finished"
                        and row["strict"]
                        and row.get("model_action_executed")
                        and row["application_cleanup"].get("confirmed")
                    )
                    row.update(
                        calls=capture.calls,
                        audit=audits,
                        events=observer.events,
                        elapsed_ms=(time.monotonic() - started) * 1000,
                    )
                    journal.write(
                        json.dumps(row, ensure_ascii=False, default=str) + "\n"
                    )
                    journal.flush()
                    written += 1
                    for record in audits:
                        audits_file.write(
                            json.dumps(record, ensure_ascii=False, default=str) + "\n"
                        )
                    audits_file.flush()
                    (output / "result.json").write_text(
                        json.dumps(
                            {**report, "spend": ledger.snapshot()},
                            ensure_ascii=False,
                            default=str,
                            indent=2,
                        )
                        + "\n"
                    )
                print(
                    json.dumps(
                        {
                            "trial": row["trial"],
                            "status": row["status"],
                            "strict": row["strict"],
                            "passed": row["passed"],
                            "error": row.get("error"),
                        }
                    ),
                    flush=True,
                )
                if not settled_now:
                    ledger.stop("s5_trial_unsettled")
                    break
            else:
                report["completed"] = all(row["status"] == "finished" for row in rows)
        finally:
            for row in rows[written:]:
                journal.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            report["spend"] = ledger.snapshot()
            report["summary"] = summarize(rows, report["spend"])
            report["paired"] = paired_results(
                rows, report["spend"], report["completed"]
            )
            report["conclusion"] = conclusion(
                report["summary"], completed=report["completed"]
            )
            report["fake_http_requests"] = fake_received
            report["external_model_requests"] = (
                sum(len(row.get("calls", {})) for row in rows)
                + sum(row.get("driver", {}).get("llm_calls", 0) for row in rows)
                if mode == "live"
                else 0
            )
            ledger.close()
            with (output / "result.json").open("w") as file:
                json.dump(report, file, ensure_ascii=False, default=str, indent=2)
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", choices=("fake", "live"))
    parser.add_argument("--approved-sha256")
    args = parser.parse_args()
    if args.run is None:
        frozen = prepare(args.output)
        print(
            json.dumps(
                {
                    key: frozen[key]
                    for key in ("sha256", "request_limit", "nano_usd_limit")
                }
            )
        )
    else:
        if not args.approved_sha256:
            parser.error("Execution requires the frozen recipe digest")
        load_freeze(args.output, args.approved_sha256)
        credential, advisor_credential = "", ""
        if args.run == "live":
            from dotenv import dotenv_values

            backend = Path(__file__).resolve().parents[2]
            credential = (
                os.environ.get("TYPESAFE_API_KEY")
                or dotenv_values(backend / "core/.env").get("TYPESAFE_API_KEY")
                or ""
            )
            advisor_credential = (
                os.environ.get("BAILIAN_API_KEY")
                or dotenv_values(backend / "core/.env").get("BAILIAN_API_KEY")
                or ""
            )
        result = asyncio.run(
            run_batch(
                args.output,
                args.approved_sha256,
                mode=args.run,
                credential=credential,
                advisor_credential=advisor_credential,
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
