"""Real SDK requests reach only a governed, task-bound HTTP boundary."""

import asyncio

import httpx
import pytest
from openai import APIConnectionError, AsyncOpenAI

from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentContext,
    SubAgentStopped,
)
from tank_backend.core.spend_ledger import SpendLimit, TokenAllowance


async def test_zero_budget_sends_no_sdk_http_request():
    from tank_backend.llm.model_transport import ChatCompletionsRoute, TaskModelTransport

    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(500)

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event()
    )
    transport = TaskModelTransport(
        "task", context,
        limit=SpendLimit(0, 0), request_limit=0,
        routes=(ChatCompletionsRoute(
            "https://model.test/v1/chat/completions", "test-model",
            TokenAllowance(30, 20, 2, 5), "test-key",
        ),),
        credentials={"test-key": "secret"},
        inner=httpx.MockTransport(provider),
    )
    async with AsyncOpenAI(
        api_key="unused", base_url="https://model.test/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=transport),
    ) as client:
        with pytest.raises(APIConnectionError):
            await client.chat.completions.create(
                model="test-model", messages=[{"role": "user", "content": "hello"}],
                max_tokens=20,
            )
    assert sent == []
    assert transport.snapshot()["batch"]["admitted_requests"] == 0


def completion(usage=None):
    return {
        "id": "provider-id", "object": "chat.completion", "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": "done",
        }}],
        "usage": usage if usage is not None else {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
        },
    }


def governed(provider, *, context=None, **overrides):
    from tank_backend.llm.model_transport import ChatCompletionsRoute, TaskModelTransport

    default_context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event()
    )
    context = context or default_context
    options = {
        "limit": SpendLimit(100, 1000), "request_limit": 4,
        "routes": (ChatCompletionsRoute(
            "https://model.test/v1/chat/completions", "test-model",
            TokenAllowance(30, 20, 2, 5), "test-key",
        ),),
        "credentials": {"test-key": "secret"}, "inner": httpx.MockTransport(provider),
    }
    options.update(overrides)
    transport = TaskModelTransport("task", context, **options)
    client = AsyncOpenAI(
        api_key="unused", base_url="https://model.test/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=transport),
    )
    return context, transport, client


async def ask(client):
    return await client.chat.completions.create(
        model="test-model", messages=[{"role": "user", "content": "hello"}], max_tokens=20,
    )


async def test_sdk_receives_response_only_after_raw_usage_settles_once():
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    context, transport, client = governed(provider)
    async with client:
        result = await ask(client)
        assert result.choices[0].message.content == "done"
        saved = transport.snapshot()
        assert saved["batch"]["known_tokens"] == 15
        assert saved["batch"]["reserved_tokens"] == 0
        assert saved["batch"]["known_nano_usd"] == 45
        assert len(saved["requests"]) == 1
        assert context.budget.total_tokens == 15
        call_id = next(iter(saved["requests"]))
        context.budget.record(call_id, 10, 5)
        assert context.budget.total_tokens == 15
    assert sent[0].headers["authorization"] == "Bearer secret"
    assert "secret" not in str(transport.snapshot())


@pytest.mark.parametrize("usage", [
    {}, {"prompt_tokens": "10", "completion_tokens": 5, "total_tokens": 15},
    {"prompt_tokens": True, "completion_tokens": 5, "total_tokens": 6},
    {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 14},
    {"prompt_tokens": 10, "completion_tokens": -1, "total_tokens": 9},
    {"prompt_tokens": 31, "completion_tokens": 5, "total_tokens": 36},
])
async def test_untrustworthy_raw_usage_never_reaches_sdk_or_allows_next_send(usage):
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion(usage))

    context, transport, client = governed(provider)
    async with client:
        for _ in range(2):
            with pytest.raises(APIConnectionError):
                await ask(client)
        assert transport.snapshot()["stop_reason"] is not None
    assert len(sent) == 1


async def test_lost_response_retains_reservation_and_blocks_replay():
    sent = []

    async def provider(request):
        sent.append(request)
        raise httpx.ReadError("lost acknowledgement")

    context, transport, client = governed(provider)
    async with client:
        for _ in range(2):
            with pytest.raises(APIConnectionError):
                await ask(client)
        assert transport.snapshot()["batch"]["reserved_tokens"] == 50
        assert transport.snapshot()["stop_reason"] == "unknown_usage"
        assert len(context.budget.unknown_calls) == 1
    assert len(sent) == 1


