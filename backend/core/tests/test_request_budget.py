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


async def test_task_policy_correlates_sdk_usage_and_redacts_known_credentials(tmp_path):
    import asyncio
    import json

    import httpx

    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.benchmarks.request_budget import RequestBudget, RequestLimits
    from tank_backend.benchmarks.task_model_policy import BenchmarkTaskPolicy
    from tank_backend.benchmarks.trace import TraceSink
    from tank_backend.llm.llm import LLM

    trace = TraceSink(tmp_path)
    policy = BenchmarkTaskPolicy(trace, RequestBudget(RequestLimits(2, 0, 2)), None,
                                 secrets=("credential-value",))
    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"network"})), SubAgentBudget(), asyncio.Event(),
        model_policy=policy, model_capture=policy,
    )
    from openai import AsyncOpenAI
    async def respond(request):
        return httpx.Response(200,json={"id":"r","object":"chat.completion","created":1,
            "model":"model","choices":[{"index":0,"finish_reason":"stop","message":{
                "role":"assistant","content":"provider text credential-value end"}}],
            "usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}})
    async with AsyncOpenAI(api_key="credential-value",base_url="https://provider.test/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond))) as client:
        llm=LLM(api_key="credential-value",model="model",base_url="https://provider.test/v1",client=client)
        bound=llm.bind_task(context,"task")
        result=await bound.complete_response([{"role":"user","content":"go"}])
        await context.runtime.aclose()
    trace.close()
    events=[json.loads(line) for line in (tmp_path/"trace.jsonl").read_text().splitlines()]
    request=next(e for e in events if e["kind"]=="model_request")
    response=next(e for e in events if e["kind"]=="model_response")
    assert request["request_id"]==response["request_id"]
    assert request["capture_level"] == response["capture_level"] == "model_call"
    assert request["request_id"] in context.budget.call_ids
    assert "credential-value" not in json.dumps(events)
    assert result.choices[0].message.content=="provider text credential-value end"
