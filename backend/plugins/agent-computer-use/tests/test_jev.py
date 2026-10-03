"""Jev uses the real host transport; only the external HTTP boundary is replaced."""

import asyncio
import json

import httpx
import pytest
from agent_computer_use.action_builder import ActionBuilder
from agent_computer_use.contracts import Element, GoalContract, Snapshot

from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext


def selection():
    goal = GoalContract.from_input({
        "schema_version": 1, "objective": "保存文档", "scope": "editor",
        "milestones": [{"id": "save", "operation": "click", "role": "button",
                        "label": "Save", "postcondition": {"key": "saved", "value": "yes"}}],
        "completion": [{"key": "saved", "value": "yes"}],
    })
    snapshot = Snapshot("obs", "editor", 1, (
        Element("save", "button", "保存", ("click",)),
        Element("cancel", "button", "取消", ("click",)),
    ))
    actions = ActionBuilder().build("goal", 1, goal, goal.milestones[0], snapshot)
    return goal, snapshot, actions


def reply(request, choice=None):
    criteria = json.loads(request.content)["questions"]["next_action"]["criteria"]
    choice = choice or next(iter(criteria))
    return {"model": "jev-1.13.0", "answers": {"next_action": {
        "type": "choice", "choice": choice,
        "probabilities": {key: float(key == choice) for key in criteria}, "confidence": 1.0,
    }}, "usage": {"input_tokens": 12, "output_tokens": 0}}


def setup(monkeypatch, respond, *, context=None):
    from agent_computer_use.jev import JevChoiceRoute, JevSelector

    sent, closed = [], []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent.append(request)
            return await respond(request)

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    ctx = context or SubAgentContext(
        SubAgentAuthorization(frozenset({"network", "desktop"})),
        SubAgentBudget(), asyncio.Event(),
    )
    ctx.runtime.configure_json_model(
        "task", JevChoiceRoute("https://offline.invalid/v1/systemone", "jev-1.13.0", "jev"),
        credential="host-secret",
    )
    return ctx, JevSelector("jev-1.13.0"), sent, closed


async def test_choice_is_bound_to_whole_action_and_accounted_once(monkeypatch):
    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply(request))

    ctx, selector, sent, closed = setup(monkeypatch, respond)
    goal, snapshot, actions = selection()
    try:
        decision = await selector.choose(goal, snapshot, actions, ctx)
        assert decision.binding == actions.binding
        assert decision.choice == "candidate"
        assert decision.candidate_id == actions.actions[0].id
        assert ctx.budget.total_tokens == 12
        assert len(sent) == 1
        body = json.loads(sent[0].content)
        assert set(body) == {"model", "state", "questions"}
        assert body["state"]["snapshot"]["observation_id"] == "obs"
        assert sent[0].headers["authorization"] == "Bearer host-secret"
        assert len(body["questions"]["next_action"]["criteria"]) == 6
    finally:
        await ctx.runtime.aclose()
    assert closed == [True]


@pytest.mark.parametrize("invalid", [
    "model", "type", "extra_answer", "choice", "probability_keys", "probability_sum",
    "probability_nan", "confidence", "not_maximum",
])
async def test_invalid_decisions_never_escape_but_usage_is_retained(monkeypatch, invalid):
    from tank_backend.agents.subagent import SubAgentStopped

    async def respond(request: httpx.Request) -> httpx.Response:
        data = reply(request)
        answer = data["answers"]["next_action"]
        if invalid == "model":
            data["model"] = "jev-latest"
        elif invalid == "type":
            answer["type"] = "score"
        elif invalid == "extra_answer":
            data["answers"]["other"] = answer.copy()
        elif invalid == "choice":
            answer["choice"] = "invented"
        elif invalid == "probability_keys":
            answer["probabilities"].pop("none")
        elif invalid == "probability_sum":
            answer["probabilities"]["none"] = 0.5
        elif invalid == "probability_nan":
            # JSON-standard response construction deliberately permits NaN here.
            answer["probabilities"]["none"] = float("nan")
        elif invalid == "confidence":
            answer["confidence"] = True
        else:
            answer["probabilities"][answer["choice"]] = 0.0
            answer["probabilities"]["none"] = 1.0
        return httpx.Response(200, content=json.dumps(data))

    ctx, selector, sent, _ = setup(monkeypatch, respond)
    try:
        with pytest.raises(SubAgentStopped, match="invalid_decision"):
            await selector.choose(*selection(), ctx)
        assert len(sent) == 1
        assert ctx.budget.total_tokens == 12
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("model", ["", "jev-latest", "jev-preview", "other", "jev-1.13.0\n"])
def test_model_must_be_an_explicit_version(model):
    from agent_computer_use.jev import JevChoiceRoute, JevSelector

    with pytest.raises(ValueError):
        JevChoiceRoute("https://offline.invalid/v1/systemone", model, "jev")
    with pytest.raises(ValueError):
        JevSelector(model)


