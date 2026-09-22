"""Budget admission and settlement through the actual LLM/SDK/HTTP boundary."""

import asyncio
import json

import httpx
import pytest
from openai import APIConnectionError, AsyncOpenAI


async def test_journal_failure_during_driver_finish_releases_contexts(tmp_path, monkeypatch):
    import os
    from unittest.mock import Mock

    from tank_backend.benchmarks.driver import DriverResult, SubAgentDriver
    from tank_backend.benchmarks.request_budget import RequestLimits, active_request_budget
    from tank_backend.benchmarks.spend_http import SpendControl, active_spend_session
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded
    from tank_backend.benchmarks.trace import TraceSink

    ledger = SpendLedger(SpendLimit(100, 1000), journal=tmp_path / "spend.jsonl")
    control = SpendControl(ledger, SpendLimit(100, 1000), ())
    driver = SubAgentDriver(Mock(), Mock(), Mock(), Mock())
    driver._request_limits = RequestLimits()
    driver._spend = control

    def fail_sync(fd):
        raise OSError("disk failed at finish")

    async def run(*args, **kwargs):
        monkeypatch.setattr(os, "fsync", fail_sync)
        return DriverResult("done", 0, 0, 0, 0, False, None)

    monkeypatch.setattr(driver, "_run", run)
    trace = TraceSink(tmp_path / "trial")
    old_spend, old_request = active_spend_session.get(), active_request_budget.get()
    try:
        with pytest.raises(SpendLimitExceeded, match="persistence_error"):
            await driver.run("test", trace, timeout_s=1, max_steps=1)
        assert active_spend_session.get() is old_spend
        assert active_request_budget.get() is old_request
        assert control.active is None
        assert driver._request_budget is not None and not driver._request_budget.active
    finally:
        monkeypatch.undo()
        ledger.close()
        trace.close()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("durable", [False, True])
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
        "write_error",
        "request_limit",
    ],
)
async def test_http_request_reserves_before_transport_and_settles_sdk_usage(
    monkeypatch,
    tmp_path,
    stream,
    usage_case,
    durable,
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

    journal = tmp_path / "spend.jsonl" if durable or usage_case == "write_error" else None
    ledger = SpendLedger(
        SpendLimit(49 if usage_case == "limit" else 100, 1000), journal=journal,
        request_limit=0 if usage_case == "request_limit" else 1,
    )
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
        if journal is not None:
            saved = json.loads(journal.read_text().splitlines()[-1])
            assert saved["batch"]["reserved_tokens"] == 50
            assert saved["requests"][session.pending]["status"] == "pending"
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
    if usage_case == "write_error":
        import os

        original_sync = os.fsync

        def fail_once(fd):
            monkeypatch.setattr(os, "fsync", original_sync)
            raise OSError("reservation sync failed")

        monkeypatch.setattr(os, "fsync", fail_once)

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
        elif usage_case in {"limit", "read_error", "cancelled", "write_error", "request_limit"}:
            error = (
                APIConnectionError
                if usage_case in {"limit", "write_error", "request_limit"}
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
        ledger.close()
    assert len(sent) == (0 if usage_case in {"limit", "write_error", "request_limit"} else 1)
    assert actions == []
    snapshot = ledger.snapshot()
    assert snapshot["batch"]["admitted_requests"] == len(snapshot["requests"])
    if usage_case in {"limit", "request_limit"}:
        assert snapshot["requests"] == {}
        assert snapshot["stop_reason"] == (
            "batch_tokens" if usage_case == "limit" else "batch_requests"
        )
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
    if usage_case == "write_error":
        assert snapshot["stop_reason"] == "persistence_error"
        assert not any(row["kind"] == "http_request" for row in records)
        return
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
