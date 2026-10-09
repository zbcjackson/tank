"""Jev uses the real host transport; only the external HTTP boundary is replaced."""

import asyncio
import json
from dataclasses import replace
from typing import cast

import httpx
import pytest
from agent_computer_use.action_builder import ActionBuilder
from agent_computer_use.contracts import Element, Fact, GoalContract, Snapshot

from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext


def selection():
    goal = GoalContract.from_input({'schema_version': 2, 'objective': '保存文档', 'scope': 'editor', 'completion': [{'key': 'status:saved', 'value': 'yes'}], 'goal_id': 'goal', 'intent': '保存文档', 'authorization_ref': 'current_task', 'allowed_operations': ['click', 'fill']})
    snapshot = Snapshot("obs", "editor", 1, (
        Element("save", "button", "保存", ("click",), click_effect=(Fact(key="activated:save", value="yes"),)),
        Element("cancel", "button", "取消", ("click",), click_effect=(Fact(key="activated:cancel", value="yes"),)),
    ))
    actions = ActionBuilder().build("goal", 1, goal, snapshot)
    return goal, snapshot, actions


def reply(request, choice=None):
    criteria = json.loads(request.content)["questions"]["next_action"]["criteria"]
    choice = choice or next(iter(criteria))
    return {"model": "jev-1.13.0", "answers": {"next_action": {
        "type": "choice", "choice": choice,
        "probabilities": {key: float(key == choice) for key in criteria}, "confidence": 1.0,
    }}, "usage": {"input_tokens": 12, "output_tokens": 0}}


def setup(monkeypatch, respond, *, context=None):
    from agent_computer_use.jev import JevSelector
    from tank_backend.llm.decision_profile import DecisionModelProfile

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
    ctx.runtime.configure_decision_model(
        "task", DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "jev"),
        credential="host-secret",
    )
    return ctx, JevSelector(), sent, closed


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
        assert set(body["questions"]["next_action"]["criteria"]) == {
            "c1", "c2", "none", "ambiguous", "need_more_context", "escalate"}
    finally:
        await ctx.runtime.aclose()
    assert closed == [True]


@pytest.mark.parametrize("route", ["jev", "text", "advisor"])
@pytest.mark.parametrize("invalid", [None, "original_id", "c0", "c01", "c99"])
async def test_model_aliases_resolve_only_against_the_current_action_set(monkeypatch, route, invalid):
    from agent_computer_use.advisor import LLMAdvisor
    from agent_computer_use.model_selector import ModelSelector
    from tank_backend.agents.subagent import SubAgentRequest, SubAgentStopped
    from tank_backend.llm.profile import LLMProfile

    goal, snapshot, actions = selection()
    original_id = actions.actions[0].id
    async def respond(request):
        payload = json.loads(request.content)
        choice = original_id if invalid == "original_id" else invalid or "c1"
        if "questions" in payload:
            return httpx.Response(200, json=reply(request, choice))
        content = {"kind": "candidate", "candidate_id": choice} if route == "advisor" else {"choice": choice}
        return httpx.Response(200, json={"id": "choice", "object": "chat.completion", "created": 1,
            "model": "planner", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    ctx, selector, sent, _ = setup(monkeypatch, respond)
    ctx.runtime.configure_model("task", LLMProfile("text", "key", "planner", "https://offline.invalid/v1", max_tokens=128))
    async def choose(current, observed):
        if route == "advisor":
            return await LLMAdvisor().assist(SubAgentRequest("Save", "", "task"), goal, observed, current, ctx)
        selected = selector if route == "jev" else ModelSelector(use_jev=False)
        return await selected.choose(goal, observed, current, ctx)
    try:
        if invalid:
            with pytest.raises(SubAgentStopped):
                await choose(actions, snapshot)
            assert len(sent) == 1
        else:
            first = await choose(actions, snapshot)
            assert first.candidate_id == original_id and first.binding == actions.binding
            observed = replace(snapshot, observation_id="next", generation=2)
            current = replace(actions, actions=tuple(reversed(actions.actions)),
                              binding=replace(actions.binding, observation_id="next", generation=2,
                                              candidate_set_id="next-set"))
            second = await choose(current, observed)
            assert second.candidate_id == actions.actions[1].id and second.binding == current.binding
            assert first.binding != second.binding
    finally:
        await ctx.runtime.aclose()


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
    from tank_backend.llm.decision_profile import DecisionModelProfile

    with pytest.raises(ValueError):
        DecisionModelProfile("https://offline.invalid/v1/systemone", model, "jev")


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
                            (Fact(key="status:saved", value="yes"), Fact(key="activated:save", value="yes"),) if self.actions else ())

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


@pytest.mark.parametrize("stop", ["revoked", "cancelled", "deadline", "zero_quota"])
async def test_host_blocks_before_sending(monkeypatch, stop):
    from tank_backend.agents.subagent import SubAgentStopped
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded

    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply(request))

    ledger = SpendLedger(SpendLimit(100, 100), request_limit=0, record_only=True)
    ledger.start_trial("trial", SpendLimit(100, 100))
    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop", "network"})),
        SubAgentBudget(), asyncio.Event(),
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


@pytest.mark.parametrize("invalid", ["empty_name", "long_name", "instructions", "state", "description"])
async def test_invalid_wire_request_is_refused_before_http(monkeypatch, invalid):
    async def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply(request))

    ctx, _, sent, _ = setup(monkeypatch, respond)
    model = ctx.runtime.decision_model
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
        question["criteria"] = {"a": 123}
    try:
        with pytest.raises(ValueError):
            await model.choose(state=cast(dict[str, object], payload["state"]),
                               instructions=question["instructions"],
                               options=question["criteria"])
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

    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(Path(__file__).parents[3]))
        import benchmarks.computer_use.legacy_json_model  # noqa: F401
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


def test_replay_positive_targets_are_counterbalanced():
    """Neither the first snapshot control nor e0 should encode the correct answer."""
    from collections import Counter, defaultdict

    module = replay_module()
    cases = module["freeze_inputs"]()["cases"]
    positions, references = defaultdict(Counter), defaultdict(Counter)
    for case in cases:
        if "target_ref" not in case["gold"] or case["category"] == "recall":
            continue
        target = case["gold"]["target_ref"]
        elements = case["public"]["snapshot"]["elements"]
        positions[case["category"]][next(i for i, e in enumerate(elements) if e["ref"] == target)] += 1
        references[case["category"]][target] += 1
    assert positions and all(counts[0] == counts[1] > 0 for counts in positions.values())
    assert all(counts["e0"] == counts["e1"] > 0 for counts in references.values())


def test_replay_gold_cannot_change_candidates_and_truncation_is_separate(tmp_path):
    from copy import deepcopy

    module = replay_module()
    source = json.loads(module["FIXTURES"].read_text())
    item = source["cases"][0]
    changed = deepcopy(item)
    changed["gold"] = {"control": "none", "secret_truth": "DO_NOT_SEND"}
    assert module["public_case"](item) == module["public_case"](changed)
    freeze = module["prepare"](tmp_path / "prepared")
    assert freeze["request_limit"] == 72
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
    assert len(requests) == 72
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
    assert len(model_rows) == 72
    assert sum(row["status"] == "invalid" for row in model_rows) == 36
    assert report["spend"]["batch"]["known_tokens"] == 36 * 21
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
    action = next(a for a in case["public"]["actions"]["actions"]
                  if a["target_ref"] != case["gold"]["target_ref"])
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