@pytest.mark.parametrize("invalid", ["incomplete", "binding", "empty", "truncated"])
async def test_ineligible_evidence_sends_nothing(monkeypatch, invalid):
    from dataclasses import replace

    from tank_backend.agents.subagent import SubAgentStopped

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply(request))

    ctx, selector, sent, _ = setup(monkeypatch, respond)
    goal, snapshot, actions = selection()
    if invalid == "incomplete":
        snapshot = replace(snapshot, complete=False)
    elif invalid == "binding":
        snapshot = replace(snapshot, observation_id="new")
    elif invalid == "empty":
        actions = replace(actions, actions=())
    else:
        actions = replace(actions, truncated=True)
    try:
        with pytest.raises(SubAgentStopped):
            await selector.choose(goal, snapshot, actions, ctx)
        assert sent == []
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("choice", [None, "none", "ambiguous", "need_more_context", "escalate"])
async def test_controller_adapter_verifies_effect_or_refuses_action(monkeypatch, choice):
    from agent_computer_use.agent import ComputerUseSubAgent
    from agent_computer_use.contracts import DispatchReceipt, Fact
    from agent_computer_use.controller import ComputerUseController

    from tank_backend.agents.base import AgentOutputType, AgentState
    from tank_backend.agents.subagent import SubAgentRequest
    from tank_backend.agents.subagent_adapter import SubAgentAdapter

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply(request, choice))

    ctx, selector, sent, closed = setup(monkeypatch, respond)
    goal, snapshot, _ = selection()

    class World:
        actions = []
        released = False
        reads = 0

        async def observe(self, scope, context):
            self.reads += 1
            return Snapshot(str(self.reads), scope, self.reads, snapshot.elements,
                            (Fact(key="saved", value="yes"),) if self.actions else ())

        async def is_current(self, binding, action, context):
            return binding.generation == self.reads

        async def dispatch(self, binding, action, context):
            context.check("desktop")
            assert ctx.budget.total_tokens == 12  # Accounting precedes any action.
            self.actions.append(action)
            return DispatchReceipt(action.id, "sent")

        async def aclose(self):
            self.released = True

    world = World()
    plugin = ComputerUseSubAgent(
        ComputerUseController(world, world, selector=selector), resources=(world,),
    )
    adapter = SubAgentAdapter("computer-use", plugin, SubAgentRequest(
        "保存", "", "task", goal.model_dump(mode="json"),
    ), ctx)
    outputs = [output async for output in adapter.run(AgentState())]
    done = [output for output in outputs if output.type == AgentOutputType.DONE]
    assert len(done) == 1
    result = done[0].metadata["task_result"]
    assert result["status"] == ("completed" if choice is None else "stopped")
    assert len(world.actions) == (1 if choice is None else 0)
    assert result["cleanup"] == "confirmed"
    assert world.released and closed == [True]
    assert len(sent) == 1


