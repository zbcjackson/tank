"""Provider calls are usable independently of task/runtime/HTTP governance."""

import httpx2
import pytest


def response(choice="a"):
    return {
        "model": "jev-1.13.0",
        "answers": {
            "next_action": {
                "type": "choice",
                "choice": choice,
                "confidence": 1.0,
                "probabilities": {"a": 1.0, "b": 0.0},
            }
        },
        "usage": {"input_tokens": 7, "output_tokens": 2},
    }


async def test_standalone_decision_model_has_no_task_or_custom_transport(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx2.Response(200, json=response())

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone",
            "jev-1.13.0",
            "TEST_KEY",
        ),
        credential="secret",
    )
    try:
        result = await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert result.choice == "a"
        assert (result.input_tokens, result.output_tokens) == (7, 2)
        assert len(calls) == 1
        assert calls[0].headers["authorization"] == "Bearer secret"
    finally:
        await model.aclose()


@pytest.mark.parametrize("allow_text,max_bytes,reason", [
    (True, 1024, None), (True, 32, "model_request_too_large"),
    (False, 1024, "model_data_denied"),
])
async def test_task_decision_respects_host_data_scope_before_sdk_creation(
    monkeypatch, allow_text, max_bytes, reason,
):
    import asyncio

    from typesafe_sdk import AsyncTypeSafeClient

    from tank_backend.agents.subagent import (
        SubAgentAuthorization,
        SubAgentBudget,
        SubAgentContext,
        SubAgentStopped,
    )
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.model_data import ModelDataScope

    created, requests = [], []
    original = AsyncTypeSafeClient.__init__

    def initialize(self, *args, **kwargs):
        created.append(True)
        original(self, *args, **kwargs)

    def respond(request):
        requests.append(request)
        return httpx2.Response(200, json=response())

    monkeypatch.setattr(AsyncTypeSafeClient, "__init__", initialize)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
        model_data_scope=ModelDataScope(frozenset({"text"} if allow_text else set()), max_bytes),
    )
    ctx.runtime.configure_decision_model("data-task", DecisionModelProfile(
        "https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"), credential="fake")
    model = ctx.runtime.decision_model
    assert model is not None
    try:
        if reason:
            with pytest.raises(SubAgentStopped, match=reason):
                await model.choose(state={"name": "中"}, instructions="Choose",
                                   options={"a": "A", "b": "B"})
            assert created == requests == [] and ctx.budget.call_count == 0
        else:
            assert (await model.choose(state={"name": "中"}, instructions="Choose",
                                       options={"a": "A", "b": "B"})).choice == "a"
            assert len(created) == len(requests) == 1 and ctx.budget.total_tokens == 9
    finally:
        await ctx.runtime.aclose()


