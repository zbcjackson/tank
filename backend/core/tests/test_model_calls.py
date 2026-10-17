"""SDK invocation boundaries replace the retired wire/route enforcement contract."""

import asyncio
from dataclasses import dataclass

import pytest

from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentContext,
    SubAgentStopped,
)
from tank_backend.llm.model_call import TaskModelCallRunner, get_model_call
from tank_backend.llm.model_data import ModelRequest


@dataclass
class Result:
    input_tokens: int | None = 7
    output_tokens: int | None = 2


def setup(**kwargs):
    ctx = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(), **kwargs
    )
    return ctx, TaskModelCallRunner("task", ctx), ModelRequest("https://test.invalid", "test", {})


async def test_call_usage_and_events_are_once_per_invocation():
    events = []

    class Observer:
        def on_event(self, kind, metadata):
            events.append((kind, metadata))

    ctx, calls, request = setup(observer=Observer())

    async def invoke():
        return Result()

    assert await calls.run(request, invoke) == Result()
    record = get_model_call("task")
    assert record is not None and record.call_id in ctx.budget.call_ids
    assert ctx.budget.total_tokens == 9 and ctx.budget.call_count == 1
    assert len(events) == 2 and events[-1][1]["status"] == "returned"
    await calls.aclose()


async def test_oversized_request_is_rejected_before_reservation_capture_or_sdk():
    from tank_backend.llm.model_data import ModelDataScope

    activity = []

    class Policy:
        def check(self):
            pass

        def reserve(self, call_id, request):
            activity.append("reserved")

        def settle(self, call_id, inputs, outputs):
            activity.append("settled")

        def release_unsent(self, call_id):
            activity.append("released")

    class Capture:
        async def request(self, call_id, request):
            activity.append("captured")

        async def response(self, call_id, response):
            pass

    ctx, calls, _ = setup(model_policy=Policy(), model_capture=Capture(),
                          model_data_scope=ModelDataScope(max_request_bytes=10))

    async def invoke():
        activity.append("sdk")
        return Result()

    try:
        with pytest.raises(SubAgentStopped, match="model_request_too_large"):
            await calls.run(ModelRequest("https://test.invalid", "test", {"text": "中文"}), invoke)
        assert activity == [] and ctx.budget.call_count == 0
        record = get_model_call("task")
        assert record is not None and record.status == "not_started"
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("slack", [-1, 0])
async def test_request_byte_limit_counts_utf8_and_accepts_the_exact_boundary(streaming, slack):
    from tank_backend.llm.model_data import ModelDataScope

    size = len(b'{"text":"\xe4\xb8\xad"}')
    ctx, calls, _ = setup(model_data_scope=ModelDataScope(max_request_bytes=size + slack))
    request = ModelRequest("https://test.invalid", "test", {"text": "中"})
    entered = []

    class Stream:
        def __aiter__(self):
            async def chunks():
                yield Result()
            return chunks()

        async def close(self):
            pass

    async def invoke():
        entered.append(True)
        return Result()

    async def open_stream():
        entered.append(True)
        return Stream()

    async def run():
        if streaming:
            return [item async for item in calls.stream(request, open_stream)]
        return await calls.run(request, invoke)

    try:
        if slack < 0:
            with pytest.raises(SubAgentStopped, match="model_request_too_large"):
                await run()
            assert entered == [] and ctx.budget.call_count == 0
        else:
            await run()
            assert entered == [True] and ctx.budget.total_tokens == 9
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("part", [
    {"type": [], "text": "private"},
    {"type": "text", "text": "hello", "image_url": {"url": "data:image/png;base64,AA=="}},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA==", "audio": "AA=="}},
])
async def test_unknown_or_mixed_content_blocks_are_not_admitted(part):
    from tank_backend.llm.model_data import ModelDataScope

    ctx, calls, _ = setup(model_data_scope=ModelDataScope(frozenset({"text", "image"})))
    entered = []

    async def invoke():
        entered.append(True)
        return Result()

    request = ModelRequest("https://test.invalid", "test", {
        "messages": [{"role": "user", "content": [part]}],
    })
    try:
        with pytest.raises(SubAgentStopped, match="model_data_denied"):
            await calls.run(request, invoke)
        assert entered == [] and ctx.budget.call_count == 0
    finally:
        await ctx.runtime.aclose()