@pytest.mark.parametrize("stop", ["revoked", "cancelled", "deadline", "audit", "zero_quota"])
async def test_host_blocks_before_sending(monkeypatch, stop):
    from tank_backend.agents.subagent import SubAgentStopped
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply(request))

    async def bad_audit(record):
        raise RuntimeError("audit unavailable")

    ledger = SpendLedger(SpendLimit(100, 100), request_limit=0, record_only=True)
    ledger.start_trial("trial", SpendLimit(100, 100))
    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop", "network"})),
        SubAgentBudget(), asyncio.Event(),
        audit=bad_audit if stop == "audit" else None,
        model_policy=BenchmarkModelPolicy(ledger, ()) if stop == "zero_quota" else None,
    )
    ctx, selector, sent, _ = setup(monkeypatch, respond, context=context)
    if stop == "revoked":
        ctx.authorization.revoke()
    elif stop == "cancelled":
        ctx.cancel.set()
    elif stop == "deadline":
        ctx.runtime.restrict_deadline(0)
    try:
        with pytest.raises((SubAgentStopped, asyncio.CancelledError, TimeoutError, SpendLimitExceeded)):
            await selector.choose(*selection(), ctx)
        assert sent == []
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("failure", ["usage", "http", "revoked", "cancelled", "timeout"])
async def test_failed_or_late_http_never_returns_a_decision(monkeypatch, failure):
    from tank_backend.agents.subagent import SubAgentStopped

    async def respond(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("provider unavailable")
        if failure == "revoked":
            ctx.authorization.revoke()
        elif failure == "cancelled":
            ctx.cancel.set()
        data = reply(request)
        if failure == "usage":
            data.pop("usage")
        return httpx.Response(529 if failure == "http" else 200, json=data)

    ctx, selector, sent, closed = setup(monkeypatch, respond)
    try:
        with pytest.raises((SubAgentStopped, asyncio.CancelledError)):
            await selector.choose(*selection(), ctx)
        assert len(sent) == 1
        if failure in {"usage", "http", "timeout"}:
            assert len(ctx.budget.unknown_calls) == 1
        else:
            assert ctx.budget.total_tokens == 12
    finally:
        await ctx.runtime.aclose()
    assert closed == [True]


async def test_unknown_usage_retains_reservation_and_blocks_next_call(monkeypatch):
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger, SpendLimit, SpendLimitExceeded, TokenAllowance,
    )

    async def respond(request: httpx.Request) -> httpx.Response:
        data = reply(request)
        data.pop("usage")
        return httpx.Response(200, json=data)

    ledger = SpendLedger(SpendLimit(100, 100), request_limit=2)
    ledger.start_trial("trial", SpendLimit(100, 100))
    policy = BenchmarkModelPolicy(ledger, (ContextWindowContract(
        "https://offline.invalid/v1/systemone", "jev-1.13.0",
        TokenAllowance(20, 10, 0, 0), "offline test bound", output_cap_required=False,
    ),))
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop", "network"})),
        SubAgentBudget(), asyncio.Event(), model_policy=policy,
    )
    ctx, selector, sent, _ = setup(monkeypatch, respond, context=ctx)
    try:
        for _ in range(2):
            with pytest.raises(SpendLimitExceeded):
                await selector.choose(*selection(), ctx)
        assert len(sent) == 1
        assert len(ctx.budget.unknown_calls) == 1
        assert ledger.snapshot()["stop_reason"] is not None
    finally:
        await ctx.runtime.aclose()


async def test_text_and_jev_share_the_original_task_ledger(monkeypatch):
    from tank_backend.llm.profile import LLMProfile

    async def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("chat/completions"):
            return httpx.Response(200, json={
                "id": "text", "object": "chat.completion", "created": 1, "model": "text",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": "advice",
                }}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            })
        return httpx.Response(200, json=reply(request))

    ctx, selector, sent, closed = setup(monkeypatch, respond)
    ctx.runtime.configure_model("task", LLMProfile(
        "advisor", "text-secret", "text", "https://offline.invalid/v1", max_tokens=10,
    ))
    try:
        model = ctx.runtime.model
        assert model is not None
        assert await model.complete([{"role": "user", "content": "advise"}]) == "advice"
        await selector.choose(*selection(), ctx)
        assert ctx.budget.total_tokens == 19
        assert ctx.budget.call_count == 2
        assert len(sent) == 2
    finally:
        await ctx.runtime.aclose()
    assert closed == [True, True]


