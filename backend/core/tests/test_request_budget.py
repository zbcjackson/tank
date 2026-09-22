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


@pytest.mark.parametrize("kind", ["engine", "extension"])
def test_request_limits_reject_uninstrumented_plugin_clients(monkeypatch, tmp_path, kind):
    from types import SimpleNamespace

    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.benchmarks import driver as module
    from tank_backend.benchmarks.request_budget import RequestLimits

    definition = (AgentDefinition("plugin", "", "", engine="test:agent") if kind == "engine"
                  else AgentDefinition("plugin", "", "", extension="test:agent"))
    config = SimpleNamespace(agents=SimpleNamespace(dirs=[]))
    monkeypatch.setattr(module.AppConfig, "load", lambda _: config)
    monkeypatch.setattr(module, "load_agent_definitions", lambda _: {"plugin": definition})
    with pytest.raises(ValueError, match="built-in benchmark transport"):
        module.SubAgentDriver.create("plugin", tmp_path / "config.yaml",
                                     request_limits=RequestLimits())
