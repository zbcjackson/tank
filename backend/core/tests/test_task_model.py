"""Task model service uses the real SDK, replacing only outbound HTTP."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentContext,
    SubAgentStopped,
)
from tank_backend.llm.profile import LLMProfile


@pytest.fixture
def model_stack(monkeypatch, request):
    requests, released = [], []
    payload = {
        "id": "reply", "object": "chat.completion", "created": 1, "model": "test",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ready"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    }

    async def respond(request):
        return httpx.Response(200, json=payload)

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            requests.append(request)
            return await respond(request)

        async def aclose(self):
            released.append(True)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
    )
    profile = LLMProfile(
        "advisor", "secret", "test", "https://offline.invalid/v1", max_tokens=20,
        temperature=getattr(request, "param", 0.7),
    )
    context.runtime.configure_model("task", profile)
    return context, profile, payload, requests, released


@pytest.mark.parametrize("stop", ["revoked", "cancelled", "deadline", "budget", "closed"])
async def test_text_model_stopped_before_http_creation(model_stack, stop):
    context, _, _, requests, released = model_stack
    model = context.runtime.model
    assert model is not None
    if stop == "revoked":
        context.authorization.revoke()
    elif stop == "cancelled":
        context.cancel.set()
    elif stop == "deadline":
        # Build an already expired task before assembly: even model setup must reject it.
        expired = replace(context, deadline=0)
        with pytest.raises(TimeoutError):
            expired.runtime.configure_model("task", model_stack[1])
        await context.runtime.aclose()
    elif stop == "budget":
        context.budget.limit = 10
        context.budget.record("previous", 7, 3)
    else:
        await context.runtime.aclose()
    try:
        with pytest.raises((SubAgentStopped, asyncio.CancelledError)):
            await model.complete([{"role": "user", "content": "late"}])
    finally:
        await context.runtime.aclose()
    assert requests == released == []


@pytest.mark.parametrize(
    "invalid", ["choices", "truncated", "refusal", "usage", "tool_calls", "function_call"],
)
async def test_invalid_model_reply_keeps_usage_and_stops(model_stack, invalid):
    context, _, payload, requests, released = model_stack
    model = context.runtime.model
    assert model is not None
    if invalid == "choices":
        payload["choices"] = []
    elif invalid == "truncated":
        payload["choices"][0]["finish_reason"] = "length"
    elif invalid == "refusal":
        payload["choices"][0]["message"]["refusal"] = "secret"
    elif invalid in {"tool_calls", "function_call"}:
        function = {"name": "unsupported", "arguments": "{}"}
        payload["choices"][0]["message"][invalid] = (
            [{"id": "call", "type": "function", "function": function}]
            if invalid == "tool_calls" else function
        )
    else:
        payload.pop("usage")
    try:
        with pytest.raises(SubAgentStopped, match="model_error") as caught:
            await model.complete([{"role": "user", "content": "hello"}])
        assert "secret" not in str(caught.value)
        assert context.budget.total_tokens == (0 if invalid == "usage" else 10)
        assert len(context.budget.unknown_calls) == (1 if invalid == "usage" else 0)
    finally:
        await context.runtime.aclose()
    assert len(requests) == 1 and released == [True]


async def test_model_cannot_be_rebound_or_replaced(model_stack):
    context, profile, _, requests, _ = model_stack
    try:
        with pytest.raises(ValueError, match="different task"):
            context.runtime.configure_model("another", profile)
        with pytest.raises(ValueError, match="already configured"):
            context.runtime.configure_model("task", profile)
    finally:
        await context.runtime.aclose()
    assert requests == []


@pytest.mark.parametrize("status", [307, 429, 503])
async def test_http_failures_never_retry_or_expose_provider_body(model_stack, monkeypatch, status):
    context, _, _, _, _ = model_stack
    sent, closed = [], []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent.append(request)
            return httpx.Response(status, text="provider secret", headers={
                "location": "https://unapproved.invalid/steal",
            })

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    model = context.runtime.model
    assert model is not None
    try:
        with pytest.raises(SubAgentStopped, match="model_error") as caught:
            await model.complete([{"role": "user", "content": "hello"}])
        assert "provider secret" not in str(caught.value)
        assert len(context.budget.unknown_calls) == 1
    finally:
        await context.runtime.aclose()
    assert len(sent) == 1 and closed == [True]


@pytest.mark.parametrize("stop", ["cancel", "close", "revoke"])
async def test_inflight_model_shutdown_joins_http(model_stack, monkeypatch, stop):
    context, _, payload, _, _ = model_stack
    started, finish = asyncio.Event(), asyncio.Event()
    events = []

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            events.append("send")
            started.set()
            try:
                await finish.wait()
                return httpx.Response(200, json=payload)
            finally:
                events.append("joined")

        async def aclose(self):
            events.append("closed")

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    model = context.runtime.model
    assert model is not None
    caller = asyncio.create_task(model.complete([{"role": "user", "content": "hello"}]))
    await started.wait()
    if stop == "cancel":
        context.cancel.set()
    elif stop == "close":
        await context.runtime.aclose()
    else:
        context.authorization.revoke()
        finish.set()
    with pytest.raises((asyncio.CancelledError, SubAgentStopped)):
        await caller
    await context.runtime.aclose()
    assert events == ["send", "joined", "closed"]
    assert context.budget.total_tokens == (10 if stop == "revoke" else 0)
    assert len(context.budget.unknown_calls) == (0 if stop == "revoke" else 1)


@pytest.mark.parametrize("model_stack", [None, 0.25], indirect=True)
async def test_shared_completion_preserves_task_request_and_single_accounting(
    model_stack, monkeypatch,
):
    from tank_backend.llm import llm as module

    context, profile, _, requests, released = model_stack

    def forbidden(*args, **kwargs):
        pytest.fail("task requests must borrow the governed client without extra initialization")

    monkeypatch.setattr(module, "initialize_langfuse", forbidden)
    monkeypatch.setattr(module, "AsyncOpenAI", forbidden)
    model = context.runtime.model
    assert model is not None
    try:
        for text in ("first", "second"):
            assert await model.complete([{"role": "user", "content": text}]) == "ready"
            expected = {
                "model": "test", "messages": [{"role": "user", "content": text}],
                "max_tokens": 20, "stream": False,
            }
            if profile.temperature is not None:
                expected["temperature"] = profile.temperature
            assert json.loads(requests[-1].content) == expected
        assert context.budget.total_tokens == 20
        assert not context.budget.unknown_calls
    finally:
        await context.runtime.aclose()
    assert len(requests) == 2 and released == [True]


async def test_governed_client_does_not_export_payload_through_global_sdk_wrappers(
    model_stack, monkeypatch,
):
    from functools import wraps

    from openai.resources.chat.completions import AsyncCompletions

    traced = []
    original = AsyncCompletions.create

    @wraps(original)
    async def external_tracing(self, *args, **kwargs):
        traced.append(kwargs)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(AsyncCompletions, "create", external_tracing)
    context, _, _, requests, _ = model_stack
    assert context.runtime.model is not None
    try:
        response = await context.runtime.model.complete([{"role": "user", "content": "private"}])
        assert response == "ready"
    finally:
        await context.runtime.aclose()
    assert len(requests) == 1 and traced == []


async def test_text_model_allows_only_pinned_non_thinking_flag(model_stack):
    context, profile, _, requests, _ = model_stack
    await context.runtime.aclose()
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
    )
    configured = replace(profile, extra_body={"enable_thinking": False})
    ctx.runtime.configure_model("task", configured)
    configured.extra_body["enable_thinking"] = True
    try:
        assert ctx.runtime.model is not None
        assert await ctx.runtime.model.complete([{"role": "user", "content": "hello"}]) == "ready"
        assert json.loads(requests[-1].content)["enable_thinking"] is False
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("extra", [
    {"enable_thinking": True}, {"enable_thinking": 0},
    {"enable_thinking": False, "max_tokens": 999}, {"other": False},
])
def test_text_model_rejects_unapproved_generation_parameters(extra):
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
    )
    with pytest.raises(ValueError):
        ctx.runtime.configure_model(
            "task", LLMProfile("f", "key", "f", "https://offline.invalid/v1", extra_body=extra),
        )


async def test_core_decision_model_uses_official_sdk_and_original_ledger(monkeypatch):
    from typesafe_sdk import AsyncTypeSafeClient

    from tank_backend.llm.decision_profile import DecisionModelProfile

    calls, sdk_calls, closed = [], [], []
    original = AsyncTypeSafeClient.system_one

    async def system_one(self, *args, **kwargs):
        sdk_calls.append(True)
        return await original(self, *args, **kwargs)

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            calls.append(request)
            return httpx.Response(200, json={
                "model": "jev-1.13.0", "answers": {"next_action": {
                    "type": "choice", "choice": "billing", "confidence": 1.0,
                    "probabilities": {"billing": 1.0, "technical": 0.0},
                }}, "usage": {"input_tokens": 9, "output_tokens": 2},
            })

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(AsyncTypeSafeClient, "system_one", system_one)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"network"})),
                          SubAgentBudget(), asyncio.Event())
    ctx.runtime.configure_decision_model("task", DecisionModelProfile(
        "typesafe", "https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY",
    ), credential="host-secret")
    model = ctx.runtime.decision_model
    assert model is not None
    assert calls == sdk_calls == closed == []
    result = await model.choose(state={"ticket": "charged twice"}, instructions="Route ticket",
                                options={"billing": "Billing", "technical": "Technical"})
    assert result.choice == "billing" and result.confidence == 1.0
    assert ctx.budget.total_tokens == 11 and ctx.budget.call_count == 1
    assert len(calls) == len(sdk_calls) == 1
    assert calls[0].headers["authorization"] == "Bearer host-secret"
    assert json.loads(calls[0].content)["questions"]["next_action"]["criteria"] == {
        "billing": "Billing", "technical": "Technical",
    }
    await ctx.runtime.aclose()
    assert closed == [True]
    with pytest.raises(SubAgentStopped):
        await model.choose(state={}, instructions="Route", options={"a": "A"})
    assert len(calls) == 1


def test_legacy_json_model_configuration_is_explicitly_rejected(tmp_path):
    from tank_backend.agents.definition import parse_agent_file
    from tank_backend.config.app_config import AppConfig, ConfigError

    with pytest.raises(ConfigError, match="decision_models"):
        AppConfig.from_raw_dict({"llm": {"default": {"api_key": "x", "model": "x"}},
                                 "json_models": {}})
    path = tmp_path / "legacy.md"
    path.write_text("---\nname: legacy\nextension: fake:agent\njson-model: old\n---\nTask")
    with pytest.raises(ValueError, match="decision-model"):
        parse_agent_file(path)


@pytest.mark.parametrize("status", [302, 429, 503])
async def test_decision_sdk_has_no_hidden_retry_or_redirect(monkeypatch, status):
    from tank_backend.llm.decision_profile import DecisionModelProfile

    sent = []

    async def respond(request):
        sent.append(request)
        return httpx.Response(status, headers={"location": "https://other.invalid/"},
                              json={"error": "provider-private-message"})

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda: httpx.MockTransport(respond))
    monkeypatch.setenv("TYPESAFE_BASE_URL", "https://other.invalid")
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-latest")
    ctx = SubAgentContext(SubAgentAuthorization(frozenset({"network"})),
                          SubAgentBudget(), asyncio.Event())
    ctx.runtime.configure_decision_model("task", DecisionModelProfile(
        "typesafe", "https://offline.invalid/v1/systemone", "jev-1.13.0", "TEST_KEY",
    ), credential="secret")
    try:
        assert ctx.runtime.decision_model is not None
        with pytest.raises(SubAgentStopped) as error:
            await ctx.runtime.decision_model.choose(state={}, instructions="Choose",
                                                    options={"a": "A"})
        assert "provider-private-message" not in str(error.value)
        assert len(sent) == 1
        assert str(sent[0].url) == "https://offline.invalid/v1/systemone"
        assert json.loads(sent[0].content)["model"] == "jev-1.13.0"
        assert len(ctx.budget.unknown_calls) == 1
    finally:
        await ctx.runtime.aclose()
