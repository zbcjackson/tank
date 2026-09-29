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
from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
from tank_backend.benchmarks.spend_http import ContextWindowContract
from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance


async def test_zero_budget_sends_no_sdk_http_request():
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(500)

    _, transport, client, ledger = governed(
        provider, limit=SpendLimit(0, 0), request_limit=0,
    )
    async with client:
        with pytest.raises(APIConnectionError):
            await client.chat.completions.create(
                model="test-model", messages=[{"role": "user", "content": "hello"}],
                max_tokens=20,
            )
    assert sent == []
    assert ledger.snapshot()["batch"]["admitted_requests"] == 0


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
    ledger = SpendLedger(
        overrides.pop("limit", SpendLimit(100, 1000)),
        request_limit=overrides.pop("request_limit", 4),
        max_pending=overrides.pop("max_pending", 1),
    )
    ledger.start_trial("experiment-trial", SpendLimit(100, 1000))
    policy = BenchmarkModelPolicy(ledger, (ContextWindowContract(
        "https://model.test/v1/chat/completions", "test-model",
        TokenAllowance(30, 20, 2, 5), "fixture provider ceiling",
    ),))
    options = {
        "policy": policy,
        "routes": (ChatCompletionsRoute(
            "https://model.test/v1/chat/completions", "test-model", "test-key",
            max_output_tokens=20,
        ),),
        "credentials": {"test-key": "secret"}, "inner": httpx.MockTransport(provider),
    }
    options.update(overrides)
    transport = TaskModelTransport("task", context, **options)
    client = AsyncOpenAI(
        api_key="unused", base_url="https://model.test/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=transport),
    )
    return context, transport, client, ledger


async def ask(client):
    return await client.chat.completions.create(
        model="test-model", messages=[{"role": "user", "content": "hello"}], max_tokens=20,
    )


async def test_sdk_receives_response_only_after_raw_usage_settles_once():
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    context, transport, client, ledger = governed(provider)
    async with client:
        result = await ask(client)
        assert result.choices[0].message.content == "done"
        saved = ledger.snapshot()
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

    context, transport, client, ledger = governed(provider)
    async with client:
        for _ in range(2):
            with pytest.raises(APIConnectionError):
                await ask(client)
        assert ledger.snapshot()["stop_reason"] is not None
    assert len(sent) == 1


async def test_lost_response_retains_reservation_and_blocks_replay():
    sent = []

    async def provider(request):
        sent.append(request)
        raise httpx.ReadError("lost acknowledgement")

    context, transport, client, ledger = governed(provider)
    async with client:
        for _ in range(2):
            with pytest.raises(APIConnectionError):
                await ask(client)
        assert ledger.snapshot()["batch"]["reserved_tokens"] == 50
        assert ledger.snapshot()["stop_reason"] == "unknown_usage"
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

    _, transport, sdk, ledger = governed(provider)
    async with sdk:
        async with httpx.AsyncClient(transport=transport) as client:
            data = {"model": "test-model", "max_tokens": 20,
                    "messages": [{"role": "user", "content": "hello"}]}
            data.update(change)
            url = data.pop("url", "https://model.test/v1/chat/completions")
            with pytest.raises(ValueError):
                await client.post(url, json=data)
        assert ledger.snapshot()["batch"]["admitted_requests"] == 0
    assert sent == []


async def test_redirect_is_not_followed_even_if_http_client_enables_it():
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(307, headers={"location": "https://other.test/stolen"})

    _, transport, sdk, ledger = governed(provider)
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

    context, transport, client, ledger = governed(
        provider, limit=SpendLimit(75, 1000), max_pending=2,
    )
    async with client:
        first = asyncio.create_task(ask(client))
        await entered.wait()
        try:
            with pytest.raises(APIConnectionError):
                await ask(client)
            assert ledger.snapshot()["batch"]["reserved_tokens"] == 50
        finally:
            release.set()
        # Admission exhaustion stops the task, but known in-flight usage still settles.
        with pytest.raises(APIConnectionError):
            await first
    assert len(sent) == 1
    assert ledger.snapshot()["batch"]["known_tokens"] == 15
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
    context, transport, client, ledger = governed(provider, context=expired)
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

    context, transport, client, ledger = governed(provider)
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
        assert ledger.snapshot()["stop_reason"] == "unknown_usage"
        assert ledger.snapshot()["batch"]["reserved_tokens"] == 50


