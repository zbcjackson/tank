"""Frozen synthetic selector replay. Preparation is offline; live runs require its digest."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
from contextlib import ExitStack
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, TextIO

from agent_computer_use.action_builder import ActionBuilder
from agent_computer_use.contracts import Action, Element, Fact, GoalContract, Snapshot, snapshot_json

FIXTURES = Path(__file__).parent / "fixtures/s3/cases.json"
STAGES = ("d2", "action")
ARMS = ("rules", "jev", "qwen")
MODELS = {
    "jev": {"model": "jev-1.13.0", "url": "https://api.typesafe.ai/v1/systemone",
            "input_ceiling": 65536, "output_ceiling": 65536, "input_price": 42, "output_price": 0},
    "qwen": {"model": "qwen3.7-flash-2026-07-15",
             "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
             "input_ceiling": 991808, "output_ceiling": 128,
             "input_price": 165, "output_price": 660},
}
THRESHOLDS = (0.0, 0.5, 0.7, 0.9, 1.01)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def code_hashes() -> dict[str, str]:
    from agent_computer_use import contracts, jev
    from tank_backend.llm import model_transport, task_json_model
    from tank_backend.benchmarks import model_policy, spend_ledger

    paths = [Path(__file__), Path(inspect.getfile(ActionBuilder))]
    paths.extend(Path(inspect.getfile(module)) for module in (contracts, jev, model_transport, task_json_model,
                                                           model_policy, spend_ledger))
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def public_case(item: dict[str, Any]) -> dict[str, Any]:
    """Build using observations and goals only. The independent label is never consulted."""
    goal = GoalContract.from_input(item["goal"])
    raw = item["snapshot"]
    snapshot = Snapshot(
        raw["observation_id"], raw["scope"], raw["generation"],
        tuple(Element(**{**element, "actions": tuple(element["actions"])})
              for element in raw["elements"]),
        tuple(Fact(**fact) for fact in raw["facts"]), complete=raw["complete"],
    )
    actions = ActionBuilder().build("goal", 1, goal, goal.milestones[0], snapshot)
    ordered = sorted(actions.actions, key=lambda action: digest([item["id"], action.target_ref]))
    actions = replace(actions, binding=replace(actions.binding, candidate_set_id="candidates"),
                      actions=tuple(Action(f"a{i}", action.target_ref, action.operation, action.value)
                                    for i, action in enumerate(ordered)))
    return {"goal": goal.model_dump(mode="json"), "snapshot": snapshot_json(snapshot),
            "actions": asdict(actions)}


def freeze_inputs() -> dict[str, Any]:
    source = json.loads(FIXTURES.read_text())
    cases = [{key: value for key, value in item.items() if key not in {"goal", "snapshot"}}
             | {"public": public_case(item)} for item in source["cases"]]
    freeze = {"revision": source["revision"], "cases": cases, "models": MODELS,
              "stages": STAGES, "arms": ARMS, "thresholds": THRESHOLDS,
              "dataset_sha256": hashlib.sha256(FIXTURES.read_bytes()).hexdigest(),
              "code_hashes": code_hashes(), "nano_usd_limit": 250_000_000,
              "request_limit": sum(c["public"]["actions"]["reason"] == "jev_eligible"
                                   and not c["public"]["actions"]["truncated"] for c in cases) * 4}
    freeze = json.loads(json.dumps(freeze))
    freeze["sha256"] = digest(freeze)
    return freeze


def prepare(output: Path) -> dict[str, Any]:
    freeze = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(freeze, ensure_ascii=False, indent=2))
    return freeze


def load_freeze(output: Path, approved_digest: str) -> dict[str, Any]:
    freeze = json.loads((output / "freeze.json").read_text())
    body = {key: value for key, value in freeze.items() if key != "sha256"}
    if (freeze != freeze_inputs() or freeze["sha256"] != approved_digest or digest(body) != approved_digest
            or freeze["code_hashes"] != code_hashes()
            or freeze["dataset_sha256"] != hashlib.sha256(FIXTURES.read_bytes()).hexdigest()):
        raise ValueError("Frozen inputs or implementation changed; prepare and approve a new batch")
    return freeze


def score(case: dict[str, Any], choice: str | None, status: str) -> dict[str, Any]:
    actions = case["public"]["actions"]["actions"]
    selected = next((action for action in actions if action["id"] == choice), None)
    gold = case["gold"]
    recall = (any(action["target_ref"] == gold["target_ref"] for action in actions)
              if "target_ref" in gold else None)
    correct = (selected is not None and selected["target_ref"] == gold.get("target_ref")
               if "target_ref" in gold else choice == gold.get("control"))
    if status in {"host_blocked", "not_run"}:
        correct = None
    return {"candidate_recall": recall, "correct": correct,
            "selection_error": recall is not False and status not in {"host_blocked", "not_run"}
            and not correct,
            "dangerous_action": selected is not None and not correct,
            "selected_action": selected is not None}


def public_question(case: dict[str, Any], stage: str) -> dict[str, Any]:
    from agent_computer_use.jev import CONTROLS

    public = case["public"]
    elements = {element["ref"]: element for element in public["snapshot"]["elements"]}
    options = {}
    for action in public["actions"]["actions"]:
        element = elements[action["target_ref"]]
        options[action["id"]] = (action if stage == "action" else {
            "target_ref": element["ref"], "role": element["role"], "label": element["label"],
        })
    options.update(CONTROLS)
    return {"state": {"goal": public["goal"], "snapshot": public["snapshot"],
                      "binding": public["actions"]["binding"]},
            "instructions": ("Select one complete bound action or a control option." if stage == "action"
                             else "Select the target for the declared milestone or a control option."),
            "criteria": options}


def action_set(case: dict[str, Any]):
    from agent_computer_use.contracts import ActionSet, Binding

    raw = case["public"]["actions"]
    return ActionSet(Binding(**raw["binding"]), tuple(Action(**action) for action in raw["actions"]),
                     raw["reason"], raw["total_candidates"], raw["truncated"])


def calibrate(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Fixed zero-calibration-error rule; holdout labels never participate."""
    result = {}
    categories = sorted({row["category"] for row in rows if row["split"] == "calibration"})
    for stage in STAGES:
        for category in categories:
            candidates = [row for row in rows if row["split"] == "calibration"
                          and row["stage"] == stage and row["category"] == category
                          and row["arm"] == "jev" and row["status"] == "returned"
                          and row["selected_action"]]
            result[f"{stage}/{category}"] = next((threshold for threshold in THRESHOLDS if not any(
                row["confidence"] >= threshold and row["dangerous_action"] for row in candidates
            )), 1.01) if candidates else 1.01

    return result


