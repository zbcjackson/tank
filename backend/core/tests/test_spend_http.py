"""Budget admission and settlement through the actual LLM/SDK/HTTP boundary."""

import asyncio
import json

import httpx
import pytest
from openai import APIConnectionError, AsyncOpenAI


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "usage_case",
    [
        "known",
        "missing",
        "mismatch",
        "overrun",
        "boolean",
        "limit",
        "read_error",
        "cancelled",
    ],
)
async def test_http_request_reserves_before_transport_and_settles_sdk_usage(
    monkeypatch,
    tmp_path,
    stream,
    usage_case,
):
    from tank_backend.benchmarks.spend_http import ContextWindowContract, SpendControl
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )
    from tank_backend.benchmarks.trace import TraceSink
    from tank_backend.llm import llm as module

    ledger = SpendLedger(SpendLimit(49 if usage_case == "limit" else 100, 1000))
    control = SpendControl(
        ledger,
        SpendLimit(100, 1000),
        (
            ContextWindowContract(
                "https://offline.invalid/v1/chat/completions",
                "test",
                TokenAllowance(30, 20, 2, 5),
                "synthetic test contract",
            ),
        ),
    )
    trace = TraceSink(tmp_path)
    session = control.start(trace)
    sent = []
    actions = []
    usage = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
    if usage_case == "mismatch":
        usage["total_tokens"] = 100
    elif usage_case == "overrun":
        usage.update(prompt_tokens=31, total_tokens=33)
    elif usage_case == "boolean":
        usage.update(prompt_tokens=True, total_tokens=3)
    response_usage = None if usage_case == "missing" else usage

    async def execute(name, args):
        actions.append(name)
        return "done"

    async def capture(request):
        request_id = session.reserve(request)
        await trace.capture_request(request, request_id=request_id)

    def respond(request):
        assert ledger.snapshot()["batch"]["reserved_tokens"] == 50
        sent.append(request)
        if usage_case in {"read_error", "cancelled"}:

            class Broken(httpx.AsyncByteStream):
                async def __aiter__(self):
                    yield b'data: {"id":"partial","choices":[]}\n\n' if stream else b"{"
                    if usage_case == "cancelled":
                        raise asyncio.CancelledError()
                    raise httpx.ReadError("synthetic read failure")

            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Broken()
            )
        if stream:
            chunks = [
                {
                    "id": "one",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "test",
                    "choices": [
                        {"index": 0, "finish_reason": "stop", "delta": {"content": "done"}}
                    ],
                },
                {
                    "id": "one",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "test",
                    "choices": [],
                    "usage": response_usage,
                },
            ]
            if usage_case != "known":
                chunks[0]["choices"][0]["delta"]["tool_calls"] = [
                    {
                        "index": 0,
                        "id": "click",
                        "type": "function",
                        "function": {"name": "click", "arguments": "{}"},
                    }
                ]
            data = (
                "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
            ).encode()

            class Fragments(httpx.AsyncByteStream):
                async def __aiter__(self):
                    for offset in range(0, len(data), 7):
                        yield data[offset : offset + 7]

            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, stream=Fragments()
            )
        return httpx.Response(
            200,
            json={
                "id": "one",
                "object": "chat.completion",
                "created": 1,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "done"},
                    }
                ],
                "usage": response_usage,
            },
        )

    client = AsyncOpenAI(
        api_key="test",
        base_url="https://offline.invalid/v1",
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            event_hooks={
                "request": [capture],
                "response": [trace.capture_response, session.capture_response],
            },
        ),
    )
    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kw: client)
    monkeypatch.setattr(module, "initialize_langfuse", lambda: None)
    llm = module.LLM(
        api_key="test",
        model="test",
        base_url="https://offline.invalid/v1",
        max_tokens=20,
        extra_body={"enable_thinking": False},
    )
    llm.disable_retries()
    llm.on_response_usage = session.settle

    async def run():
        if stream:
            updates = []
            async for u in llm.chat_stream(
                messages=[{"role": "user", "content": "hello"}],
                tool_executor=execute,
            ):
                if u[1] == "done":
                    assert ledger.snapshot()["batch"]["reserved_tokens"] == 50
                updates.append(u)
            assert any(u[1] == "done" for u in updates)
        else:
            response = await llm.complete_response(messages=[{"role": "user", "content": "hello"}])
            assert response.choices[0].message.content == "done"

    try:
        if usage_case == "known":
            await run()
        elif usage_case in {"limit", "read_error", "cancelled"}:
            error = (
                APIConnectionError
                if usage_case == "limit"
                else asyncio.CancelledError
                if usage_case == "cancelled"
                else httpx.ReadError
                if stream
                else APIConnectionError
            )
            with pytest.raises(error):
                await run()
        else:
            with pytest.raises(SpendLimitExceeded):
                await run()
    finally:
        control.finish(session)
        trace.close()
        await client.close()
    assert len(sent) == (0 if usage_case == "limit" else 1)
    assert actions == []
    snapshot = ledger.snapshot()
    if usage_case == "limit":
        assert snapshot["requests"] == {}
        assert snapshot["stop_reason"] == "batch_tokens"
        return
    if usage_case == "known":
        assert snapshot["batch"]["known_tokens"] == 5
        assert snapshot["batch"]["known_nano_usd"] == 16
    elif usage_case == "overrun":
        assert snapshot["batch"]["known_tokens"] == 33
        assert snapshot["stop_reason"] == "bound_exceeded"
    else:
        assert snapshot["batch"]["reserved_tokens"] == 50
        assert snapshot["stop_reason"] is not None
    records = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]
    request_id = next(row["request_id"] for row in records if row["kind"] == "http_request")
    assert request_id in snapshot["requests"]