def replay_v2(monkeypatch):
    import runpy
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    return runpy.run_module("benchmarks.computer_use.s3_replay_v2", run_name="replay_v2_test")


def test_v2_scores_actionability_separately(monkeypatch):
    m = replay_v2(monkeypatch)
    positive = {"should_act": True, "target_ref": "e2"}
    negative = {"should_act": False}
    actions = [{"id": "a0", "target_ref": "e2"}, {"id": "a1", "target_ref": "e3"}]
    assert m["score"](positive, actions, "a0", "returned")["target_correct"] is True
    wrong = m["score"](positive, actions, "a1", "returned")
    assert wrong["actionability_correct"] and wrong["wrong_action"]
    refusal = m["score"](positive, actions, "abstain", "returned")
    assert refusal["false_refusal"] and not refusal["decision_correct"]
    assert m["score"](negative, actions, "abstain", "returned")["decision_correct"]
    assert not m["score"](negative, actions, None, "invalid")["decision_correct"]


async def test_v2_trace_reuses_real_http_pool_without_closing_borrowed_pool(monkeypatch):
    m = replay_v2(monkeypatch)

    connections, calls, closed = [], [], []

    async def serve(reader, writer):
        connections.append(True)
        try:
            while True:
                headers = await reader.readuntil(b"\r\n\r\n")
                length = next(int(line.split(b":", 1)[1]) for line in headers.splitlines()
                              if line.lower().startswith(b"content-length:"))
                await reader.readexactly(length)
                calls.append(True)
                body = b'{"usage":{"prompt_tokens":1,"completion_tokens":0,"total_tokens":1}}'
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                             + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    class Pool(httpx.AsyncHTTPTransport):
        async def aclose(self):
            closed.append(True)
            await super().aclose()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/chat/completions"
    pool = Pool()
    probes = []
    try:
        for i in range(2):
            probe = m["TraceProbe"]()
            probes.append(probe)
            ctx = SubAgentContext(SubAgentAuthorization(frozenset({"network"})),
                                  SubAgentBudget(), asyncio.Event())
            async with httpx.AsyncClient(transport=m["TraceLease"](pool, probe)) as client:
                await client.post(url, json={"model": "test", "max_tokens": 10,
                                           "messages": [{"role": "user", "content": "test"}]})
            await ctx.runtime.aclose()
            assert closed == []
        assert len(connections) == 1 and len(calls) == 2
        assert [probe.summary()["connection"] for probe in probes] == ["new", "reused"]
        assert probes[0].summary()["tcp_ms"] is not None
        assert probes[1].summary()["tcp_ms"] is None
        assert "test-secret" not in json.dumps([p.summary() for p in probes])
    finally:
        await pool.aclose()
        server.close()
        await server.wait_closed()
    assert closed == [True]


async def test_v2_missing_trace_is_unknown_not_zero(monkeypatch):
    probe = replay_v2(monkeypatch)["TraceProbe"]()
    assert probe.summary()["connection"] == "unknown"
    assert probe.summary()["headers_complete_ms"] is None
    await probe.trace("connection.connect_tcp.started", {"secret": "DO_NOT_LOG"})
    await probe.trace("connection.connect_tcp.failed", {"exception": "DO_NOT_LOG"})
    assert probe.summary()["tcp_ms"] is None
    assert "DO_NOT_LOG" not in json.dumps(probe.summary())


