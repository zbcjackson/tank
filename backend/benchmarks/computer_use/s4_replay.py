"""Frozen Calculator decision probes through task-owned SDKs, with no desktop executor."""

from __future__ import annotations

import copy
import asyncio
import gzip
import hashlib
import inspect
import json
import time
from contextlib import ExitStack
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from statistics import median
from typing import Any

from pydantic import TypeAdapter

from agent_computer_use.contracts import (
    Action, ActionDetails, ActionSet, Binding, DispatchReceipt, ExecutionStep, Fact, GoalContract,
    GoalProgress, ObservedChange, Snapshot, ValueChange,
)
from benchmarks.computer_use import s4_ax
from benchmarks.computer_use.s3_replay import MODELS, digest

SOURCE = Path(__file__).parent / "reports/20261008-s4-native-advisor/live/result.json.gz"
SOURCE_HASH = "1cd21575708832567862fb2096f96109ae06067a30e6f6a36582ecedec25d278"
ARMS = ("grounding", "archived", "current", "advisor")
SPEC = (("after-7", 0, 1, "7", "Multiply", "7×"),
        ("after-operator", 0, 6, "7×", "8", "7×8"),
        ("before-equals", 0, 7, "7×8", "Equals", "56"),
        ("repair-787", 1, 3, "787", "Clear", "0"))