@pytest.mark.parametrize("invalid", ["empty_name", "long_name", "instructions", "state", "stream"])
async def test_invalid_wire_request_is_refused_before_http(monkeypatch, invalid):
    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply(request))

    ctx, _, sent, _ = setup(monkeypatch, respond)
    model = ctx.runtime.json_model
    assert model is not None
    payload = {"model": "jev-1.13.0", "state": {}, "questions": {"next_action": {
        "type": "choice", "instructions": "Choose", "criteria": {"a": "Action"},
    }}}
    question = payload["questions"]["next_action"]
    if invalid == "empty_name":
        question["criteria"] = {" ": "Action"}
    elif invalid == "long_name":
        question["criteria"] = {"a" * 129: "Action"}
    elif invalid == "instructions":
        question["instructions"] = 123
    elif invalid == "state":
        payload["state"] = True
    else:
        payload["stream"] = True
    try:
        with pytest.raises(ValueError):
            await model.request(payload)
        assert sent == []
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("stop", ["cancel", "deadline"])
async def test_inflight_request_is_joined_on_stop(monkeypatch, stop):
    import time

    started, finished = asyncio.Event(), asyncio.Event()

    async def respond(request: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")
        finally:
            finished.set()

    ctx, selector, sent, closed = setup(monkeypatch, respond)
    if stop == "deadline":
        ctx.runtime.restrict_deadline(time.monotonic() + 0.05)
    task = asyncio.create_task(selector.choose(*selection(), ctx))
    try:
        await asyncio.wait_for(started.wait(), 1)
        if stop == "cancel":
            ctx.cancel.set()
        from tank_backend.agents.subagent import SubAgentStopped

        with pytest.raises((asyncio.CancelledError, TimeoutError, SubAgentStopped)):
            await asyncio.wait_for(task, 1)
        assert finished.is_set()
        assert len(sent) == 1 and len(ctx.budget.unknown_calls) == 1
    finally:
        await ctx.runtime.aclose()
    assert closed == [True]


def replay_module():
    import runpy
    from pathlib import Path

    return runpy.run_path(str(Path(__file__).parents[3] / "benchmarks/computer_use/s3_replay.py"))


def test_replay_freezes_public_inputs_separately_from_gold(tmp_path):
    module = replay_module()
    freeze = module["prepare"](tmp_path / "prepared")
    assert len(freeze["cases"]) == 24
    families = {
        split: {case["layout_family"] for case in freeze["cases"] if case["split"] == split}
        for split in ("calibration", "holdout")
    }
    assert not families["calibration"] & families["holdout"]
    assert all("gold" not in json.dumps(case["public"]) for case in freeze["cases"])
    assert module["load_freeze"](tmp_path / "prepared", freeze["sha256"]) == freeze


def test_replay_gold_cannot_change_candidates_and_truncation_is_separate(tmp_path):
    from copy import deepcopy

    module = replay_module()
    source = json.loads(module["FIXTURES"].read_text())
    item = source["cases"][0]
    changed = deepcopy(item)
    changed["gold"] = {"control": "none", "secret_truth": "DO_NOT_SEND"}
    assert module["public_case"](item) == module["public_case"](changed)
    freeze = module["prepare"](tmp_path / "prepared")
    assert freeze["request_limit"] == 64
    case = next(c for c in freeze["cases"] if c["category"] == "recall")
    scored = module["score"](case, None, "host_blocked")
    assert scored["candidate_recall"] is False
    assert scored["selection_error"] is False
    assert scored["dangerous_action"] is False


async def test_replay_uses_identical_inputs_and_counts_bad_replies(monkeypatch, tmp_path):
    module = replay_module()
    freeze = module["prepare"](tmp_path / "prepared")
    requests = []

    async def provider(request):
        data = json.loads(request.content)
        requests.append(data)
        if "questions" in data:
            options = data["questions"]["next_action"]["criteria"]
            return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {"next_action": {
                "type": "choice", "choice": "none", "confidence": 0.8,
                "probabilities": {key: float(key == "none") for key in options},
            }}, "usage": {"input_tokens": 10, "output_tokens": 0}})
        # Invalid JSON must be recorded as a failed selection, not silently dropped.
        return httpx.Response(200, json={"model": "qwen3.7-flash-2026-07-15", "choices": [{
            "finish_reason": "stop", "message": {"role": "assistant", "content": "bad-json"},
        }], "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}})

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda: httpx.MockTransport(provider))
    report = await module["run_replay"](tmp_path / "prepared", freeze["sha256"],
                                         {"jev": "fake-key", "qwen": "fake-key"})
    assert len(requests) == 64
    jev_questions = [{"state": data["state"],
                      "instructions": data["questions"]["next_action"]["instructions"],
                      "criteria": data["questions"]["next_action"]["criteria"]}
                     for data in requests if "questions" in data]
    qwen_questions = [json.loads(data["messages"][1]["content"])
                      for data in requests if "messages" in data]
    assert sorted(module["digest"](q) for q in jev_questions) == sorted(
        module["digest"](q) for q in qwen_questions)
    assert all("gold" not in json.dumps(q) and "layout_family" not in json.dumps(q)
               for q in jev_questions + qwen_questions)
    assert len(report["rows"]) == 144
    model_rows = [row for row in report["rows"] if row["status"] in {"returned", "invalid"}]
    assert len(model_rows) == 64
    assert sum(row["status"] == "invalid" for row in model_rows) == 32
    assert report["spend"]["batch"]["known_tokens"] == 32 * 21
    assert "fake-key" not in json.dumps(report)
    for case in freeze["cases"]:
        for stage in ("d2", "action"):
            pair = [row for row in model_rows if row["case_id"] == case["id"] and row["stage"] == stage]
            if pair:
                assert len({row["public_sha256"] for row in pair}) == 1


def test_replay_threshold_uses_calibration_only():
    module = replay_module()
    rows = [dict(split="calibration", stage="action", arm="jev", status="returned", category="semantic",
                 selected_action=True, confidence=0.6, dangerous_action=True),
            dict(split="calibration", stage="action", arm="jev", status="returned", category="semantic",
                 selected_action=True, confidence=0.8, dangerous_action=False)]
    chosen = module["calibrate"](rows)
    rows.append(dict(split="holdout", stage="action", arm="jev", status="returned", category="semantic",
                     selected_action=True, confidence=1.0, dangerous_action=True))
    assert module["calibrate"](rows) == chosen == {"d2/semantic": 1.01, "action/semantic": 0.7}


def test_replay_applies_locked_threshold_to_holdout(tmp_path):
    module = replay_module()
    freeze = module["prepare"](tmp_path / "prepared")
    case = next(c for c in freeze["cases"] if c["split"] == "holdout" and c["category"] == "semantic")
    action = next(a for a in case["public"]["actions"]["actions"] if a["target_ref"] == "e1")
    row = {"case_id": case["id"], "category": case["category"],
           "split": "holdout", "stage": "action", "arm": "jev",
           "status": "returned", "choice": action["id"], "confidence": 0.6,
           **module["score"](case, action["id"], "returned")}
    module["apply_thresholds"]([row], freeze["cases"], {"action/semantic": 0.7})
    assert row["dangerous_action"] is True
    assert row["accepted_choice"] == "escalate"
    assert row["accepted"]["dangerous_action"] is False


async def test_replay_unknown_usage_stops_batch_without_retry(monkeypatch, tmp_path):
    module = replay_module()
    freeze = module["prepare"](tmp_path / "prepared")
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(529)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda: httpx.MockTransport(provider))
    report = await module["run_replay"](tmp_path / "prepared", freeze["sha256"],
                                         {"jev": "fake", "qwen": "fake"})
    assert len(sent) == 1
    assert report["spend"]["stop_reason"] is not None
    assert any(row["status"] == "not_run" for row in report["rows"])
    assert report["summary"]
    assert (tmp_path / "prepared/audit.jsonl").read_text()
    with pytest.raises(FileExistsError):
        await module["run_replay"](tmp_path / "prepared", freeze["sha256"],
                                     {"jev": "fake", "qwen": "fake"})
    assert len(sent) == 1