async def test_revocation_while_awaiting_response_settles_but_does_not_return_decision():
    async def provider(request):
        context.authorization.revoke()
        return httpx.Response(200, json=completion())

    context, transport, client, ledger = governed(provider)
    async with client:
        with pytest.raises(APIConnectionError):
            await ask(client)
    assert ledger.snapshot()["batch"]["known_tokens"] == 15


async def test_close_during_http_settles_once_and_rejects_late_sdk_calls():
    entered = asyncio.Event()
    sent = []

    async def provider(request):
        sent.append(request)
        entered.set()
        await asyncio.Event().wait()

    _, transport, client, ledger = governed(provider)
    pending = asyncio.create_task(ask(client))
    await entered.wait()
    await transport.aclose()
    with pytest.raises(asyncio.CancelledError):
        await pending
    with pytest.raises(APIConnectionError):
        await ask(client)
    await client.close()
    assert len(sent) == 1
    assert ledger.snapshot()["stop_reason"] == "unknown_usage"
    assert ledger.snapshot()["batch"]["reserved_tokens"] == 50


async def test_explicit_context_limit_stops_after_usage_is_recorded():
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(limit=10), asyncio.Event(),
    )
    _, transport, client, ledger = governed(provider, context=context)
    async with client:
        with pytest.raises(APIConnectionError):
            await ask(client)
    assert len(sent) == 1
    assert context.budget.total_tokens == 15


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

    _, transport, client, ledger = governed(provider)
    async with client:
        with pytest.raises(APIConnectionError):
            await ask(client)
    assert closed == [True]
    assert len(chunks) == 4
    assert ledger.snapshot()["batch"]["reserved_tokens"] == 50


async def test_multiple_clients_and_recreation_share_the_same_task_usage():
    async def provider(request):
        return httpx.Response(200, json=completion())

    context, _, client, _ = governed(provider, policy=None)
    async with client:
        await ask(client)
        _, second, other, _ = governed(provider, context=context, policy=None)
        async with other:
            await ask(other)
            assert second.snapshot()["usage"]["total_tokens"] == 30
    _, third, other, _ = governed(provider, context=context, policy=None)
    async with other:
        await ask(other)
        assert third.snapshot()["usage"]["total_tokens"] == 45


async def test_valid_usage_with_invalid_decision_is_still_charged():
    async def provider(request):
        return httpx.Response(200, json={"usage": {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
        }})

    _, transport, client, ledger = governed(provider)
    async with client:
        response = await ask(client)
        assert response.choices is None
        assert ledger.snapshot()["batch"]["known_tokens"] == 15


@pytest.mark.parametrize("body", [
    b'{"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15},"usage":{}}',
    b'{"usage":{"prompt_tokens":10,"prompt_tokens":9,"completion_tokens":5,"total_tokens":15}}',
])
async def test_duplicate_usage_fields_fail_closed_before_sdk_coercion(body):
    async def provider(request):
        return httpx.Response(200, content=body)

    _, transport, client, ledger = governed(provider)
    async with client:
        with pytest.raises(APIConnectionError):
            await ask(client)
    assert ledger.snapshot()["batch"]["reserved_tokens"] == 50


@pytest.mark.parametrize("temperature", [True, "0.5", {"image_url": "private"}, -1, 3])
async def test_auxiliary_fields_cannot_smuggle_unapproved_data(temperature):
    sent = []

    async def provider(request):
        sent.append(request)
        return httpx.Response(200, json=completion())

    _, transport, sdk, ledger = governed(provider)
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

    _, transport, client, ledger = governed(provider, inner=FailingClose(provider))
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

    context, transport, client, ledger = governed(provider)
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
    saved = ledger.snapshot()
    assert saved["batch"]["charged_tokens"] == 0
    assert transport.snapshot()["sent_requests"] == 0
    assert next(iter(saved["requests"].values()))["status"] == "not_sent"
    assert context.budget.unknown_calls == set()