async def test_bad_choice_retains_known_usage(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile

    monkeypatch.setattr(
        httpx2,
        "AsyncHTTPTransport",
        lambda **kw: httpx2.MockTransport(
            lambda request: httpx2.Response(200, json=response("unoffered"))
        ),
    )
    model = DecisionModel(
        DecisionModelProfile(
            "https://offline.invalid/v1/systemone",
            "jev-1.13.0",
            "TEST_KEY",
        ),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError) as error:
            await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert (error.value.input_tokens, error.value.output_tokens) == (7, 2)
    finally:
        await model.aclose()


@pytest.mark.parametrize("failure", ["disabled", "enter", "update", "exit"])
async def test_optional_observability_never_changes_decision(monkeypatch, failure):
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.observability import model_observation as telemetry

    calls = []

    async def respond(request):
        calls.append(request)
        return httpx2.Response(200, json=response())

    class Span:
        def __enter__(self):
            if failure == "enter":
                raise RuntimeError("tracing unavailable")
            return self

        def update(self, **kwargs):
            if failure == "update":
                raise RuntimeError("tracing unavailable")

        def __exit__(self, *args):
            if failure == "exit":
                raise RuntimeError("tracing unavailable")

    class Client:
        def start_as_current_observation(self, **kwargs):
            return Span()

    monkeypatch.setattr(
        telemetry, "get_langfuse", lambda: None if failure == "disabled" else Client()
    )
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    try:
        result = await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert result.choice == "a" and result.input_tokens == 7 and len(calls) == 1
    finally:
        await model.aclose()


async def test_failed_decision_trace_keeps_usage_and_error_level(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.observability import model_observation as telemetry

    updates = []

    class Span:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def update(self, **kwargs):
            updates.append(kwargs)

    class Client:
        def start_as_current_observation(self, **kwargs):
            return Span()

    monkeypatch.setattr(telemetry, "get_langfuse", lambda: Client())
    monkeypatch.setattr(
        httpx2,
        "AsyncHTTPTransport",
        lambda **kw: httpx2.MockTransport(
            lambda request: httpx2.Response(200, json=response("unoffered"))
        ),
    )
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError):
            await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert any(u.get("level") == "ERROR" for u in updates)
        assert any(
            u.get("usage_details") == {"input_tokens": 7, "output_tokens": 2} for u in updates
        )
    finally:
        await model.aclose()


async def test_choice_is_bound_to_options_at_invocation(monkeypatch):
    import json

    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile

    options: dict[str, object] = {"a": "A", "b": "B"}

    async def respond(request):
        assert set(json.loads(request.content)["questions"]["next_action"]["criteria"]) == {
            "a",
            "b",
        }
        options["late"] = "Not offered in this invocation"
        data = response("late")
        data["answers"]["next_action"]["probabilities"] = {"a": 0.0, "b": 0.0, "late": 1.0}
        return httpx2.Response(200, json=data)

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError, match="invalid_decision"):
            await model.choose(state={}, instructions="Choose", options=options)
    finally:
        await model.aclose()


async def test_task_choice_capture_and_sdk_share_input_snapshot(monkeypatch):
    import asyncio
    import json

    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.task_decision_model import TaskDecisionModel

    ticket, option = {"text": "original"}, {"label": "original"}
    state: dict[str, object] = {"ticket": ticket}
    options: dict[str, object] = {"a": option, "b": "B"}
    captured = []

    class Capture:
        async def request(self, call_id, request):
            import copy

            captured.append(copy.deepcopy(request.parameters))
            request.parameters["state"] = {"recorder": "redacted"}
            ticket["text"] = "changed"
            option["label"] = "changed"
            options["late"] = "Not in the captured question"
            await asyncio.sleep(0)

        async def response(self, call_id, response):
            pass

    async def respond(request):
        assert json.loads(request.content) == captured[0]
        return httpx2.Response(200, json=response())

    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY"),
        credential="secret",
    )
    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})),
        SubAgentBudget(),
        asyncio.Event(),
        model_capture=Capture(),
    )
    task_model = TaskDecisionModel("task", context, model)
    try:
        result = await task_model.choose(state=state, instructions="Choose", options=options)
        assert result.choice == "a" and context.budget.total_tokens == 9
    finally:
        await task_model.aclose()
        await model.aclose()


async def test_invalid_sdk_configuration_allocates_no_http_client(monkeypatch):
    from typesafe_sdk import TypeSafeError

    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile

    clients = []
    original = httpx2.AsyncClient

    def client(**kwargs):
        created = original(**kwargs)
        clients.append(created)
        return created

    monkeypatch.setattr(httpx2, "AsyncClient", client)
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "KEY"),
        credential="invalid key",
    )
    try:
        with pytest.raises(TypeSafeError):
            await model.choose(state={}, instructions="Choose", options={"a": "A"})
        assert clients == []
    finally:
        await model.aclose()
        for allocated in clients:
            await allocated.aclose()