def test_replay_tampered_freeze_is_rejected(tmp_path):
    module = replay_module()
    freeze = module["prepare"](tmp_path / "prepared")
    path = tmp_path / "prepared/freeze.json"
    changed = json.loads(path.read_text())
    changed["models"]["jev"]["url"] = "https://other.invalid/v1/systemone"
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="Frozen"):
        module["load_freeze"](tmp_path / "prepared", freeze["sha256"])


def test_replay_recomputed_digest_cannot_change_recipe(tmp_path):
    module = replay_module()
    freeze = module["prepare"](tmp_path / "prepared")
    path = tmp_path / "prepared/freeze.json"
    freeze["models"]["qwen"]["model"] = "unapproved-model"
    freeze["sha256"] = module["digest"]({k: v for k, v in freeze.items() if k != "sha256"})
    path.write_text(json.dumps(freeze))
    with pytest.raises(ValueError, match="Frozen"):
        module["load_freeze"](tmp_path / "prepared", freeze["sha256"])


@pytest.mark.parametrize("field", ["tool_calls", "function_call", "refusal"])
def test_replay_qwen_tool_or_refusal_is_not_a_choice(field):
    module = replay_module()
    response = {"model": module["MODELS"]["qwen"]["model"], "choices": [{
        "finish_reason": "stop", "message": {"content": '{"choice":"a0"}', field: {"name": "bad"}},
    }]}
    with pytest.raises(ValueError):
        module["parse_qwen"](response, {"a0": {}}, module["MODELS"]["qwen"]["model"])


async def test_replay_audit_failure_stops_entire_batch(monkeypatch, tmp_path):
    module = replay_module()
    freeze = module["prepare"](tmp_path / "prepared")
    append = module["append_json"]
    failed, sent = [], []

    def fail_first_audit(file, value):
        if str(file.name).endswith("audit.jsonl") and not failed:
            failed.append(True)
            raise OSError("audit unavailable")
        append(file, value)

    async def provider(request):
        sent.append(request)
        return httpx.Response(529)

    monkeypatch.setitem(module["run_replay"].__globals__, "append_json", fail_first_audit)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda: httpx.MockTransport(provider))
    report = await module["run_replay"](tmp_path / "prepared", freeze["sha256"],
                                         {"jev": "fake", "qwen": "fake"})
    assert failed and sent == []
    assert report["spend"]["stop_reason"] == "audit_failed"