@pytest.mark.parametrize("change", [
    {"url": "https://other.test/v1/chat/completions"},
    {"url": "https://model.test/v1/embeddings"},
    {"url": "https://model.test/v1/chat/completions?key=secret"},
    {"model": "other-model"}, {"stream": True}, {"max_tokens": 21},
    {"messages": [{"role": "user", "content": [{
        "type": "image_url", "image_url": {"url": "https://private.test/image"},
    }]}]},
    {"messages": [{"role": "user", "content": "x" * 65537}]},
    {"unknown_option": True},
])
async def test_destination_model_protocol_and_upload_rejected_before_send(change):
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    _, transport, sdk = governed(provider)
    async with sdk:
        async with httpx.AsyncClient(transport=transport) as client:
            data = {"model": "test-model", "max_tokens": 20,
                    "messages": [{"role": "user", "content": "hello"}]}
            data.update(change)
            url = data.pop("url", "https://model.test/v1/chat/completions")
            with pytest.raises(ValueError):
                await client.post(url, json=data)
        assert transport.snapshot()["batch"]["admitted_requests"] == 0
    assert sent == []


async def test_redirect_is_not_followed_even_if_http_client_enables_it():
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(307, headers={"location": "https://other.test/stolen"})

    _, transport, sdk = governed(provider)
    async with sdk, httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        with pytest.raises(ValueError):
            await client.post("https://model.test/v1/chat/completions", json={
                "model": "test-model", "max_tokens": 20,
                "messages": [{"role": "user", "content": "hello"}],
            })
    assert len(sent) == 1


async def test_concurrent_sdk_requests_cannot_over_reserve_task_tokens():
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []

    async def provider(request):
        sent.append(request)
        entered.set()
        await release.wait()
        return httpx.Response(200, json=completion())

    context, transport, client = governed(provider, limit=SpendLimit(75, 1000), max_pending=2)
    async with client:
        first = asyncio.create_task(ask(client))
        await entered.wait()
        try:
            with pytest.raises(APIConnectionError):
                await ask(client)
            assert transport.snapshot()["batch"]["reserved_tokens"] == 50
        finally:
            release.set()
        # Admission exhaustion stops the task, but known in-flight usage still settles.
        with pytest.raises(APIConnectionError):
            await first
    assert len(sent) == 1
    assert transport.snapshot()["batch"]["known_tokens"] == 15
    assert context.budget.total_tokens == 15


@pytest.mark.parametrize("stop", ["cancel", "deadline", "revoke", "close"])
async def test_stopped_task_has_no_late_sends(stop):
    from time import monotonic

    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    expired = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
        deadline=monotonic() - 1,
    ) if stop == "deadline" else None
    context, transport, client = governed(provider, context=expired)
    async with client:
        if stop == "cancel":
            context.cancel.set()
        elif stop == "deadline":
            pass
        elif stop == "revoke":
            context.authorization.revoke()
        else:
            await transport.aclose()
        with pytest.raises((APIConnectionError, asyncio.CancelledError)):
            await ask(client)
    assert sent == []


async def test_cancel_during_http_keeps_unknown_reservation_and_joins_request():
    entered, exited = asyncio.Event(), asyncio.Event()

    async def provider(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            exited.set()

    context, transport, client = governed(provider)
    async with client:
        pending = asyncio.create_task(ask(client))
        await entered.wait()
        context.cancel.set()
        try:
            done, _ = await asyncio.wait({pending}, timeout=1)
            assert pending in done, "task cancellation must join the in-flight HTTP request"
            with pytest.raises(asyncio.CancelledError):
                await pending
        finally:
            if not pending.done():
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
        assert exited.is_set()
        assert transport.snapshot()["stop_reason"] == "unknown_usage"
        assert transport.snapshot()["batch"]["reserved_tokens"] == 50


async def test_revocation_while_awaiting_response_settles_but_does_not_return_decision():
    async def provider(request):
        context.authorization.revoke()
        return httpx.Response(200, json=completion())

    context, transport, client = governed(provider)
    async with client:
        with pytest.raises(APIConnectionError):
            await ask(client)
    assert transport.snapshot()["batch"]["known_tokens"] == 15


async def test_close_during_http_settles_once_and_rejects_late_sdk_calls():
    entered = asyncio.Event()
    sent = []

    async def provider(request):
        sent.append(request)
        entered.set()
        await asyncio.Event().wait()

    _, transport, client = governed(provider)
    pending = asyncio.create_task(ask(client))
    await entered.wait()
    await transport.aclose()
    with pytest.raises(asyncio.CancelledError):
        await pending
    with pytest.raises(APIConnectionError):
        await ask(client)
    await client.close()
    assert len(sent) == 1
    assert transport.snapshot()["stop_reason"] == "unknown_usage"
    assert transport.snapshot()["batch"]["reserved_tokens"] == 50


async def test_context_token_budget_is_not_weaker_than_transport_limit():
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(limit=49), asyncio.Event(),
    )
    _, transport, client = governed(provider, context=context)
    async with client:
        with pytest.raises(APIConnectionError):
            await ask(client)
    assert sent == []