async def test_official_sdk_owns_default_http_client(monkeypatch):
    from tank_backend.llm import decision_model as module
    from tank_backend.llm.decision_profile import DecisionModelProfile

    clients, configurations = [], []
    sdk_class, http_factory = module.AsyncTypeSafeClient, httpx2.AsyncClient

    def sdk(**kwargs):
        assert "http_client" not in kwargs and "transport" not in kwargs
        configurations.append(kwargs)
        return sdk_class(**kwargs)

    def http(**kwargs):
        assert "trust_env" not in kwargs and "follow_redirects" not in kwargs
        assert kwargs.get("transport") is None
        client = http_factory(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(module, "AsyncTypeSafeClient", sdk)
    monkeypatch.setattr(httpx2, "AsyncClient", http)
    monkeypatch.setattr(
        httpx2,
        "AsyncHTTPTransport",
        lambda **kw: httpx2.MockTransport(lambda request: httpx2.Response(200, json=response())),
    )
    model = module.DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "KEY"),
        credential="secret",
    )
    try:
        assert clients == []
        result = await model.choose(state={}, instructions="Choose", options={"a": "A", "b": "B"})
        assert result.choice == "a"
        assert len(clients) == len(configurations) == 1
        assert configurations[0]["timeout"] == 30
        assert configurations[0]["retry"].max_retries == 0
        assert clients[0].trust_env and not clients[0].follow_redirects
        assert not clients[0].is_closed
    finally:
        await model.aclose()
    assert clients[0].is_closed


async def test_task_decision_error_survives_unknown_usage_stop(monkeypatch):
    import asyncio
    import json

    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )
    from tank_backend.llm.decision_model import DecisionModel
    from tank_backend.llm.decision_profile import DecisionModelProfile
    from tank_backend.llm.task_decision_model import TaskDecisionModel

    events, requests = [], []
    class Observer:
        def on_event(self, kind, metadata):
            events.append((kind, metadata))
    async def respond(request):
        requests.append(request)
        return httpx2.Response(401, json={"error": "private-body-secret"},
                               headers={"x-private": "private-header-secret"})
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    url = "https://offline.invalid/v1/systemone"
    ledger = SpendLedger(SpendLimit(10000, 1000000), request_limit=1)
    ledger.start_trial("trial", SpendLimit(10000, 1000000))
    policy = BenchmarkModelPolicy(ledger, (ContextWindowContract(
        url, "jev-1.13.0", TokenAllowance(100, 100, 42, 0), "test", output_cap_required=False),))
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(),
                          asyncio.Event(), observer=Observer(), model_policy=policy)
    model = DecisionModel(
        DecisionModelProfile(url, "jev-1.13.0", "KEY"), credential="private-key-secret",
    )
    task = TaskDecisionModel("task", ctx, model)
    try:
        with pytest.raises(SpendLimitExceeded, match="unknown_usage"):
            await task.choose(state={}, instructions="Choose", options={"a": "A"})
        errors = [data for kind, data in events if kind == "decision_error"]
        assert len(errors) == 1
        assert errors[0]["error_type"] == "TypeSafeAuthenticationError"
        assert errors[0]["http_status"] == 401
        assert errors[0]["task_id"] == "task" and errors[0]["call_id"]
        assert len(requests) == 1
        assert "private-" not in json.dumps(events)
        assert ledger.snapshot()["stop_reason"] == "unknown_usage"
    finally:
        await task.aclose()
        await model.aclose()
        ledger.close()


async def test_connection_failure_diagnostics_exclude_private_message(monkeypatch):
    from tank_backend.llm.decision_model import DecisionModel, DecisionModelError
    from tank_backend.llm.decision_profile import DecisionModelProfile

    requests = []
    async def respond(request):
        requests.append(request)
        raise httpx2.ConnectError("private-proxy-credentials", request=request)
    monkeypatch.setattr(httpx2, "AsyncHTTPTransport", lambda **kw: httpx2.MockTransport(respond))
    model = DecisionModel(
        DecisionModelProfile("https://offline.invalid/v1/systemone", "jev-1.13.0", "KEY"),
        credential="secret",
    )
    try:
        with pytest.raises(DecisionModelError) as error:
            await model.choose(state={}, instructions="Choose", options={"a": "A"})
        assert error.value.diagnostics == {
            "error_type": "TypeSafeAPIConnectionError", "http_status": None,
            "cause_type": "ConnectError",
        }
        assert "private-" not in str(error.value.diagnostics)
        assert len(requests) == 1
    finally:
        await model.aclose()
