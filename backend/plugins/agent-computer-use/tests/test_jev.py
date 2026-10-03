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