async def test_oversized_response_is_closed_and_retains_reservation():
    closed, chunks = [], []

    class Oversized(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(5):
                chunks.append(True)
                yield b"x" * 600_000

        async def aclose(self):
            closed.append(True)

    async def provider(request):
        return httpx.Response(200, stream=Oversized())

    _, transport, client = governed(provider)
    async with client:
        with pytest.raises(APIConnectionError):
            await ask(client)
    assert closed == [True]
    assert len(chunks) == 4
    assert transport.snapshot()["batch"]["reserved_tokens"] == 50


async def test_one_context_cannot_create_another_model_budget_before_or_after_close():
    async def provider(request):
        return httpx.Response(200, json=completion())

    context, _, client = governed(provider)
    try:
        with pytest.raises(ValueError, match="already"):
            governed(provider, context=context)
    finally:
        await client.close()
    with pytest.raises(ValueError, match="already"):
        governed(provider, context=context)


async def test_valid_usage_with_invalid_decision_is_still_charged():
    async def provider(request):
        return httpx.Response(200, json={"usage": {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
        }})

    _, transport, client = governed(provider)
    async with client:
        response = await ask(client)
        assert response.choices is None
        assert transport.snapshot()["batch"]["known_tokens"] == 15


@pytest.mark.parametrize("body", [
    b'{"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15},"usage":{}}',
    b'{"usage":{"prompt_tokens":10,"prompt_tokens":9,"completion_tokens":5,"total_tokens":15}}',
])
async def test_duplicate_usage_fields_fail_closed_before_sdk_coercion(body):
    async def provider(request):
        return httpx.Response(200, content=body)

    _, transport, client = governed(provider)
    async with client:
        with pytest.raises(APIConnectionError):
            await ask(client)
    assert transport.snapshot()["batch"]["reserved_tokens"] == 50


@pytest.mark.parametrize("temperature", [True, "0.5", {"image_url": "private"}, -1, 3])
async def test_auxiliary_fields_cannot_smuggle_unapproved_data(temperature):
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    _, transport, sdk = governed(provider)
    async with sdk, httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError):
            await client.post("https://model.test/v1/chat/completions", json={
                "model": "test-model", "max_tokens": 20, "temperature": temperature,
                "messages": [{"role": "user", "content": "hello"}],
            })
    assert sent == []


async def test_repeated_close_preserves_unconfirmed_cleanup():
    class FailingClose(httpx.MockTransport):
        async def aclose(self):
            raise RuntimeError("cleanup failed")

    def provider(request):
        return httpx.Response(200, json=completion())

    _, transport, client = governed(provider, inner=FailingClose(provider))
    for _ in range(2):
        with pytest.raises(RuntimeError, match="cleanup failed"):
            await transport.aclose()
    with pytest.raises(RuntimeError, match="cleanup failed"):
        await client.close()


async def test_revoke_before_http_send_releases_known_unsent_reservation():
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    context, transport, client = governed(provider)
    async with client:
        asyncio.get_running_loop().call_soon(context.authorization.revoke)
        with pytest.raises(SubAgentStopped):
            await transport.handle_async_request(httpx.Request(
                "POST", "https://model.test/v1/chat/completions", json={
                    "model": "test-model", "max_tokens": 20,
                    "messages": [{"role": "user", "content": "hello"}],
                },
            ))
    assert sent == []
    saved = transport.snapshot()
    assert saved["batch"]["charged_tokens"] == 0
    assert saved["sent_requests"] == 0
    assert next(iter(saved["requests"].values()))["status"] == "not_sent"
    assert context.budget.unknown_calls == set()