def archived_call(call: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    request, response = call["request"], call["response"]
    if "questions" in request:
        return {"question": copy.deepcopy({key: request[key] for key in ("state", "questions")}),
                "choice": response["answers"]["next_action"]["choice"], "source": "selector"}
    payload = json.loads(request["messages"][1]["content"])
    answer = json.loads(response["choices"][0]["message"]["content"])
    if answer["kind"] != "candidate":
        raise ValueError("Source archive must contain candidate advice")
    controls = {key: value for key, value in template["criteria"].items() if isinstance(value, str)}
    return {"question": {"state": payload["state"], "questions": {"next_action": {
        **template, "criteria": {**payload["actions"], **controls}}}},
        "choice": answer["candidate_id"], "source": "advisor"}


def snapshot_from_state(state: dict[str, Any]) -> Snapshot:
    raw = copy.deepcopy(state["snapshot"])
    defaults = raw.pop("element_defaults", {})
    raw["elements"] = [{**defaults, **element} for element in raw["elements"]]
    return TypeAdapter(Snapshot).validate_json(json.dumps(raw))


def build_cases() -> list[dict[str, Any]]:
    encoded = SOURCE.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != SOURCE_HASH:
        raise ValueError("Source archive hash changed")
    archive = json.loads(gzip.decompress(encoded))
    template = archive["rows"][0]["calls"][0]["request"]["questions"]["next_action"]
    cases = []
    for case_id, source_row, position, display, preferred, next_display in SPEC:
        row = archive["rows"][source_row]
        calls = [archived_call(call, template) for call in row["calls"]]
        receipts = {item["action_id"]: item for item in row["result"]["details"]["receipts"]}
        evidence = {item["action_id"]: item["observation_id"] for item in row["result"]["details"]["evidence"]
                    if "action_id" in item}
        question = calls[position]["question"]
        state = question["state"]
        snapshot = snapshot_from_state(state)
        if Fact(key="ax:value:result", value=display) not in snapshot.facts:
            raise ValueError("Archived state differs from the declared diagnostic")
        elements = {element.ref: element for element in snapshot.elements}
        actions, details = [], []
        for candidate_id, item in question["questions"]["next_action"]["criteria"].items():
            if not isinstance(item, dict):
                continue
            element = elements[item["target_ref"]]
            actions.append(Action(candidate_id, element.ref, item["operation"], item["value"]))
            details.append(ActionDetails(candidate_id, element.role, item["label"], element.ancestors,
                element.value, item["input_key"], tuple(Fact(**value) for value in item["effect"]),
                tuple(ValueChange(**value) for value in item["changes"])))
        history = []
        for index, previous in enumerate(calls[:position]):
            before = previous["question"]["state"]
            after = calls[index + 1]["question"]["state"]
            chosen = previous["choice"]
            receipt = receipts[chosen]
            if (receipt["status"] != "sent" or evidence[chosen] != after["snapshot"]["observation_id"]
                    or receipt["candidate_set_id"] != before["binding"]["candidate_set_id"]
                    or chosen not in after["progress"]["verified_actions"]):
                raise ValueError("Historical action/readback link is unverified")
            candidate = previous["question"]["questions"]["next_action"]["criteria"][chosen]
            target = next(element for element in snapshot_from_state(before).elements
                          if element.ref == candidate["target_ref"])
            old_values = {fact["key"]: fact["value"] for fact in before["snapshot"]["facts"]}
            new_values = {fact["key"]: fact["value"] for fact in after["snapshot"]["facts"]}
            changes = tuple(ObservedChange(key, old_values.get(key), new_values.get(key))
                            for key in sorted(old_values.keys() | new_values.keys())
                            if old_values.get(key) != new_values.get(key))
            history.append(ExecutionStep(index + 1, chosen, candidate["operation"], target.role,
                target.label, target.ancestors, candidate["value"], previous["source"],
                before["snapshot"]["observation_id"], after["snapshot"]["observation_id"],
                "sent", "verified", changes))
        progress = TypeAdapter(GoalProgress).validate_json(json.dumps(state["progress"]))
        progress = replace(progress, recent_steps=tuple(history[-10:]))
        action_set = ActionSet(Binding(**state["binding"]), tuple(actions), "jev_eligible",
                               len(actions), details=tuple(details), progress=progress)
        goal = GoalContract.from_input(state["goal"])
        grounded = GoalContract.from_input({**goal.model_dump(mode="json"),
            "intent": f"Click the observed button labelled {preferred!r} once.",
            "objective": f"Click the observed button labelled {preferred!r} once.",
            "completion": [{"key": "ax:value:result", "value": next_display}]})
        if len(actions) != 44 or preferred not in {detail.label for detail in details}:
            raise ValueError("Complete candidate coverage is required")
        cases.append({"id": case_id, "display": display, "source_row": row["case_id"], "source_call": position + 1,
            "prior_bindings": [previous["question"]["state"]["binding"] for previous in calls[:position]],
            "prior_receipts": [{"action_id": previous["choice"], "status": receipts[previous["choice"]]["status"]}
                               for previous in calls[:position]],
            "archived_question_derived": calls[position]["source"] == "advisor",
            "preferred": preferred, "alternatives": ["Delete"] if preferred == "Clear" else [],
            "goal": goal.model_dump(mode="json"), "grounding_goal": grounded.model_dump(mode="json"),
            "snapshot": TypeAdapter(Snapshot).dump_python(snapshot, mode="json"),
            "actions": TypeAdapter(ActionSet).dump_python(action_set, mode="json"),
            "archived_question": question})
    return cases


def freeze_inputs() -> dict[str, Any]:
    from tank_backend.llm import llm, model_data, profile
    root = Path(__file__).resolve().parents[2]
    sources = s4_ax.freeze_inputs()["source_sha256"].copy()
    for path in (Path(__file__), root / "uv.lock", *(Path(inspect.getfile(module)) for module in (llm, model_data, profile))):
        sources[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    cases = build_cases()
    schedule = []
    for repeat in range(3):
        for offset in range(4):
            case = cases[(offset + repeat) % 4]
            shift = (offset + repeat) % 4
            schedule.extend({"case_id": case["id"], "arm": arm, "repeat": repeat}
                            for arm in (*ARMS[shift:], *ARMS[:shift]))
    frozen = {"revision": "s4-frozen-diagnostic-1", "cases": cases, "schedule": schedule,
        "source_archive_sha256": SOURCE_HASH, "source_sha256": sources,
        "versions": {name: version(name) for name in ("typesafe-sdk", "openai", "httpx", "httpx2")},
        "models": {"jev": MODELS["jev"], "advisor": {**MODELS["qwen"], "output_ceiling": 2048}},
        "request_limit": 60, "nano_usd_limit": 250_000_000, "seconds_per_trial": 60,
        "lifecycle": "fresh task and lazy SDK clients per row; no warmups, desktop resources or SDK retries",
        "boundary": "No desktop operations; known archived states, not holdout or end-to-end task success",
        "scoring": "preferred action / repair alternative / handoff / other action / invalid proposal",
        "stop_policy": "operational errors, unknown usage, cancellation or cleanup failure stop; known semantic misses remain in denominator"}
    frozen["sha256"] = digest(frozen)
    return frozen


def prepare(output: Path) -> dict[str, Any]:
    frozen = freeze_inputs()
    output.mkdir(parents=True, exist_ok=False)
    (output / "freeze.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    return frozen


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    frozen = freeze_inputs()
    if approved != frozen["sha256"] or json.loads((output / "freeze.json").read_text()) != frozen:
        raise ValueError("Diagnostic freeze changed; prepare a new recipe")
    return frozen


class NoDesktop:
    async def observe(self, *args):
        raise AssertionError("Diagnostic replay has no desktop observer")

    async def is_current(self, *args):
        raise AssertionError("Diagnostic replay has no desktop references")

    async def dispatch(self, *args):
        raise AssertionError("Diagnostic replay has no desktop executor")


def classify(case: dict[str, Any], arm: str, label: str | None, control: str | None) -> str:
    if control is not None:
        return "handoff"
    if label == case["preferred"]:
        return "preferred"
    if arm != "grounding" and label in case["alternatives"]:
        return "repair_alternative"
    return "other_action"


async def select_frozen(case: dict[str, Any], arm: str, context, row: dict[str, Any]) -> None:
    from agent_computer_use.advisor import LLMAdvisor
    from agent_computer_use.controller import ComputerUseController
    from agent_computer_use.jev import JevSelector
    from tank_backend.agents.subagent import SubAgentRequest, SubAgentStopped

    goal = GoalContract.from_input(case["grounding_goal"] if arm == "grounding" else case["goal"])
    snapshot = TypeAdapter(Snapshot).validate_json(json.dumps(case["snapshot"]))
    actions = TypeAdapter(ActionSet).validate_json(json.dumps(case["actions"]))
    label = control = None
    if arm == "archived":
        packet = case["archived_question"]
        question = packet["questions"]["next_action"]
        answer = await context.runtime.decision_model.choose(
            state=packet["state"], instructions=question["instructions"], options=question["criteria"])
        criterion = question["criteria"][answer.choice]
        label = criterion["label"] if isinstance(criterion, dict) else None
        control = answer.choice if isinstance(criterion, str) else None
    else:
        selector = JevSelector()
        decision = None
        if arm == "advisor":
            channel = NoDesktop()
            controller = ComputerUseController(channel, channel, selector=selector, advisor=LLMAdvisor(allow_focus=True))
            controller.progress = actions.progress or GoalProgress()
            controller.goal_id, controller.version, controller.task_id = goal.goal_id, actions.binding.goal_version, row["trial"]
            controller.receipts = TypeAdapter(list[DispatchReceipt]).validate_json(json.dumps(case["prior_receipts"]))
            controller.bindings = TypeAdapter(list[Binding]).validate_json(json.dumps(case["prior_bindings"]))
            advice = await controller.advise(SubAgentRequest("", "", row["trial"]), goal, snapshot,
                                             replace(actions, reason="diagnostic_review"), context)
            assert advice is not None
            row["advice_kind"] = advice.kind
            if advice.kind == "candidate":
                action = controller.candidate(actions, advice.candidate_id)
                label = next(item.label for item in actions.details if item.action_id == action.id)
            elif advice.kind == "focus":
                controller.adopt_focus(advice.focus, goal, snapshot, actions)
                row["focus"] = advice.focus.model_dump(mode="json") if advice.focus is not None else None
                row["focus_used_same_frozen_snapshot"] = True
                decision = await selector.choose(goal, snapshot, replace(actions, progress=controller.progress), context)
            elif advice.kind == "inputs":
                raise SubAgentStopped("invalid_goal_patch")
            else:
                control = advice.kind
        else:
            decision = await selector.choose(goal, snapshot, actions, context)
        if decision is not None:
            if decision.choice == "candidate":
                label = next(item.label for item in actions.details if item.action_id == decision.candidate_id)
            else:
                control = decision.choice
    row.update(status="returned", label=label, control=control,
               classification=classify(case, arm, label, control))


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories = ("preferred", "repair_alternative", "handoff", "other_action", "invalid", "error", "not_run")
    result = {}
    for arm in ARMS:
        group = [row for row in rows if row["arm"] == arm]
        elapsed = [row["elapsed_ms"] for row in group if row["status"] == "returned"]
        result[arm] = {"planned": len(group),
            **{name: sum(row["classification"] == name for row in group) for name in categories},
            "sdk_calls": sum(len(row.get("calls", [])) for row in group),
            "timed_returned_n": len(elapsed), "median_returned_ms": median(elapsed) if elapsed else None,
            "known_estimate_nano_usd": sum(row.get("spend", {}).get("known_nano_usd", 0) for row in group),
            "charged_estimate_nano_usd": sum(row.get("spend", {}).get("charged_nano_usd", 0) for row in group),
            "known_tokens": sum(row.get("spend", {}).get("known_tokens", 0) for row in group)}
    return result


async def run_batch(output: Path, approved: str, *, jev_credential: str, advisor_credential: str) -> dict[str, Any]:
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext, SubAgentStopped
    from tank_backend.agents.task_runtime import ExecutionRecord
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded, TokenAllowance
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.profile import LLMProfile
    from benchmarks.computer_use.jev_smoke import Capture

    frozen = load_freeze(output, approved)
    if not jev_credential.strip() or not advisor_credential.strip():
        raise ValueError("Both explicitly configured model credentials are required")
    for name in ("started.json", "result.json", "spend.jsonl", "calls.jsonl", "audit.jsonl"):
        if (output / name).exists():
            raise FileExistsError(output / name)
    with (output / "started.json").open("x") as stream:
        json.dump({"sha256": approved, "desktop_operations": 0}, stream)
    rows = [{**item, "trial": f"{item['case_id']}-{item['arm']}-{item['repeat']}",
             "status": "not_run", "classification": "not_run"} for item in frozen["schedule"]]
    cases = {case["id"]: case for case in frozen["cases"]}
    ledger = SpendLedger(SpendLimit(6_000_000, frozen["nano_usd_limit"]),
                         request_limit=frozen["request_limit"], journal=output / "spend.jsonl")
    contracts = tuple(ContextWindowContract(model["url"], model["model"], TokenAllowance(
        model["input_ceiling"], model["output_ceiling"], model["input_price"], model["output_price"]),
        "Inherited frozen conservative token/price contract; estimate, not provider invoice",
        output_cap_required=name != "jev") for name, model in frozen["models"].items())
    report: dict[str, Any] = {"sha256": approved, "completed": False, "rows": rows}

    class Policy(BenchmarkModelPolicy):
        def __init__(self, maximum: int):
            super().__init__(ledger, contracts)
            self.maximum, self.calls = maximum, 0

        def reserve(self, call_id, request):
            if self.calls >= self.maximum:
                ledger.stop("trial_call_limit")
                raise SpendLimitExceeded("trial_call_limit")
            super().reserve(call_id, request)
            self.calls += 1

    with ExitStack() as stack:
        stack.callback(ledger.close)
        journal = stack.enter_context((output / "calls.jsonl").open("x"))
        audits = stack.enter_context((output / "audit.jsonl").open("x"))

        class JournalCapture(Capture):
            async def request(self, call_id, request):
                await super().request(call_id, request)
                journal.write(json.dumps({"call_id": call_id, **self.calls[call_id]}, ensure_ascii=False) + "\n")
                journal.flush()

            async def response(self, call_id, response):
                await super().response(call_id, response)
                if "choices" in response:
                    self.calls[call_id]["response"]["choices"] = response["choices"]
                journal.write(json.dumps({"call_id": call_id, **self.calls[call_id]}, ensure_ascii=False) + "\n")
                journal.flush()

        async def audit(record: ExecutionRecord) -> None:
            from dataclasses import asdict
            audits.write(json.dumps(asdict(record)) + "\n")
            audits.flush()

        def persist() -> None:
            report.update(spend=ledger.snapshot(), summary=summary(rows))
            (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

        try:
            for row in rows:
                load_freeze(output, approved)
                ledger.start_trial(row["trial"], SpendLimit(1_200_000, frozen["nano_usd_limit"]))
                capture = JournalCapture()
                observer = s4_ax.PilotObserver()
                context = SubAgentContext(SubAgentAuthorization(frozenset({"network", "desktop"})),
                    SubAgentBudget(), asyncio.Event(), deadline=time.monotonic() + frozen["seconds_per_trial"],
                    observer=observer, max_actions=0, max_observations=0, audit=audit,
                    model_policy=Policy(2 if row["arm"] == "advisor" else 1), model_capture=capture)
                started = time.monotonic()
                row.update(status="started", classification="error")
                try:
                    context.runtime.bind(row["trial"])
                    await context.runtime.write_audit(ExecutionRecord(row["trial"], row["trial"],
                        "frozen_diagnostic", "not_sent", category="model", phase="prepared"))
                    model = frozen["models"]["jev"]
                    context.runtime.configure_decision_model(row["trial"], DecisionModelProfile(
                        model["url"], model["model"], "TANK_S4_DIAGNOSTIC_KEY"), credential=jev_credential)
                    if row["arm"] == "advisor":
                        model = frozen["models"]["advisor"]
                        context.runtime.configure_model(row["trial"], LLMProfile("advisor", advisor_credential,
                            model["model"], model["url"].removesuffix("/chat/completions"), temperature=0,
                            max_tokens=model["output_ceiling"], extra_body={"enable_thinking": False}))
                    await select_frozen(cases[row["case_id"]], row["arm"], context, row)
                except asyncio.CancelledError:
                    row.update(status="cancelled", classification="error")
                    ledger.stop("cancelled")
                    raise
                except SubAgentStopped as exc:
                    semantic = exc.reason in {"invalid_advice", "invalid_decision", "invalid_focus",
                        "unsupported_focus_evidence", "focus_already_satisfied", "invalid_goal_patch"}
                    row.update(status="invalid" if semantic else "error", classification="invalid" if semantic else "error",
                               reason=exc.reason)
                    if not semantic:
                        ledger.stop("operational_error")
                except Exception as exc:
                    row.update(status="error", classification="error", error_type=type(exc).__name__)
                    ledger.stop("operational_error")
                finally:
                    row["cleanup_confirmed"] = False
                    try:
                        await context.runtime.aclose()
                        row["cleanup_confirmed"] = True
                    except BaseException as exc:
                        row.update(cleanup_error_type=type(exc).__name__, status="error", classification="error")
                        ledger.stop("cleanup_failed")
                        if not isinstance(exc, Exception):
                            raise
                    finally:
                        row.update(calls=list(capture.calls.values()), events=observer.events,
                                   elapsed_ms=(time.monotonic() - started) * 1000,
                                   desktop_operations=len(context.runtime.records))
                        if row["desktop_operations"] or context.budget.unknown_calls:
                            row.update(status="error", classification="error")
                            ledger.stop("desktop_or_unknown_usage")
                        ledger.finish_trial()
                        row["spend"] = ledger.snapshot()["trials"][row["trial"]]
                        persist()
                print(json.dumps({key: row.get(key) for key in ("trial", "classification", "label", "control", "reason")}), flush=True)
                if ledger.snapshot()["stop_reason"]:
                    break
            report["completed"] = all(row["status"] in {"returned", "invalid"} and row["cleanup_confirmed"] for row in rows)
        except Exception as exc:
            report["error_type"] = type(exc).__name__
            ledger.stop("batch_error")
            raise
        finally:
            persist()
    return report


if __name__ == "__main__":
    import argparse
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--approved-sha256")
    args = parser.parse_args()
    if not args.run:
        frozen = prepare(args.output)
        print(json.dumps({key: frozen[key] for key in ("sha256", "request_limit", "nano_usd_limit")}))
    else:
        if not args.approved_sha256:
            parser.error("Execution requires a frozen recipe digest")
        load_freeze(args.output, args.approved_sha256)
        from dotenv import dotenv_values
        values = dotenv_values(Path(__file__).resolve().parents[2] / "core/.env")
        report = asyncio.run(run_batch(args.output, args.approved_sha256,
            jev_credential=os.environ.get("TYPESAFE_API_KEY") or values.get("TYPESAFE_API_KEY") or "",
            advisor_credential=os.environ.get("BAILIAN_API_KEY") or values.get("BAILIAN_API_KEY") or ""))
        raise SystemExit(0 if report["completed"] else 1)