@pytest.mark.parametrize("stop", ["cancel", "deadline", "revoked", "closed", "limit"])
async def test_stopped_call_never_invokes_sdk(stop):
    ctx, calls, request = setup()
    invoked = []

    async def invoke():
        invoked.append(True)
        return Result()

    if stop == "cancel":
        ctx.cancel.set()
    elif stop == "deadline":
        object.__setattr__(ctx, "deadline", 0)
    elif stop == "revoked":
        ctx.authorization.revoke()
    elif stop == "limit":
        ctx.budget.limit = 1
        ctx.budget.record("prior", 1, 0)
    else:
        await calls.aclose()
    with pytest.raises((SubAgentStopped, asyncio.CancelledError, TimeoutError)):
        await calls.run(request, invoke)
    assert not invoked
    record = get_model_call("task")
    assert record is not None and record.status == "not_started"


@pytest.mark.parametrize("stop", ["cancel", "deadline", "close"])
async def test_inflight_stop_joins_sdk_and_marks_unknown(stop):
    ctx, calls, request = setup()
    started, cleaned = asyncio.Event(), asyncio.Event()

    async def invoke():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    if stop == "deadline":
        import time

        object.__setattr__(ctx, "deadline", time.monotonic() + 0.05)
    task = asyncio.create_task(calls.run(request, invoke))
    await asyncio.wait_for(started.wait(), 1)
    if stop == "cancel":
        ctx.cancel.set()
    elif stop == "close":
        await calls.aclose()
    with pytest.raises((asyncio.CancelledError, TimeoutError)):
        await task
    assert cleaned.is_set() and len(ctx.budget.unknown_calls) == 1


async def test_late_revocation_retains_usage_but_not_result():
    ctx, calls, request = setup()

    async def invoke():
        ctx.authorization.revoke()
        return Result()

    with pytest.raises(SubAgentStopped):
        await calls.run(request, invoke)
    assert ctx.budget.total_tokens == 9


async def test_error_with_known_usage_is_counted():
    from tank_backend.llm.decision_model import DecisionModelError

    ctx, calls, request = setup()

    async def invoke():
        raise DecisionModelError("bad choice", 7, 2)

    with pytest.raises(DecisionModelError):
        await calls.run(request, invoke)
    assert ctx.budget.total_tokens == 9 and not ctx.budget.unknown_calls


async def test_model_audit_and_observer_failures_do_not_block_sdk():
    events = []

    async def audit(record):
        raise RuntimeError("not a model execution gate")

    class Observer:
        def on_event(self, kind, metadata):
            events.append(kind)
            raise RuntimeError("optional telemetry")

    ctx, calls, request = setup(audit=audit, observer=Observer())

    async def invoke():
        return Result()

    assert await calls.run(request, invoke) == Result()
    assert ctx.budget.total_tokens == 9 and len(events) == 2


async def test_parallel_calls_share_usage_and_keep_distinct_ids():
    ctx, calls, request = setup()

    async def invoke():
        await asyncio.sleep(0)
        return Result()

    await asyncio.gather(*(calls.run(request, invoke) for _ in range(8)))
    assert ctx.budget.call_count == 8 and ctx.budget.total_tokens == 72


async def test_sdk_stream_checks_each_buffered_event_and_closes():
    ctx, calls, request = setup()
    closed = []

    class Stream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            return Result(None, None)

        async def close(self):
            closed.append(True)

    async def open_stream():
        return Stream()

    stream = calls.stream(request, open_stream)
    await anext(stream)
    ctx.cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await anext(stream)
    assert closed == [True] and len(ctx.budget.unknown_calls) == 1


async def test_sdk_stream_preserves_final_usage_on_normal_end():
    ctx, calls, request = setup()

    class Stream:
        def __aiter__(self):
            async def chunks():
                yield Result(None, None)
                yield Result()

            return chunks()

        async def close(self):
            pass

    async def open_stream():
        return Stream()

    assert len([x async for x in calls.stream(request, open_stream)]) == 2
    assert ctx.budget.total_tokens == 9


async def test_closing_a_paused_stream_records_usage_once():
    ctx, calls, request = setup()

    class Stream:
        def __aiter__(self):
            async def chunks():
                yield Result()
                await asyncio.Event().wait()

            return chunks()

        async def close(self):
            pass

    async def open_stream():
        return Stream()

    stream = calls.stream(request, open_stream)
    await anext(stream)
    await calls.aclose()
    assert ctx.budget.total_tokens == 9 and ctx.budget.call_count == 1
    await stream.aclose()
    assert ctx.budget.total_tokens == 9 and ctx.budget.call_count == 1