@pytest.mark.parametrize(
    "change",
    [
        {"model": "other"},
        {"enable_thinking": True},
        {"enable_thinking": None},
        {"max_tokens": 21},
        {"max_tokens": True},
        {"max_tokens": 0},
        {"n": 2},
        {"enable_search": True},
        {"stream": True},
        {"stream": "true"},
    ],
)
def test_contract_mismatch_stops_batch_without_admitting_request(tmp_path, change):
    from tank_backend.benchmarks.spend_http import ContextWindowContract, SpendControl
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )
    from tank_backend.benchmarks.trace import TraceSink

    ledger = SpendLedger(SpendLimit(100, 1000))
    control = SpendControl(
        ledger,
        SpendLimit(100, 1000),
        (
            ContextWindowContract(
                "https://offline.invalid/v1/chat/completions",
                "test",
                TokenAllowance(30, 20, 2, 5),
                "synthetic test contract",
            ),
        ),
    )
    trace = TraceSink(tmp_path)
    session = control.start(trace)
    body = {
        "model": "test",
        "max_tokens": 20,
        "enable_thinking": False,
        "stream": False,
        "messages": [{"role": "user", "content": "hello"}],
        **change,
    }
    try:
        with pytest.raises(SpendLimitExceeded, match="request_contract"):
            session.reserve(
                httpx.Request("POST", "https://offline.invalid/v1/chat/completions", json=body)
            )
        assert ledger.snapshot()["requests"] == {}
        assert ledger.snapshot()["stop_reason"] == "request_contract"
    finally:
        control.finish(session)
        trace.close()


@pytest.mark.parametrize("content", ["[]", "null", "{", '{"model":"test","model":"test"}'])
def test_unparseable_request_stops_before_reservation(tmp_path, content):
    from tank_backend.benchmarks.spend_http import ContextWindowContract, SpendControl
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )
    from tank_backend.benchmarks.trace import TraceSink

    ledger = SpendLedger(SpendLimit(100, 1000))
    control = SpendControl(
        ledger,
        SpendLimit(100, 1000),
        (
            ContextWindowContract(
                "https://offline.invalid/v1/chat/completions",
                "test",
                TokenAllowance(30, 20, 2, 5),
                "synthetic",
            ),
        ),
    )
    trace = TraceSink(tmp_path)
    session = control.start(trace)
    try:
        with pytest.raises(SpendLimitExceeded):
            session.reserve(
                httpx.Request(
                    "POST", "https://offline.invalid/v1/chat/completions", content=content
                )
            )
        assert ledger.snapshot()["requests"] == {}
        assert ledger.snapshot()["stop_reason"] == "request_contract"
    finally:
        control.finish(session)
        trace.close()


@pytest.mark.parametrize(
    "evidence,url",
    [
        ("", "https://offline.invalid/v1/chat/completions"),
        ("test", "https://user:secret@offline.invalid/v1/chat/completions"),
        ("test", "http://offline.invalid/v1/chat/completions"),
    ],
)
def test_context_contract_requires_evidence_and_uncredentialed_https(evidence, url):
    from tank_backend.benchmarks.spend_http import ContextWindowContract
    from tank_backend.benchmarks.spend_ledger import TokenAllowance

    with pytest.raises(ValueError):
        ContextWindowContract(url, "test", TokenAllowance(30, 20, 2, 5), evidence)