def test_v2_freeze_compact_inputs_and_disjoint_evidence(monkeypatch, tmp_path):
    m = replay_v2(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    assert len(f["cases"]) == 24 and f["request_limit"] == 72
    for c in f["cases"]:
        q = c["question"]
        assert '"gold"' not in json.dumps(q)
        assert '"target_ref"' not in json.dumps(q)
        assert '"binding"' not in json.dumps(q)
        assert "abstain" in q["criteria"]
        assert not {"none", "ambiguous", "need_more_context", "escalate"} & q["criteria"].keys()
    chart = next(c for c in f["cases"] if c["id"] == "chart-visual")
    assert "Open chart" not in json.dumps(chart["question"])
    assert m["load_freeze"](tmp_path / "prepared", f["sha256"]) == f


@pytest.mark.parametrize("fail", [False, True])
async def test_v2_batch_uses_pools_and_governance(monkeypatch, tmp_path, fail):
    m = replay_v2(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    sent, created, closed = [], [], []

    class HTTP(httpx.AsyncBaseTransport):
        def __init__(self, **kwargs):
            created.append(self)

        async def handle_async_request(self, request):
            data = json.loads(request.content)
            sent.append(data)
            if fail:
                return httpx.Response(529)
            if "questions" in data:
                criteria = data["questions"]["next_action"]["criteria"]
                return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {
                    "next_action": {"type": "choice", "choice": "abstain", "confidence": 1,
                                    "probabilities": {key: float(key == "abstain") for key in criteria}},
                }, "usage": {"input_tokens": 10, "output_tokens": 0}})
            return httpx.Response(200, json={"model": m["v1"].MODELS["qwen"]["model"], "choices": [{
                "finish_reason": "stop", "message": {"content": '{"choice":"abstain"}'},
            }], "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}})

        async def aclose(self):
            closed.append(self)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    result = await m["run_replay"](tmp_path / "prepared", f["sha256"],
                                     {"jev": "fake-secret", "qwen": "fake-secret"})
    assert len(result["rows"]) == 144
    assert len(sent) == (1 if fail else 72)
    assert len(created) == len(closed) == (1 if fail else 38)
    assert len({id(p) for p in closed}) == len(closed)
    assert bool(result["spend"]["stop_reason"]) == fail
    assert "fake-secret" not in json.dumps(result)
    if not fail:
        assert result["spend"]["batch"]["known_tokens"] == 36 * 21
        for row in result["rows"]:
            if row["status"] == "returned":
                assert row["timing"]["connection"] == "unknown"
        for case in f["cases"]:
            rows = [r for r in result["rows"] if r["case_id"] == case["id"]]
            assert len({r["public_sha256"] for r in rows}) == 1
    with pytest.raises(FileExistsError):
        await m["run_replay"](tmp_path / "prepared", f["sha256"], {"jev": "fake", "qwen": "fake"})


async def test_v2_audit_failure_blocks_all_sends(monkeypatch, tmp_path):
    m = replay_v2(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    append = m["v1"].append_json
    failed, sent = [], []

    def fail_audit(file, value):
        if str(file.name).endswith('audit.jsonl') and not failed:
            failed.append(True)
            raise OSError('audit failed')
        append(file, value)

    async def provider(request):
        sent.append(request)
        return httpx.Response(529)

    monkeypatch.setattr(m["v1"], "append_json", fail_audit)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(provider))
    r = await m["run_replay"](tmp_path / "prepared", f["sha256"], {"jev": "fake", "qwen": "fake"})
    assert failed and sent == [] and r["spend"]["stop_reason"] == "audit_failed"


def test_v2_positions_and_gold_are_not_exposed(monkeypatch, tmp_path):
    from collections import Counter
    from copy import deepcopy

    m = replay_v2(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    positions = Counter(c["gold"]["target_ref"] for c in f["cases"]
                        if c["gold"].get("target_ref") in {"e0", "e1", "e2", "e3"})
    assert set(positions) == {"e0", "e1", "e2", "e3"}
    assert max(positions.values()) - min(positions.values()) <= 1
    c = f["cases"][0]
    changed = deepcopy(c)
    changed["gold"] = {"should_act": False}
    assert m["question"](c["public"]) == m["question"](changed["public"])
    path = tmp_path / 'prepared/freeze.json'
    f["httpcore"] = "unexpected"
    path.write_text(json.dumps(f))
    with pytest.raises(ValueError, match='Frozen'):
        m["load_freeze"](tmp_path / 'prepared', f["sha256"])


@pytest.mark.parametrize('choice', ['none', 'a999'])
def test_v2_rejects_unoffered_choice(monkeypatch, choice):
    m = replay_v2(monkeypatch)
    data = {"model": "jev-1.13.0", "answers": {"next_action": {
        "type": "choice", "choice": choice, "confidence": 1,
        "probabilities": {"a0": 0, "abstain": 1},
    }}}
    with pytest.raises(ValueError):
        m["parse_response"]('jev', data, {'a0': {}, 'abstain': 'refuse'})


async def test_v2_cleanup_failure_keeps_paid_row_and_stops(monkeypatch, tmp_path):
    m = replay_v2(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    sent = []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent.append(request)
            q = json.loads(request.content)['questions']['next_action']['criteria']
            return httpx.Response(200, json={"model":"jev-1.13.0", "answers":{"next_action":{
                "type":"choice", "choice":"abstain", "confidence":1,
                "probabilities":{key:float(key=='abstain') for key in q},
            }}, "usage":{"input_tokens":10,"output_tokens":0}})

        async def aclose(self):
            raise OSError('cleanup failed')

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: HTTP())
    r = await m['run_replay'](tmp_path/'prepared', f['sha256'], {'jev':'fake','qwen':'fake'})
    assert len(sent) == 1 and not r['completed']
    assert r['rows'][1]['usage']['total_tokens'] == 10
    assert r['rows'][1]['cleanup'] == 'unknown'
    assert r['spend']['stop_reason'] == 'cleanup_failed'


async def test_v2_cancel_preserves_call_and_stops_pool(monkeypatch, tmp_path):
    m = replay_v2(monkeypatch)
    f = m['prepare'](tmp_path/'prepared')
    started, ended, closed = asyncio.Event(), asyncio.Event(), []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            started.set()
            try:
                await asyncio.Event().wait()
                raise AssertionError("unreachable")
            finally:
                ended.set()

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(httpx, 'AsyncHTTPTransport', lambda **kwargs: HTTP())
    task = asyncio.create_task(m['run_replay'](tmp_path/'prepared', f['sha256'],
                                               {'jev':'fake','qwen':'fake'}))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    r = json.loads((tmp_path/'prepared/result.json').read_text())
    assert ended.is_set() and closed == [True]
    assert not r['completed'] and r['rows'][-1]['status'] == 'cancelled'
    assert r['rows'][-1]['usage']['unknown_calls'] == 1


async def test_v2_phase_names_do_not_claim_first_byte_or_inference(monkeypatch):
    p = replay_v2(monkeypatch)['TraceProbe']()
    for name in ('connection.start_tls.started', 'connection.start_tls.complete',
                 'http11.receive_response_headers.started', 'http11.receive_response_headers.complete',
                 'http11.receive_response_body.started', 'http11.receive_response_body.complete'):
        await p.trace(name, {'headers': {'Authorization': 'DO_NOT_LOG'}})
    s = p.summary()
    assert s['tls_ms'] >= 0 and s['headers_wait_ms'] >= 0 and s['body_receive_ms'] >= 0
    assert s['headers_complete_ms'] <= s['body_complete_ms']
    assert 'ttfb_ms' not in s and 'inference_ms' not in s
    assert 'DO_NOT_LOG' not in json.dumps(s)


def replay_v3(monkeypatch):
    import runpy
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    return runpy.run_module(
        "benchmarks.computer_use.s3_replay_v3", run_name="replay_v3_test"
    )


def test_v3_factorial_changes_only_intended_factor(monkeypatch, tmp_path):
    m = replay_v3(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    assert len(f["cases"]) == 12 and f["request_limit"] == 120
    for c in f["cases"]:
        q = c["questions"]
        assert q["legacy"] == m["v2"].question(c["public"])
        assert "host_contract" not in q["legacy"]["state"]
        assert q["broad_minimal"]["state"] == q["scoped_minimal"]["state"]
        assert q["broad_enriched"]["state"] == q["scoped_enriched"]["state"]
        assert q["broad_minimal"]["instructions"] == q["broad_enriched"]["instructions"]
        assert (
            q["scoped_minimal"]["instructions"] == q["scoped_enriched"]["instructions"]
        )
        assert len({m["v1"].digest(x["criteria"]) for x in q.values()}) == 1
        assert "business_state" not in q["broad_minimal"]["state"]
        assert (
            q["broad_minimal"]["state"]["host_contract"]
            == q["scoped_enriched"]["state"]["host_contract"]
        )
        assert '"gold"' not in json.dumps(q) and '"should_act"' not in json.dumps(q)
    assert m["load_freeze"](tmp_path / "prepared", f["sha256"]) == f


def test_v3_does_not_penalize_minimal_evidence_refusal_as_error(monkeypatch):
    m = replay_v3(monkeypatch)
    c = m["freeze_inputs"]()["cases"][0]
    for variant in ("legacy", "broad_minimal", "scoped_minimal"):
        s = m["score"](c, variant, "abstain", "returned")
        assert s["evidence_acceptable"] is True and not s["enriched_positive_refusal"]
        assert s["positive_abstain"] and not s["positive_action"]
    s = m["score"](c, "scoped_enriched", "abstain", "returned")
    assert not s["evidence_acceptable"] and s["enriched_positive_refusal"]
    negative = next(
        c for c in m["freeze_inputs"]()["cases"] if not c["gold"]["should_act"]
    )
    assert not m["score"](negative, "broad_enriched", None, "invalid")[
        "evidence_acceptable"
    ]
    action = negative["public"]["actions"]["actions"][0]["id"]
    assert m["score"](negative, "scoped_enriched", action, "returned")[
        "negative_action"
    ]


@pytest.mark.parametrize("key", ["gold", "should_act", "target_ref", "candidate_id"])
def test_v3_rejects_gold_markers_in_business_facts(monkeypatch, key):
    m = replay_v3(monkeypatch)
    c = m["freeze_inputs"]()["cases"][0]
    with pytest.raises(ValueError, match="oracle"):
        m["questions"](c["public"], {"nested": {key: "a0"}})


@pytest.mark.parametrize("fail", [False, True])
async def test_v3_governed_factorial_batch(monkeypatch, tmp_path, fail):
    m = replay_v3(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    sent, pools, closed = [], [], []

    class HTTP(httpx.AsyncBaseTransport):
        def __init__(self, **kwargs):
            pools.append(self)

        async def handle_async_request(self, request):
            data = json.loads(request.content)
            sent.append(data)
            if fail:
                return httpx.Response(529)
            if "questions" in data:
                criteria = data["questions"]["next_action"]["criteria"]
                return httpx.Response(
                    200,
                    json={
                        "model": "jev-1.13.0",
                        "answers": {
                            "next_action": {
                                "type": "choice",
                                "choice": "abstain",
                                "confidence": 1,
                                "probabilities": {
                                    key: float(key == "abstain") for key in criteria
                                },
                            }
                        },
                        "usage": {"input_tokens": 10, "output_tokens": 0},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "model": m["v1"].MODELS["qwen"]["model"],
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": '{"choice":"abstain"}'},
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 1,
                        "total_tokens": 11,
                    },
                },
            )

        async def aclose(self):
            closed.append(self)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    r = await m["run_replay"](
        tmp_path / "prepared",
        f["sha256"],
        {"jev": "fake-secret", "qwen": "fake-secret"},
    )
    assert len(r["rows"]) == 120 and len(sent) == (1 if fail else 120)
    assert len(pools) == len(closed) == (1 if fail else 2)
    assert len({id(p) for p in closed}) == len(closed)
    assert bool(r["spend"]["stop_reason"]) == fail
    assert "fake-secret" not in json.dumps(r)
    if not fail:
        assert r["spend"]["batch"]["known_tokens"] == 1260
        for variant in m["VARIANTS"]:
            for arm in ("jev", "qwen"):
                s = r["summary"][f"{variant}/{arm}"]
                assert (
                    s["planned_n"] == 12
                    and s["positive_n"] == 8
                    and s["negative_n"] == 4
                )
                assert s["positive_abstain"] == 8 and s["negative_action"] == 0
        for c in f["cases"]:
            for variant in m["VARIANTS"]:
                pair = [
                    x
                    for x in r["rows"]
                    if x["case_id"] == c["id"] and x["variant"] == variant
                ]
                q = [
                    (
                        {
                            "state": x["request"]["state"],
                            "instructions": x["request"]["questions"]["next_action"][
                                "instructions"
                            ],
                            "criteria": x["request"]["questions"]["next_action"][
                                "criteria"
                            ],
                        }
                        if x["arm"] == "jev"
                        else json.loads(x["request"]["messages"][1]["content"])
                    )
                    for x in pair
                ]
                assert q[0] == q[1] == c["questions"][variant]
    with pytest.raises(FileExistsError):
        await m["run_replay"](
            tmp_path / "prepared", f["sha256"], {"jev": "fake", "qwen": "fake"}
        )


def test_v3_order_and_freeze_integrity(monkeypatch, tmp_path):
    from collections import Counter

    m = replay_v3(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    for v in m["VARIANTS"]:
        first = Counter(
            next(arm for variant, arm in m["schedule"](i) if variant == v)
            for i in range(12)
        )
        assert first == {"jev": 6, "qwen": 6}
    starts = Counter(m["schedule"](i)[0][0] for i in range(12))
    assert max(starts.values()) - min(starts.values()) <= 1
    f["cases"][0]["questions"]["legacy"]["instructions"] = "altered"
    f["sha256"] = m["v1"].digest({k: v for k, v in f.items() if k != "sha256"})
    (tmp_path / "prepared/freeze.json").write_text(json.dumps(f))
    with pytest.raises(ValueError, match="Frozen"):
        m["load_freeze"](tmp_path / "prepared", f["sha256"])


async def test_v3_audit_failure_stops_all_conditions(monkeypatch, tmp_path):
    m = replay_v3(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    append = m["v1"].append_json
    failed = []
    sent = []

    def fail(file, value):
        if str(file.name).endswith("audit.jsonl") and not failed:
            failed.append(True)
            raise OSError("audit unavailable")
        append(file, value)

    async def provider(request):
        sent.append(request)
        return httpx.Response(529)

    monkeypatch.setattr(m["v1"], "append_json", fail)
    monkeypatch.setattr(
        httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(provider)
    )
    r = await m["run_replay"](
        tmp_path / "prepared", f["sha256"], {"jev": "fake", "qwen": "fake"}
    )
    assert failed and not sent and r["spend"]["stop_reason"] == "audit_failed"
    assert len(r["rows"]) == 120 and not r["completed"]


async def test_v3_cancel_keeps_inflight_evidence(monkeypatch, tmp_path):
    m = replay_v3(monkeypatch)
    f = m["prepare"](tmp_path / "prepared")
    started, ended = asyncio.Event(), asyncio.Event()
    closed = []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            started.set()
            try:
                await asyncio.Event().wait()
                raise AssertionError("unreachable")
            finally:
                ended.set()

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: HTTP())
    task = asyncio.create_task(
        m["run_replay"](
            tmp_path / "prepared", f["sha256"], {"jev": "fake", "qwen": "fake"}
        )
    )
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    r = json.loads((tmp_path / "prepared/result.json").read_text())
    assert ended.is_set() and closed == [True]
    assert (
        r["rows"][0]["status"] == "cancelled"
        and r["rows"][0]["usage"]["unknown_calls"] == 1
    )
    assert not r["completed"]


def test_v3_contrasts_are_predefined_and_require_complete_responses(monkeypatch):
    m = replay_v3(monkeypatch)
    rows = []
    for arm in ('jev','qwen'):
        for variant in m['VARIANTS']:
            rows.append({'case_id':'one','arm':arm,'variant':variant,'status':'returned',
                         'positive_action':variant=='scoped_enriched',
                         'negative_action':False,'wrong_target':False})
    c = m['contrasts'](rows)
    assert c['jev']['facts_under_scoped']['positive_action_delta'] == 1
    assert c['jev']['interaction']['positive_action_delta'] == 1
    rows[0]['status']='invalid'
    assert m['contrasts'](rows) is None


async def test_selector_distinguishes_declared_goals_from_observed_facts(monkeypatch):
    from dataclasses import replace

    from agent_computer_use.contracts import Fact, GoalInput

    async def respond(request):
        return httpx.Response(200, json=reply(request, "need_more_context"))

    ctx, selector, sent, _ = setup(monkeypatch, respond)
    goal, snapshot, actions = selection()
    goal = goal.model_copy(update={"inputs": (GoalInput(key="saved", purpose="declared state", value="yes"),)})
    snapshot = replace(snapshot, facts=(Fact(key="saved", value="no"),))
    try:
        decision = await selector.choose(goal, snapshot, actions, ctx)
        state = json.loads(sent[0].content)["state"]
        contract = state["evidence_contract"]
        assert contract["schema_version"] == 1
        assert contract["output_effect"] == "proposal_only"
        assert contract["sources"]["goal.inputs"] == "task_or_advisor_declarations"
        assert contract["sources"]["goal.completion"] == "desired_outcomes"
        assert contract["sources"]["snapshot.facts"] == "current_observation_channel_reports"
        assert contract["business_validation"] == "not_established_by_this_contract"
        assert state["goal"]["inputs"] == [goal.inputs[0].model_dump(mode="json")]
        assert state["snapshot"]["facts"] == [{"key": "saved", "value": "no"}]
        assert "business_state" not in state
        assert decision.choice == "need_more_context"
    finally:
        await ctx.runtime.aclose()


async def test_selector_request_uses_only_current_observation_evidence(monkeypatch):
    from dataclasses import replace

    from agent_computer_use.contracts import Fact

    async def respond(request):
        return httpx.Response(200, json=reply(request, "need_more_context"))

    ctx, selector, sent, _ = setup(monkeypatch, respond)
    goal, snapshot, actions = selection()
    try:
        await selector.choose(goal, replace(snapshot, facts=(Fact(key="old", value="private"),)), actions, ctx)
        current = replace(snapshot, observation_id="obs2", generation=2,
                          facts=(Fact(key="new", value="reported"),))
        current_actions = replace(actions, binding=replace(actions.binding, observation_id="obs2", generation=2))
        await selector.choose(goal, current, current_actions, ctx)
        state = json.loads(sent[1].content)["state"]
        assert state["evidence_contract"]["sources"]["snapshot.facts"] == "current_observation_channel_reports"
        assert state["snapshot"]["facts"] == [{"key": "new", "value": "reported"}]
        assert "private" not in sent[1].content.decode()
        assert state["binding"]["observation_id"] == "obs2"
    finally:
        await ctx.runtime.aclose()


async def test_holdout_freezes_actual_selector_payload_without_labels(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_holdout as holdout

    cases, labels = holdout.load_dataset()
    seen = []

    async def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=reply(request, "need_more_context"))

    ctx, selector, _, _ = setup(monkeypatch, respond)
    try:
        case = cases[0]
        snapshot, actions = holdout.build_case(case)
        await selector.choose(case.goal, snapshot, actions, ctx)
        frozen = json.loads(json.dumps(holdout.prepare(tmp_path / "freeze")))
        assert frozen["cases"][0]["requests"]["contract"] == seen[0]
        for row in frozen["cases"]:
            old, new = row["requests"]["legacy"], row["requests"]["contract"]
            assert old["questions"]["next_action"]["criteria"] == new["questions"]["next_action"]["criteria"]
            assert {k: v for k, v in new["state"].items() if k != "evidence_contract"} == old["state"]
            assert all(key not in json.dumps(new) for key in ("expected_target_ref", "allowed_controls"))
        assert len(labels) == 24
    finally:
        await ctx.runtime.aclose()


def test_holdout_coverage_scoring_and_freeze_tampering(monkeypatch, tmp_path):
    from collections import Counter

    from agent_computer_use.contracts import DecisionResult
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_holdout as holdout

    cases, labels = holdout.load_dataset()
    assert len(cases) == 24
    assert Counter(c.condition for c in cases) == dict.fromkeys(holdout.CONDITIONS, 6)
    positions = []
    for case in cases:
        _, actions = holdout.build_case(case)
        expected = labels[case.id]
        if expected.expected_target_ref is not None:
            index = next(i for i, a in enumerate(actions.actions) if a.target_ref == expected.expected_target_ref)
            positions.append(index)
            correct = DecisionResult(actions.binding, "candidate", actions.actions[index].id)
            assert holdout.score(expected, actions, correct, "returned")["correct"]
        else:
            wrong = DecisionResult(actions.binding, "candidate", actions.actions[0].id)
            assert holdout.score(expected, actions, wrong, "returned")["negative_action"]
            refusal = DecisionResult(actions.binding, "need_more_context")
            assert holdout.score(expected, actions, refusal, "returned")["correct"]
        failed = holdout.score(expected, actions, None, "not_run")
        assert failed["planned_n"] == 1 and failed["correct"] is False
    assert Counter(positions) == {0: 6, 1: 6}
    frozen = json.loads(json.dumps(holdout.prepare(tmp_path / "freeze")))
    holdout.load_freeze(tmp_path / "freeze", frozen["sha256"])
    path = tmp_path / "freeze" / "freeze.json"
    data = json.loads(path.read_text())
    data["request_limit"] += 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        holdout.load_freeze(path.parent, frozen["sha256"])
    with pytest.raises(FileExistsError):
        holdout.prepare(path.parent)


@pytest.mark.parametrize("mutation", ["label", "case", "missing_label"])
def test_holdout_sources_are_pinned_and_labels_never_build_requests(monkeypatch, tmp_path, mutation):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_holdout as holdout

    for name in ("cases.json", "labels.json"):
        (tmp_path / name).write_bytes((holdout.DATA / name).read_bytes())
    monkeypatch.setattr(holdout, "DATA", tmp_path)
    cases, _ = holdout.load_dataset()
    before = holdout.requests(cases[0])
    frozen = holdout.prepare(tmp_path / "freeze")
    if mutation == "case":
        data = json.loads((tmp_path / "cases.json").read_text())
        data[0]["facts"][0]["value"] = "changed observation"
        (tmp_path / "cases.json").write_text(json.dumps(data))
    else:
        labels = json.loads((tmp_path / "labels.json").read_text())
        if mutation == "label":
            labels["h01"] = {"expected_target_ref": "e1"}
        else:
            del labels["h01"]
        (tmp_path / "labels.json").write_text(json.dumps(labels))
    with pytest.raises(ValueError):
        holdout.load_freeze(tmp_path / "freeze", str(frozen["sha256"]))
    if mutation == "label":
        assert holdout.requests(holdout.load_dataset()[0][0]) == before


def test_holdout_preparation_has_no_network_or_credentials(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_holdout as holdout

    def forbidden(*args, **kwargs):
        raise AssertionError("offline preparation reached an external boundary")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    frozen = json.loads(json.dumps(holdout.prepare(tmp_path / "freeze")))
    assert frozen["request_limit"] == len(frozen["schedule"]) == 48
    assert frozen["preparation_only"] is True
    for arm in ("legacy", "contract"):
        assert sum(row["arm"] == arm for row in frozen["schedule"]) == 24
    assert {p.name for p in (tmp_path / "freeze").iterdir()} == {"freeze.json"}


def test_holdout_pair_order_is_balanced_within_each_condition(monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_holdout as holdout

    frozen = json.loads(json.dumps(holdout.freeze_inputs()))
    first = {row["case_id"]: row["arm"] for row in frozen["schedule"][::2]}
    for condition in holdout.CONDITIONS:
        selected = [row for row in frozen["cases"] if row["condition"] == condition]
        assert sum(first[row["id"]] == "legacy" for row in selected) == 3


@pytest.mark.parametrize("failure", [None, "unknown", "cancel", "cleanup", "audit", "budget", "invalid", "http"])
async def test_holdout_live_governed_execution(monkeypatch, tmp_path, failure):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_holdout_live as live

    sent, closed = [], []

    class HTTP(httpx.AsyncBaseTransport):
        def __init__(self, **kwargs):
            assert kwargs["retries"] == 0

        async def handle_async_request(self, request):
            sent.append(json.loads(request.content))
            if failure == "cancel":
                raise asyncio.CancelledError
            if failure == "http":
                return httpx.Response(503)
            data = reply(request, "need_more_context")
            if failure == "invalid":
                data["answers"]["next_action"]["confidence"] = True
            if failure == "unknown":
                data.pop("usage")
            return httpx.Response(200, json=data)

        async def aclose(self):
            closed.append(True)
            if failure == "cleanup":
                raise RuntimeError("cleanup failure")

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    if failure == "audit":
        append = live.v1.append_json

        def reject_audit(file, row):
            if Path(file.name).name == "audit.jsonl":
                raise OSError("audit unavailable")
            append(file, row)

        monkeypatch.setattr(live.v1, "append_json", reject_audit)
    if failure == "budget":
        original = live.SpendLedger

        def zero_budget(*args, **kwargs):
            kwargs["request_limit"] = 0
            return original(*args, **kwargs)

        monkeypatch.setattr(live, "SpendLedger", zero_budget)
    frozen = live.prepare(tmp_path / "run")
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await live.run_replay(tmp_path / "run", frozen["sha256"], "test-key")
        result = json.loads((tmp_path / "run/result.json").read_text())
    else:
        result = await live.run_replay(tmp_path / "run", frozen["sha256"], "test-key")
    assert len(result["rows"]) == 48
    assert sum(s["planned_n"] for s in result["summary"].values()) == 48
    assert len((tmp_path / "run/rows.jsonl").read_text().splitlines()) == 48
    assert closed == [True]
    if failure in ("audit", "budget"):
        assert sent == []
    elif failure in ("unknown", "cancel", "http"):
        assert len(sent) == 1
        assert sum(r["status"] == "not_run" for r in result["rows"]) == 47
    else:
        assert len(sent) == 48
        by_id = {c["id"]: c for c in frozen["cases"]}
        assert sent == [by_id[r["case_id"]]["requests"][r["arm"]] for r in frozen["schedule"]]
        assert result["spend"]["batch"]["known_tokens"] == 48 * 12
        assert result["spend"]["batch"]["reserved_tokens"] == 0
        assert len((tmp_path / "run/audit.jsonl").read_text().splitlines()) == 48
        assert all(s["invalid_n" if failure == "invalid" else "returned_n"] == 6
                   for s in result["summary"].values())
    assert result["completed"] == (failure in (None, "invalid"))
    assert (result["contrasts"] is not None) == (failure in (None, "cleanup"))
    before = len(sent)
    with pytest.raises((FileExistsError, ValueError)):
        await live.run_replay(tmp_path / "run", frozen["sha256"], "test-key")
    assert len(sent) == before


async def test_holdout_live_refuses_changed_freeze_before_client(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_holdout_live as live

    frozen = live.prepare(tmp_path / "run")
    live.load_freeze(tmp_path / "run", frozen["sha256"])
    frozen["request_limit"] = 49
    frozen["sha256"] = live.v1.digest({k: v for k, v in frozen.items() if k != "sha256"})
    (tmp_path / "run/freeze.json").write_text(json.dumps(frozen))

    def forbidden(**kwargs):
        raise AssertionError("changed recipe created a client")

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", forbidden)
    with pytest.raises(ValueError, match="recipe changed"):
        await live.run_replay(tmp_path / "run", frozen["sha256"], "test-key")
    assert not (tmp_path / "run/spend.jsonl").exists()


async def test_holdout_live_preserves_existing_result_without_ledger(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_holdout_live as live

    frozen = live.prepare(tmp_path / "run")
    result = tmp_path / "run/result.json"
    result.write_text("existing evidence")

    def forbidden(**kwargs):
        raise AssertionError("existing evidence allowed transport creation")

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", forbidden)
    with pytest.raises(FileExistsError):
        await live.run_replay(tmp_path / "run", frozen["sha256"], "test-key")
    assert result.read_text() == "existing evidence"
    assert not (tmp_path / "run/spend.jsonl").exists()


async def test_holdout_live_scores_frozen_labels_without_second_source_read(monkeypatch, tmp_path):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_holdout_live as live

    frozen = live.prepare(tmp_path / "run")
    original = live.dataset.load_dataset
    reads = 0

    def changing_source():
        nonlocal reads
        reads += 1
        cases, labels = original()
        if reads > 1:
            labels["h02"] = live.dataset.Expected(expected_target_ref="e0")
        return cases, labels

    class HTTP(httpx.AsyncBaseTransport):
        def __init__(self, **kwargs):
            pass

        async def handle_async_request(self, request):
            return httpx.Response(200, json=reply(request, "need_more_context"))

    monkeypatch.setattr(live.dataset, "load_dataset", changing_source)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    result = await live.run_replay(tmp_path / "run", frozen["sha256"], "test-key")
    assert all(r["correct"] for r in result["rows"] if r["case_id"] == "h02")


@pytest.mark.parametrize("mode,primary", [("llm", "none"), ("jev-fallback", "none"), ("jev-fallback", "candidate")])
async def test_candidate_strategy_uses_shared_host_model_and_same_evidence(monkeypatch, mode, primary):
    from agent_computer_use.model_selector import ModelSelector
    from tank_backend.llm.profile import LLMProfile

    calls = []
    async def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if "questions" in payload:
            return httpx.Response(200, json=reply(request, None if primary == "candidate" else primary))
        question = json.loads(payload["messages"][1]["content"])
        choice = next(k for k, v in question["questions"]["next_action"]["criteria"].items() if isinstance(v, dict))
        return httpx.Response(200, json={"id": "f", "object": "chat.completion", "created": 1,
            "model": "f-model", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps({"choice": choice})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})

    ctx, _, _, _ = setup(monkeypatch, respond)
    ctx.runtime.configure_model("task", LLMProfile("f", "f-key", "f-model", "https://offline.invalid/v1", max_tokens=128))
    try:
        goal, snapshot, actions = selection()
        decision = await ModelSelector(use_jev=mode == "jev-fallback").choose(goal, snapshot, actions, ctx)
        assert decision.choice == "candidate" and decision.binding == actions.binding
        assert len(calls) == (2 if mode == "jev-fallback" and primary != "candidate" else 1)
        assert ctx.budget.total_tokens == len(calls) * 12
        if len(calls) == 2:
            question = json.loads(calls[1]["messages"][1]["content"])
            assert question == {k: v for k, v in calls[0].items() if k != "model"}
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("failure", ["unknown", "invalid", "revoked", "cancelled", "deadline", "budget"])
async def test_candidate_strategy_never_falls_back_after_hard_failure(monkeypatch, failure):
    from agent_computer_use.model_selector import ModelSelector
    from tank_backend.llm.profile import LLMProfile
    from tank_backend.agents.subagent import SubAgentStopped

    async def respond(request):
        data = reply(request, "none")
        if failure == "unknown":
            data.pop("usage")
        elif failure == "invalid":
            data["answers"]["next_action"]["confidence"] = True
        elif failure == "revoked":
            ctx.authorization.revoke()
        elif failure == "deadline":
            ctx.runtime.restrict_deadline(0)
        elif failure == "budget":
            ctx.budget.limit = 12
        else:
            ctx.cancel.set()
        return httpx.Response(200, json=data)

    ctx, _, sent, _ = setup(monkeypatch, respond)
    ctx.runtime.configure_model("task", LLMProfile("f", "f-key", "f-model", "https://offline.invalid/v1", max_tokens=128))
    try:
        with pytest.raises((SubAgentStopped, asyncio.CancelledError, TimeoutError)):
            await ModelSelector(use_jev=True).choose(*selection(), ctx)
        assert len(sent) == 1
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("change,expected", [
    ({"elapsed_ms": 110, "nano_usd": 50}, "no_net_gain_demonstrated_keep_disabled"),
    ({"elapsed_ms": 90, "nano_usd": 100}, "limited_pilot_gain_not_production_adoption"),
    ({"accepted": 23}, "quality_gate_failed_keep_disabled"),
    ({"unexpected_actions": 1}, "quality_gate_failed_keep_disabled"),
    ({"finished": 20}, "incomplete_no_adoption_conclusion"),
    ({"f_calls": 18, "elapsed_ms": 80, "nano_usd": 50}, "no_net_gain_demonstrated_keep_disabled"),
])
def test_strategy_conclusion_does_not_reward_failed_or_wasteful_paths(monkeypatch, change, expected):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s3_strategy as bench
    h = {"finished": 24, "accepted": 24, "unexpected_actions": 0, "elapsed_ms": 100,
         "nano_usd": 100, "f_calls": 18, "jev_calls": 0}
    j = {**h, "f_calls": 6, "jev_calls": 18, **change}
    assert bench.conclusion({"H3": h, "J3": j}, True) == expected


@pytest.mark.parametrize("bad", ['{"choice":"invented"}', '{"choice":"none","extra":1}',
                                 '{"choice":"none","choice":"ambiguous"}', 'not-json'])
async def test_fallback_rejects_bad_choice_without_additional_calls(monkeypatch, bad):
    from agent_computer_use.model_selector import ModelSelector
    from tank_backend.llm.profile import LLMProfile
    from tank_backend.agents.subagent import SubAgentStopped
    async def respond(request):
        data = json.loads(request.content)
        if "questions" in data:
            return httpx.Response(200, json=reply(request, "none"))
        return httpx.Response(200, json={"id":"f","object":"chat.completion","created":1,
            "model":"f-model","choices":[{"index":0,"finish_reason":"stop",
            "message":{"role":"assistant","content":bad}}],
            "usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}})
    ctx, _, sent, _ = setup(monkeypatch, respond)
    ctx.runtime.configure_model("task", LLMProfile("f","key","f-model","https://offline.invalid/v1",max_tokens=128))
    try:
        with pytest.raises(SubAgentStopped, match="invalid_decision"):
            await ModelSelector(use_jev=True).choose(*selection(),ctx)
        assert len(sent)==2 and ctx.budget.total_tokens==24
    finally:
        await ctx.runtime.aclose()


async def test_llm_advisor_uses_task_model_and_returns_bound_structured_action(monkeypatch):
    from agent_computer_use.advisor import LLMAdvisor
    from tank_backend.agents.subagent import SubAgentRequest
    from tank_backend.llm.profile import LLMProfile

    captured = []
    async def respond(request):
        payload = json.loads(request.content)
        advice = json.loads(payload['messages'][1]['content'])
        captured.append(advice)
        action_id = next(iter(advice['actions']))
        return httpx.Response(200, json={'id': 'advice', 'object': 'chat.completion',
            'created': 1, 'model': 'planner', 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': json.dumps({
                'kind': 'candidate', 'candidate_id': action_id})}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}})
    ctx, _, sent, _ = setup(monkeypatch, respond)
    ctx.runtime.configure_model('task', LLMProfile(
        'advisor', 'secret', 'planner', 'https://offline.invalid/v1', max_tokens=128))
    goal, snapshot, actions = selection()
    actions = replace(actions, reason='goal_progress_unverified')
    try:
        result = await LLMAdvisor().assist(SubAgentRequest('Finish task', 'Keep other data', 'task'),
                                          goal, snapshot, actions, ctx)
        assert result.kind == 'candidate' and result.binding == actions.binding
        assert result.candidate_id == actions.actions[0].id
        assert captured[0]['reason'] == 'goal_progress_unverified'
        assert set(captured[0]['actions']) == {"c1", "c2"}
        assert [item["label"] for item in captured[0]['actions'].values()] == [d.label for d in actions.details]
        assert captured[0]['context'] == 'Keep other data'
        assert ctx.budget.total_tokens == 15 and len(sent) == 1
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("body", [
    "not-json", '{"kind":"candidate","candidate_id":"a","scope":"other"}',
    '{"kind":"completed"}', '{"kind":"candidate"}',
    '{"kind":"unable","candidate_id":"a"}',
    '{"kind":"inputs","inputs":[]}',
    '{"kind":"unable","kind":"need_observation"}',
    '{"kind":"focus"}',
    '{"kind":"focus","focus":{"objective":"Prepare","completion":[]}}',
    '{"kind":"focus","focus":{"objective":"Prepare","completion":[{"key":"x","value":"1"},{"key":"x","value":"2"}]}}',
    '{"kind":"focus","candidate_id":"c1","focus":{"objective":"Prepare","completion":[{"key":"x","value":"1"}]}}',
    '{"kind":"focus","focus":{"objective":"Prepare","completion":[{"key":"x","value":"1"}],"scope":"other"}}',
])
async def test_llm_advisor_rejects_invalid_structured_reply(monkeypatch, body):
    from agent_computer_use.advisor import LLMAdvisor
    from tank_backend.agents.subagent import SubAgentRequest, SubAgentStopped
    from tank_backend.llm.profile import LLMProfile
    async def respond(request):
        return httpx.Response(200, json={"id": "advice", "object": "chat.completion", "created": 1,
            "model": "planner", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": body}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    ctx, _, sent, _ = setup(monkeypatch, respond)
    ctx.runtime.configure_model("task", LLMProfile(
        "advisor", "secret", "planner", "https://offline.invalid/v1", max_tokens=128))
    try:
        with pytest.raises(SubAgentStopped, match="invalid_advice"):
            await LLMAdvisor().assist(SubAgentRequest("Finish", "", "task"), *selection(), ctx)
        assert len(sent) == 1
    finally:
        await ctx.runtime.aclose()


async def test_llm_advisor_generates_only_declared_missing_inputs(monkeypatch):
    from agent_computer_use.advisor import LLMAdvisor
    from agent_computer_use.contracts import GoalInput
    from tank_backend.agents.subagent import SubAgentRequest
    from tank_backend.llm.profile import LLMProfile
    async def respond(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        assert payload["state"]["goal"]["inputs"][0]["source"] == "generated"
        return httpx.Response(200, json={"id": "advice", "object": "chat.completion", "created": 1,
            "model": "planner", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"kind": "inputs", "inputs": [
                    {"key": "filename", "value": "报告.pdf"}]})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    ctx, _, sent, _ = setup(monkeypatch, respond)
    ctx.runtime.configure_model("task", LLMProfile(
        "advisor", "secret", "planner", "https://offline.invalid/v1", max_tokens=128))
    goal, snapshot, actions = selection()
    try:
        for source in ("user", "generated"):
            task_goal = goal.model_copy(update={"inputs": (GoalInput(
                key="filename", purpose="Generate a descriptive PDF filename", source=source),)})
            result = await LLMAdvisor().assist(SubAgentRequest("Export", "", "task"),
                                              task_goal, snapshot, actions, ctx)
            assert result.kind == ("needs_user_input" if source == "user" else "inputs")
        assert result.inputs == (Fact(key="filename", value="报告.pdf"),)
        assert len(sent) == 1
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("allowed", [False, True])
async def test_advisor_advertises_focus_only_when_a_selector_can_receive_it(monkeypatch, allowed):
    from agent_computer_use.advisor import LLMAdvisor
    from tank_backend.agents.subagent import SubAgentRequest, SubAgentStopped
    from tank_backend.llm.profile import LLMProfile
    async def respond(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        assert payload["focus_available"] is allowed
        assert ("focus" in payload["response_schema"]["properties"]["kind"]["enum"]) is allowed
        return httpx.Response(200, json={"id": "focus", "object": "chat.completion", "created": 1,
            "model": "planner", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"kind": "focus", "focus": {
                    "objective": "Save the document", "completion": [{"key": "status:saved", "value": "yes"}]}})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    ctx, _, sent, _ = setup(monkeypatch, respond)
    ctx.runtime.configure_model("task", LLMProfile("advisor", "key", "planner", "https://offline.invalid/v1", max_tokens=128))
    try:
        advisor = LLMAdvisor(allow_focus=allowed)
        if allowed:
            result = await advisor.assist(SubAgentRequest("Save", "", "task"), *selection(), ctx)
            assert result.kind == "focus" and result.focus is not None
        else:
            with pytest.raises(SubAgentStopped, match="invalid_advice"):
                await advisor.assist(SubAgentRequest("Save", "", "task"), *selection(), ctx)
        assert len(sent) == 1 and ctx.budget.total_tokens == 15
    finally:
        await ctx.runtime.aclose()


def test_native_diagnostic_prepares_frozen_states_without_network_or_desktop(tmp_path, monkeypatch):
    from pathlib import Path
    import socket
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_replay
    def forbidden(*args, **kwargs):
        raise AssertionError("Preparation must not use network or desktop")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(s4_replay.s4_ax.computer_ax, "_load_ax", forbidden)
    frozen = s4_replay.prepare(tmp_path / "diagnostic")
    assert len(frozen["cases"]) == 4 and len(frozen["schedule"]) == 48
    assert frozen["request_limit"] == 60 and frozen["nano_usd_limit"] == 250_000_000
    assert {case["display"] for case in frozen["cases"]} == {"7", "7×", "7×8", "787"}
    assert all(len(case["actions"]["actions"]) == 44 for case in frozen["cases"])
    assert s4_replay.load_freeze(tmp_path / "diagnostic", frozen["sha256"]) == frozen
    with pytest.raises(ValueError, match="freeze"):
        s4_replay.load_freeze(tmp_path / "diagnostic", "wrong")


@pytest.mark.parametrize("advice_kind,failure", [
    ("focus", None), ("candidate", None), ("focus", "unknown"), ("focus", "http"),
    ("focus", "cancel"), ("focus", "budget"), ("focus", "capture"),
    ("focus", "cleanup"), ("focus", "cancel_cleanup"),
    ("focus", "invalid_advice"), ("focus", "semantic_miss"),
])
async def test_native_diagnostic_runs_official_sdks_without_desktop(tmp_path, monkeypatch, advice_kind, failure):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_replay
    preferred = {"7": "Multiply", "7×": "8", "7×8": "Equals", "787": "Clear"}
    next_value = {"7": "7×", "7×": "7×8", "7×8": "56", "787": "0"}
    sent = []
    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            data = json.loads(request.content)
            sent.append(data)
            if failure == "http":
                return httpx.Response(503, json={"error": "offline injected error"})
            if failure == "cancel":
                raise asyncio.CancelledError()
            question = data if "questions" in data else json.loads(data["messages"][1]["content"])
            progress = question["state"]["progress"]
            if progress.get("current_focus"):
                assert progress["current_focus"]["started_action"] == progress["verified_action_count"]
            display = next(fact["value"] for fact in question["state"]["snapshot"]["facts"]
                           if fact["key"] == "ax:value:result")
            candidates = question["questions"]["next_action"]["criteria"] if "questions" in question else question["actions"]
            label = "9" if failure == "semantic_miss" else preferred[display]
            choice = next(key for key, item in candidates.items() if isinstance(item, dict) and item["label"] == label)
            if "questions" in data:
                response = reply(request, choice)
                if failure == "unknown":
                    response["usage"] = {}
                return httpx.Response(200, json=response)
            advice = {"kind": "focus", "focus": {"objective": "Advance the calculation", "completion": [
                {"key": "ax:value:result", "value": next_value[display]}]}} if advice_kind == "focus" else {
                    "kind": "candidate", "candidate_id": choice}
            return httpx.Response(200, json={"id": "advice", "object": "chat.completion", "created": 1,
                "model": "qwen3.7-flash-2026-07-15", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "not-json" if failure == "invalid_advice" else json.dumps(advice)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    if failure == "budget":
        original_freeze = s4_replay.freeze_inputs
        def limited():
            frozen = original_freeze()
            frozen.pop("sha256")
            frozen["request_limit"] = 0
            frozen["sha256"] = s4_replay.digest(frozen)
            return frozen
        monkeypatch.setattr(s4_replay, "freeze_inputs", limited)
    if failure == "capture":
        from benchmarks.computer_use.jev_smoke import Capture
        async def reject_capture(*args):
            raise OSError("Capture unavailable")
        monkeypatch.setattr(Capture, "request", reject_capture)
    if failure in ("cleanup", "cancel_cleanup"):
        from tank_backend.agents.task_runtime import TaskRuntime
        close = TaskRuntime.aclose
        async def failed_close(runtime):
            await close(runtime)
            if failure == "cancel_cleanup":
                raise asyncio.CancelledError()
            raise RuntimeError("Cleanup unconfirmed")
        monkeypatch.setattr(TaskRuntime, "aclose", failed_close)
    output = tmp_path / "diagnostic"
    frozen = s4_replay.prepare(output)
    if failure in ("cancel", "cancel_cleanup"):
        with pytest.raises(asyncio.CancelledError):
            await s4_replay.run_batch(output, frozen["sha256"], jev_credential="test", advisor_credential="test")
        result = json.loads((output / "result.json").read_text())
    else:
        result = await s4_replay.run_batch(output, frozen["sha256"], jev_credential="test", advisor_credential="test")
    if failure not in (None, "invalid_advice", "semantic_miss"):
        assert not result["completed"] and len(result["rows"]) == 48
        assert result["spend"]["stop_reason"] is not None
        assert len(sent) == (0 if failure in ("budget", "capture") else 1)
        assert sum(row["status"] == "not_run" for row in result["rows"]) == 47
        assert result["rows"][0]["desktop_operations"] == 0
        return
    assert result["completed"] and len(result["rows"]) == 48
    if failure == "invalid_advice":
        assert sum(row["classification"] == "invalid" for row in result["rows"]) == 12
    else:
        assert all(row["classification"] == ("other_action" if failure == "semantic_miss" else "preferred")
                   for row in result["rows"])
    assert all(row["desktop_operations"] == 0 and row["cleanup_confirmed"] for row in result["rows"])
    uses_focus = advice_kind == "focus" and failure != "invalid_advice"
    assert len(sent) == (60 if uses_focus else 48)
    assert result["spend"]["batch"]["admitted_requests"] == len(sent)
    assert result["spend"]["batch"]["known_tokens"] == (756 if uses_focus else 612)


async def test_native_diagnostic_refuses_existing_results_before_admission(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_replay
    async def forbidden(*args):
        raise AssertionError("Existing artifacts must stop admission")
    monkeypatch.setattr(s4_replay, "select_frozen", forbidden)
    output = tmp_path / "diagnostic"
    frozen = s4_replay.prepare(output)
    (output / "result.json").write_text("prior evidence")
    with pytest.raises(FileExistsError):
        await s4_replay.run_batch(output, frozen["sha256"], jev_credential="test", advisor_credential="test")
    assert (output / "result.json").read_text() == "prior evidence"
    assert not (output / "started.json").exists()


async def test_native_diagnostic_stops_when_recipe_changes_between_rows(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_replay
    output = tmp_path / "diagnostic"
    frozen = s4_replay.prepare(output)
    sent = []
    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent.append(request)
            changed = json.loads((output / "freeze.json").read_text())
            changed["seconds_per_trial"] += 1
            (output / "freeze.json").write_text(json.dumps(changed))
            return httpx.Response(200, json=reply(request))
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    with pytest.raises(ValueError, match="freeze"):
        await s4_replay.run_batch(output, frozen["sha256"], jev_credential="test", advisor_credential="test")
    result = json.loads((output / "result.json").read_text())
    assert len(sent) == 1 and len(result["rows"]) == 48
    assert result["spend"]["stop_reason"] == "batch_error"
    assert sum(row["status"] == "not_run" for row in result["rows"]) == 47


def test_native_diagnostic_history_comes_only_from_prior_verified_readbacks(monkeypatch):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]))
    from benchmarks.computer_use import s4_replay
    cases = {case["id"]: case for case in s4_replay.build_cases()}
    assert [step["label"] for step in cases["repair-787"]["actions"]["progress"]["recent_steps"]] == ["7", "8", "7"]
    history = cases["after-operator"]["actions"]["progress"]["recent_steps"]
    assert [step["label"] for step in history] == ["7", "8", "7", "Clear", "7", "Multiply"]
    assert history[-1]["changes"] == [{"key": "ax:value:result", "before": "7", "after": "7×"}]
    assert all(step["effect_status"] == "verified" for step in history)
    assert cases["repair-787"]["archived_question_derived"]
    case = cases["repair-787"]
    assert s4_replay.classify(case, "current", "Delete", None) == "repair_alternative"
    assert s4_replay.classify(case, "grounding", "Delete", None) == "other_action"
