"""Request admission is shared across planner and locator clients."""

import pytest


def test_request_limits_latch_denial_and_keep_failed_attempts_counted():
    from tank_backend.benchmarks.request_budget import (
        RequestBudget,
        RequestLimitExceeded,
        RequestLimits,
    )

    budget = RequestBudget(RequestLimits(planner=2, locator=1, total=2))
    budget.reserve("planner")
    budget.reserve("locator")
    with pytest.raises(RequestLimitExceeded):
        budget.reserve("planner")
    assert budget.snapshot()["total"] == 2
    assert budget.snapshot()["blocked"] is True
    with pytest.raises(RequestLimitExceeded):
        budget.reserve("locator")
    assert budget.snapshot()["total"] == 2


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_request_limits_reject_invalid_caps(value):
    from tank_backend.benchmarks.request_budget import RequestLimits

    with pytest.raises(ValueError):
        RequestLimits(planner=value)


def test_closed_request_budget_never_reopens_or_changes_its_summary():
    from tank_backend.benchmarks.request_budget import (
        RequestBudget,
        RequestLimitExceeded,
        RequestLimits,
    )

    budget = RequestBudget(RequestLimits())
    budget.reserve("planner")
    budget.active = False
    summary = budget.snapshot()
    with pytest.raises(RequestLimitExceeded):
        budget.reserve("locator")
    assert budget.snapshot() == summary


def test_request_limits_reject_uninstrumented_plugin_clients(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.benchmarks import driver as module
    from tank_backend.benchmarks.request_budget import RequestLimits

    definition = AgentDefinition("plugin", "", "", extension="test:agent")
    config = SimpleNamespace(agents=SimpleNamespace(dirs=[]))
    monkeypatch.setattr(module.AppConfig, "load", lambda _: config)
    monkeypatch.setattr(module, "load_agent_definitions", lambda _: {"plugin": definition})
    with pytest.raises(ValueError, match="built-in benchmark transport"):
        module.SubAgentDriver.create("plugin", tmp_path / "config.yaml",
                                     request_limits=RequestLimits())


async def test_task_policy_correlates_capture_usage_and_redacts_known_credentials(tmp_path):
    import asyncio
    import json

    import httpx
    from openai import AsyncOpenAI

    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.benchmarks.request_budget import RequestBudget, RequestLimits
    from tank_backend.benchmarks.task_model_policy import BenchmarkTaskPolicy
    from tank_backend.benchmarks.trace import TraceSink
    from tank_backend.llm.model_transport import ChatCompletionsRoute, TaskModelTransport

    trace = TraceSink(tmp_path)
    policy = BenchmarkTaskPolicy(trace, RequestBudget(RequestLimits(2, 0, 2)), None)
    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
        model_policy=policy, model_capture=policy,
    )
    body = json.dumps({
        "id": "reply", "model": "model", "object": "chat.completion", "created": 1,
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": "provider text credential-value end",
        }}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }).encode()
    split = body.index(b"credential-value") + 6

    class Wire(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield body[:split]
            yield body[split:]

    transport = TaskModelTransport("task", context, routes=(ChatCompletionsRoute(
        "https://provider.test/v1/chat/completions", "model", "key",
    ),), credentials={"key": "credential-value"}, inner=httpx.MockTransport(
        lambda request: httpx.Response(200, stream=Wire()),
    ))
    async with AsyncOpenAI(api_key="unused", base_url="https://provider.test/v1", max_retries=0,
                           http_client=httpx.AsyncClient(transport=transport)) as client:
        result = await client.chat.completions.create(
            model="model", messages=[{"role": "user", "content": "go"}], max_tokens=20,
        )
    trace.close()
    events = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]
    request = next(event for event in events if event["kind"] == "http_request")
    response = next(event for event in events if event["kind"] == "http_response")
    assert request["request_id"] == response["request_id"]
    assert request["request_id"] in context.budget.call_ids
    archived = (tmp_path / response["file"]).read_bytes()
    assert b"credential-value" not in archived and b"[REDACTED]" in archived
    assert response["credentials_redacted"] is True
    assert result.choices[0].message.content == "provider text credential-value end"