@pytest.mark.parametrize("cancel", [False, True])
async def test_real_sdk_stream_checks_buffered_chunks_and_borrows_client(cancel):
    import json

    import httpx
    from openai import AsyncOpenAI

    from tank_backend.core.events import UpdateType
    from tank_backend.llm.llm import LLM

    closed = []
    chunks = [
        {
            "id": "r",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
        }
        for text in ("a", "b")
    ]
    chunks.append(
        {
            "id": "r",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "m",
            "choices": [],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
        }
    )

    class Wire(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield (
                b"".join(("data: " + json.dumps(c) + "\n\n").encode() for c in chunks)
                + b"data: [DONE]\n\n"
            )

        async def aclose(self):
            closed.append(True)

    async with AsyncOpenAI(
        api_key="secret",
        base_url="https://offline.invalid/v1",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"content-type": "text/event-stream"}, stream=Wire()
                )
            )
        ),
    ) as client:
        ctx, _, _ = setup()
        llm = LLM(
            api_key="secret", model="m", base_url="https://offline.invalid/v1", client=client
        ).bind_task(ctx, "task")
        events = llm.chat_stream([{"role": "user", "content": "hello"}])
        first = await anext(events)
        assert first[0] == UpdateType.TEXT and first[1] == "a"
        if cancel:
            ctx.cancel.set()
            with pytest.raises(asyncio.CancelledError):
                await anext(events)
            assert len(ctx.budget.unknown_calls) == 1
        else:
            rest = [e async for e in events]
            assert [e[1] for e in rest if e[0] == UpdateType.TEXT] == ["b"]
            assert ctx.budget.total_tokens == 9 and ctx.budget.call_count == 1
        await events.aclose()
        await ctx.runtime.aclose()
        assert not client.is_closed() and closed == [True]


async def test_repeated_cancellation_and_close_join_sdk_cleanup():
    ctx, calls, request = setup()
    started, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    async def invoke():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    task = asyncio.create_task(calls.run(request, invoke))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    await asyncio.wait_for(cleaning.wait(), 1)
    task.cancel()
    closing = asyncio.create_task(calls.aclose())
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await closing
    assert cleaned.is_set()
    assert len(ctx.budget.unknown_calls) == 1


async def test_cancel_between_admission_and_sdk_entry_does_not_invoke():
    ctx, calls, request = setup()
    invoked = []

    async def invoke():
        invoked.append(True)
        return Result()

    asyncio.get_running_loop().call_soon(ctx.cancel.set)
    with pytest.raises(asyncio.CancelledError):
        await calls.run(request, invoke)
    assert invoked == []
    assert ctx.budget.call_count == 0


@pytest.mark.parametrize("revoke", [False, True])
async def test_chat_sdk_uses_private_snapshot_across_capture_await(revoke):
    import copy
    import json

    import httpx
    from openai import AsyncOpenAI
    from openai.types.chat import ChatCompletionMessageParam

    from tank_backend.llm.llm import LLM

    message: ChatCompletionMessageParam = {"role": "user", "content": "original"}
    captured, sent = [], []

    class Capture:
        async def request(self, call_id, request):
            captured.append(copy.deepcopy(request.parameters))
            message["content"] = [{"type": "image_url", "image_url": {
                "url": "data:image/png;base64,AA==",
            }}]
            request.parameters["messages"] = [message]
            await asyncio.sleep(0)
            if revoke:
                ctx.authorization.revoke()

        async def response(self, call_id, response):
            pass

    async def respond(request):
        sent.append(True)
        assert json.loads(request.content) == captured[0]
        return httpx.Response(200, json={
            "id": "r", "object": "chat.completion", "created": 1, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
        })

    async with AsyncOpenAI(
        api_key="secret", base_url="https://offline.invalid/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    ) as client:
        ctx, _, _ = setup(model_capture=Capture())
        llm = LLM(api_key="secret", model="m", base_url="https://offline.invalid/v1",
                  client=client).bind_task(ctx, "task")
        try:
            if revoke:
                with pytest.raises(SubAgentStopped):
                    await llm.complete_response([message], retry=False)
                assert sent == [] and ctx.budget.call_count == 0
            else:
                result = await llm.complete_response([message], retry=False)
                assert result.choices[0].message.content == "ok"
                assert sent == [True] and ctx.budget.total_tokens == 9
        finally:
            await ctx.runtime.aclose()