async def test_revocation_during_request_cleanup_prevents_decision_delivery():
    async def provider(request):
        return httpx.Response(200, json=completion())

    context, transport, client, ledger = governed(provider)

    async def revoke_after_settlement():
        while context.budget.total_tokens == 0:
            await asyncio.sleep(0)
        context.authorization.revoke()

    revoker = asyncio.create_task(revoke_after_settlement())
    try:
        async with client:
            with pytest.raises(APIConnectionError):
                await ask(client)
        assert ledger.snapshot()["batch"]["known_tokens"] == 15
    finally:
        revoker.cancel()
        await asyncio.gather(revoker, return_exceptions=True)


async def test_caller_cancel_after_response_preserves_known_usage():
    pending = asyncio.current_task()

    async def provider(request):
        assert pending is not None
        asyncio.get_running_loop().call_soon(pending.cancel)
        return httpx.Response(200, json=completion())

    context, transport, client, ledger = governed(provider)
    async with client:
        pending = asyncio.create_task(ask(client))
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert ledger.snapshot()["batch"]["known_tokens"] == 15
        assert ledger.snapshot()["batch"]["reserved_tokens"] == 0
        assert context.budget.total_tokens == 15
        assert context.budget.unknown_calls == set()


@pytest.mark.parametrize("close_order", ["after_cleanup", "first", "during_cleanup"])
async def test_repeated_caller_cancel_joins_cleanup_before_close(close_order):
    entered, cleaning, release, exited = (asyncio.Event() for _ in range(4))

    async def provider(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            exited.set()

    _, transport, client, ledger = governed(provider)
    pending = asyncio.create_task(ask(client))
    await entered.wait()
    closing = None
    if close_order == "first":
        closing = asyncio.create_task(transport.aclose())
    else:
        pending.cancel()
    await cleaning.wait()
    if close_order == "during_cleanup":
        closing = asyncio.create_task(transport.aclose())
    else:
        pending.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert exited.is_set(), "repeated cancellation must not interrupt transport cleanup"
    async with asyncio.timeout(1):
        if closing is not None:
            await closing
        await client.close()
    assert ledger.snapshot()["batch"]["reserved_tokens"] == 50


async def test_production_transport_needs_no_limits_prices_or_trial():
    from tank_backend.llm.model_transport import ChatCompletionsRoute, TaskModelTransport

    async def provider(request):
        return httpx.Response(200, json=completion({
            "prompt_tokens": 1_000_000, "completion_tokens": 5, "total_tokens": 1_000_005,
        }))

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
    )
    transport = TaskModelTransport(
        "task", context,
        routes=(ChatCompletionsRoute(
            "https://model.test/v1/chat/completions", "test-model", "test-key",
        ),),
        credentials={"test-key": "secret"}, inner=httpx.MockTransport(provider),
    )
    async with AsyncOpenAI(
        api_key="unused", base_url="https://model.test/v1", max_retries=0,
        http_client=httpx.AsyncClient(transport=transport),
    ) as client:
        for _ in range(6):
            assert (await ask(client)).choices[0].message.content == "done"
    assert context.budget.total_tokens == 6_000_030
    assert set(transport.snapshot()) == {"task_id", "sent_requests", "usage"}


async def test_record_only_transport_keeps_unknown_usage_without_latching_a_budget_stop():
    replies = iter([{}, completion()])

    async def provider(request):
        return httpx.Response(200, json=next(replies))

    context, transport, client, _ = governed(provider, policy=None)
    async with client:
        with pytest.raises(APIConnectionError):
            await ask(client)
        assert (await ask(client)).choices[0].message.content == "done"
    assert transport.snapshot()["usage"]["unknown_calls"] == 1
    assert context.budget.total_tokens == 15


async def test_transport_close_does_not_close_the_experiment_batch():
    async def provider(request):
        return httpx.Response(200, json=completion())

    _, _, client, ledger = governed(provider)
    async with client:
        await ask(client)
    ledger.finish_trial()
    ledger.start_trial("next-trial", SpendLimit(100, 1000))
    ledger.reserve("next-call", TokenAllowance(30, 20, 2, 5))
    ledger.settle("next-call", input_tokens=10, output_tokens=5)
    assert ledger.snapshot()["batch"]["known_tokens"] == 30
    ledger.close()