async def run_replay(
    output: Path, approved_digest: str, credentials: dict[str, str],
) -> dict[str, Any]:
    import asyncio
    import time

    from agent_computer_use.jev import JevChoiceRoute, parse_choice
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.agents.task_runtime import ExecutionRecord
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance
    from tank_backend.llm.model_transport import ChatCompletionsRoute

    freeze = load_freeze(output, approved_digest)
    if set(credentials) != {"jev", "qwen"} or not all(value.strip() for value in credentials.values()):
        raise ValueError("Both model credentials are required")
    # Exclusive journal creation refuses accidental restarts against the same approved batch.
    ledger = SpendLedger(SpendLimit(100_000_000, freeze["nano_usd_limit"]),
                         request_limit=freeze["request_limit"], journal=output / "spend.jsonl")
    contracts = tuple(ContextWindowContract(
        config["url"], config["model"], TokenAllowance(
            config["input_ceiling"], config["output_ceiling"],
            config["input_price"], config["output_price"],
        ), "Frozen official context ceilings and upper-tier USD rates, 2026-10-03",
        output_cap_required=arm == "qwen",
    ) for arm, config in MODELS.items())
    policy = BenchmarkModelPolicy(ledger, contracts)
    rows: list[dict[str, Any]] = []
    files = ExitStack()
    files.callback(ledger.close)
    stop = False
    thresholds: dict[str, float] = {}
    try:
        audit_file = files.enter_context((output / "audit.jsonl").open("x"))
        rows_file = files.enter_context((output / "rows.jsonl").open("x"))
        for split in ("calibration", "holdout"):
            for stage in STAGES:
                for index, case in enumerate(c for c in freeze["cases"] if c["split"] == split):
                    question = public_question(case, stage)
                    actions = case["public"]["actions"]
                    # Alternate model order; rules never consume a request.
                    arms = ("rules", "jev", "qwen") if index % 2 == 0 else ("rules", "qwen", "jev")
                    for arm in arms:
                        row: dict[str, Any] = {
                            "case_id": case["id"], "category": case["category"], "split": split,
                            "stage": stage, "arm": arm, "public_sha256": digest(question),
                            "status": "not_run", "choice": None, "confidence": None,
                            "elapsed_ms": None, "usage": {},
                        }
                        if actions["reason"] == "rules_unique":
                            row.update(status="rule", choice=actions["actions"][0]["id"])
                        elif actions["reason"] != "jev_eligible" or actions["truncated"]:
                            row.update(status="host_blocked", reason=actions["reason"])
                        elif arm == "rules":
                            row.update(status="rule", choice="escalate")
                        elif not stop:
                            trial = f"{split}-{stage}-{case['id']}-{arm}"
                            ledger.start_trial(trial, SpendLimit(2_000_000, freeze["nano_usd_limit"]))
                            async def audit(record: ExecutionRecord) -> None:
                                await asyncio.to_thread(append_json, audit_file, asdict(record))

                            ctx = SubAgentContext(
                                SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(),
                                asyncio.Event(), deadline=time.monotonic() + 45, model_policy=policy, audit=audit,
                            )
                            config = MODELS[arm]
                            route = (JevChoiceRoute(config["url"], config["model"], arm)
                                     if arm == "jev" else ChatCompletionsRoute(
                                         config["url"], config["model"], arm, max_output_tokens=128,
                                         extra_parameters={"enable_thinking": False},
                                     ))
                            ctx.runtime.configure_json_model(trial, route, credential=credentials[arm])
                            model = ctx.runtime.json_model
                            assert model is not None
                            request: dict[str, Any] = (
                                {"model": config["model"], "state": question["state"],
                                 "questions": {"next_action": {"type": "choice",
                                                               "instructions": question["instructions"],
                                                               "criteria": question["criteria"]}}}
                                if arm == "jev" else {
                                    "model": config["model"], "temperature": 0, "max_tokens": 128,
                                    "enable_thinking": False,
                                    "messages": [{"role": "system", "content":
                                                  'Choose one offered option. Return only JSON '
                                                  '{"choice":"option id"}. Do not execute actions.'},
                                                 {"role": "user", "content": json.dumps(question,
                                                  ensure_ascii=False, sort_keys=True)}],
                                }
                            )
                            row["request"] = request
                            started = time.monotonic()
                            try:
                                response = await model.request(request)
                                row["response"] = response
                                if arm == "jev":
                                    decision = parse_choice(response, action_set(case), config["model"])
                                    row["choice"] = (decision.candidate_id if decision.choice == "candidate"
                                                     else decision.choice)
                                    answers = response["answers"]
                                    assert isinstance(answers, dict)
                                    row["confidence"] = answers["next_action"]["confidence"]
                                else:
                                    row["choice"] = parse_qwen(
                                        response, question["criteria"], config["model"],
                                    )
                                row["status"] = "returned"
                            except Exception as exc:
                                row.update(status="invalid", error_type=type(exc).__name__)
                            finally:
                                row["elapsed_ms"] = (time.monotonic() - started) * 1000
                                row["usage"] = ctx.budget.snapshot()
                                await ctx.runtime.aclose()
                            if ctx.runtime.audit_failed:
                                ledger.stop("audit_failed")
                            stop = bool(ctx.budget.unknown_calls or ledger.snapshot()["stop_reason"])
                            if not stop:
                                ledger.finish_trial()
                        row.update(score(case, row["choice"], row["status"]))
                        rows.append(row)
                        append_json(rows_file, row)
            if split == "calibration":
                thresholds = calibrate(rows)
                (output / "thresholds.json").write_text(json.dumps({
                    "freeze_sha256": approved_digest, "thresholds": thresholds,
                    "calibration_sha256": digest(rows),
                }, indent=2))
        apply_thresholds(rows, freeze["cases"], thresholds)
        report = {"freeze_sha256": approved_digest, "rows": rows, "summary": summarize(rows),
                  "thresholds": thresholds, "spend": ledger.snapshot()}
        (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        return report
    finally:
        files.close()


def parse_qwen(response: dict[str, Any], options: dict[str, Any], model: str) -> str:
    from tank_backend.llm.model_transport import json_object

    if response.get("model") != model:
        raise ValueError("unexpected model version")
    choices = response.get("choices")
    if (not isinstance(choices, list) or len(choices) != 1
            or not isinstance(choices[0], dict) or choices[0].get("finish_reason") != "stop"):
        raise ValueError("incomplete completion")
    message = choices[0].get("message")
    if (not isinstance(message, dict) or not isinstance(message.get("content"), str)
            or any(message.get(field) for field in ("tool_calls", "function_call", "refusal"))):
        raise ValueError("not a selection")
    answer = json_object(message["content"])
    if (set(answer) != {"choice"} or not isinstance(answer["choice"], str)
            or answer["choice"] not in options):
        raise ValueError("unknown choice")
    return answer["choice"]


def append_json(file: TextIO, value: object) -> None:
    file.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
    file.flush()
    os.fsync(file.fileno())


def apply_thresholds(
    rows: list[dict[str, Any]], cases: list[dict[str, Any]], thresholds: dict[str, float],
) -> None:
    by_id = {case["id"]: case for case in cases}
    for row in rows:
        choice = row["choice"]
        if (row["arm"] == "jev" and row["status"] == "returned" and row["selected_action"]
                and row["confidence"] < thresholds[f"{row['stage']}/{row['category']}"]):
            choice = "escalate"
        row["accepted_choice"] = choice
        row["accepted"] = score(by_id[row["case_id"]], choice, row["status"])


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from statistics import median

    summary = {}
    for split in ("calibration", "holdout"):
        for stage in STAGES:
            for arm in ARMS:
                group = [row for row in rows if (row["split"], row["stage"], row["arm"])
                         == (split, stage, arm)]
                latencies = [row["elapsed_ms"] for row in group if row["elapsed_ms"] is not None]
                summary[f"{split}/{stage}/{arm}"] = {
                    "n": len(group), "host_blocked": sum(r["status"] == "host_blocked" for r in group),
                    "not_run": sum(r["status"] == "not_run" for r in group),
                    "invalid": sum(r["status"] == "invalid" for r in group),
                    "correct": sum(r["correct"] is True for r in group),
                    "selection_errors": sum(r["selection_error"] for r in group),
                    "recall_targets": sum(r["candidate_recall"] is not None for r in group),
                    "recall_misses": sum(r["candidate_recall"] is False for r in group),
                    "raw_actions": sum(r["selected_action"] for r in group),
                    "raw_wrong_actions": sum(r["dangerous_action"] for r in group),
                    "accepted_actions": sum(r["accepted"]["selected_action"] for r in group),
                    "accepted_wrong_actions": sum(r["accepted"]["dangerous_action"] for r in group),
                    "latency_n": len(latencies), "median_ms": median(latencies) if latencies else None,
                    "known_tokens": sum(r["usage"].get("total_tokens", 0) for r in group),
                }
    return summary


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approved-sha256")
    args = parser.parse_args()
    if not args.live:
        if args.approved_sha256:
            parser.error("approval digest is only used with --live")
        frozen = prepare(args.output)
        print(json.dumps({"sha256": frozen["sha256"], "cases": len(frozen["cases"]),
                          "max_requests": frozen["request_limit"], "max_usd": 0.25,
                          "real_requests": 0}))
    else:
        if not args.approved_sha256:
            parser.error("--live requires the separately approved freeze digest")
        load_freeze(args.output, args.approved_sha256)
        from dotenv import load_dotenv
        from tank_backend.config.app_config import AppConfig

        backend = Path(__file__).resolve().parents[2]
        load_dotenv(backend / "core/.env")
        profile = AppConfig.load(backend / "core/config.yaml").llm_profiles["computer_use"]
        if (profile.model != MODELS["qwen"]["model"]
                or profile.base_url.rstrip("/") + "/chat/completions" != MODELS["qwen"]["url"]):
            raise ValueError("Configured comparison profile differs from frozen model/destination")
        result = asyncio.run(run_replay(args.output, args.approved_sha256, {
            "jev": os.environ.get("TYPESAFE_API_KEY", ""), "qwen": profile.api_key,
        }))
        print(json.dumps({"freeze_sha256": result["freeze_sha256"],
                          "spend": result["spend"]["batch"],
                          "stop_reason": result["spend"]["stop_reason"]}))
        raise SystemExit(1 if result["spend"]["stop_reason"] else 0)
