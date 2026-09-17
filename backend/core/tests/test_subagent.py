"""Exercise the generic plugin seam through Supervisor and Runner."""

import asyncio
import json
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from tank_backend.agents.agent_tool import AgentTool
from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.definition import AgentDefinition, parse_agent_file
from tank_backend.agents.resources import DesktopResource
from tank_backend.agents.runner import AgentRunner
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.subagent import SubAgent, SubAgentBudget, SubAgentStopped
from tank_backend.agents.supervisor import WorkerSupervisor
from tank_backend.config.app_config import AppConfig, ConfigError
from tank_backend.persistence import Base, Database
from tank_backend.pipeline.bus import Bus
from tank_backend.plugin.manifest import ExtensionManifest
from tank_backend.plugin.registry import ExtensionRegistry


class FakeSubAgent(SubAgent):
    def __init__(self):
        self.reason = "final_answer"
        self.close_error = False
        self.closed = False
        self.request = self.context = None

    async def run(self, request, context):
        self.request, self.context = request, context
        context.check()
        context.budget.record("call1", 7, 3)
        yield AgentOutput(AgentOutputType.USAGE, metadata={"total_tokens": 10})
        yield AgentOutput(AgentOutputType.TOOL_EXECUTING, metadata={"name": "fake"})
        yield AgentOutput(AgentOutputType.TOKEN, "hello")
        if self.reason:
            yield AgentOutput(AgentOutputType.DONE, metadata={"stop_reason": self.reason})

    async def aclose(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("cleanup failed")


@pytest.fixture
def stack(tmp_path, monkeypatch):
    fake = FakeSubAgent()
    monkeypatch.setitem(sys.modules, "_subagent_test", SimpleNamespace(create=lambda cfg: fake))
    registry = ExtensionRegistry()
    registry.register("fake", ExtensionManifest("agent", "subagent", "_subagent_test:create"))
    definition = AgentDefinition("fake", "test", "context", extension="fake:agent")
    runner = AgentRunner(
        MagicMock(),
        MagicMock(),
        Bus(),
        ToolApprovalPolicy(),
        PendingToolCallStore(),
        {"fake": definition},
        registry=registry,
        app_config=AppConfig(),
        desktop_resource=DesktopResource(),
    )
    db = Database(f"sqlite+pysqlite:///{tmp_path}/db")
    Base.metadata.create_all(db.engine)
    store = WorkerStore(db)
    supervisor = WorkerSupervisor(runner, store)
    yield fake, runner, supervisor, definition, store
    db.dispose()


async def test_full_dispatch_and_shared_usage(stack):
    fake, runner, supervisor, definition, store = stack
    result = await AgentTool(runner, supervisor=supervisor).execute(
        prompt="task", subagent_type="fake"
    )
    assert isinstance(result.content, str)
    data = json.loads(result.content)
    assert data["status"] == "completed"
    assert fake.closed and fake.request.task == "task"
    assert fake.request.task_id == data["task_id"]
    assert fake.context.budget.total_tokens == 10
    assert store.get(data["task_id"]).output == "hello"


@pytest.mark.parametrize("reason", ["max_steps", "budget", "context_limit", "unknown", None])
async def test_only_explicit_final_answer_completes(stack, reason):
    fake, runner, supervisor, definition, store = stack
    fake.reason = reason
    result = await supervisor.run_foreground(agent_def=definition, prompt="task")
    assert result.status == "failed" and fake.closed


async def test_close_failure_fails_worker(stack):
    fake, runner, supervisor, definition, store = stack
    fake.close_error = True
    result = await supervisor.run_foreground(agent_def=definition, prompt="task")
    assert result.status == "failed" and "cleanup" in result.error


async def test_no_authorization_means_no_start(stack):
    fake, runner, supervisor, definition, store = stack
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake",
        ExtensionManifest(
            "agent", "subagent", "_subagent_test:create", permissions=("desktop", "shell")
        ),
    )
    result = await supervisor.run_foreground(agent_def=definition, prompt="task")
    assert result.status == "failed" and fake.request is None


def test_extension_engine_exclusive(tmp_path):
    path = tmp_path / "agent.md"
    path.write_text("---\nname: test\nengine: old:agent\nextension: new:agent\n---\nprompt")
    with pytest.raises(ValueError, match="engine.*extension|extension.*engine"):
        parse_agent_file(path)
    with pytest.raises(ValueError):
        AgentDefinition("x", "", "", engine="x:y", extension="x:z")


@pytest.mark.parametrize(
    "raw", [[], {"x": []}, {"x": {"config": []}}, {"x": {"config": {}, "permissions": []}}]
)
def test_malformed_subagent_config_rejected(raw):
    with pytest.raises(ConfigError, match="subagents"):
        AppConfig.from_raw_dict(
            {
                "llm": {
                    "default": {"api_key": "x", "model": "x", "base_url": "https://example.com"}
                },
                "subagents": raw,
            }
        )


def test_budget_unique_calls_and_unknown():
    budget = SubAgentBudget(limit=10)
    budget.record("x", 7, 3)
    budget.record("x", 7, 3)
    assert budget.total_tokens == 10
    with pytest.raises(SubAgentStopped, match="budget"):
        budget.check()
    budget.record_unknown("lost")
    assert budget.unknown_calls == {"lost"}


async def test_desktop_quarantine_and_cancellable_wait():
    resource = DesktopResource()
    async with resource.acquire():
        task = asyncio.create_task(resource.lock.acquire())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    resource.quarantine("cleanup unknown")
    with pytest.raises(RuntimeError, match="quarantined"):
        async with resource.acquire():
            pass
    resource.clear_quarantine()
    async with resource.acquire():
        pass


async def test_permissions_approval_is_explicit_and_bound(stack):
    fake, runner, supervisor, definition, store = stack
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake",
        ExtensionManifest(
            "agent",
            "subagent",
            "_subagent_test:create",
            permissions=("desktop", "shell", "filesystem", "network"),
        ),
    )
    tool = AgentTool(runner, supervisor=supervisor)
    parked = await tool.execute(prompt="task", subagent_type="fake")
    assert "APPROVAL REQUIRED" in parked.content and fake.request is None
    pending = runner._pending_store.get_oldest_pending()
    assert "filesystem" in pending.description and "shell" in pending.description
    # A grant for one task cannot authorize a different prompt.
    stolen: dict[str, Any] = dict(pending.tool_args, prompt="different")
    again = await tool.execute(**stolen)
    assert "APPROVAL REQUIRED" in again.content and fake.request is None
    pending2 = runner._pending_store.list_pending()[-1]
    assert pending2.on_confirmation is not None
    pending2.on_confirmation(True)
    approved = await tool.execute(**pending2.tool_args)
    assert isinstance(approved.content, str)
    assert json.loads(approved.content)["status"] == "completed"
    assert fake.context.authorization.permissions == frozenset(
        {"desktop", "shell", "filesystem", "network"}
    )


async def test_cleanup_failure_quarantines_desktop(stack):
    from tank_backend.agents.subagent import SubAgentAuthorization

    fake, runner, supervisor, definition, store = stack
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake",
        ExtensionManifest("agent", "subagent", "_subagent_test:create", permissions=("desktop",)),
    )
    fake.close_error = True
    auth = SubAgentAuthorization(frozenset({"desktop"}))
    first = await supervisor.run_foreground(agent_def=definition, prompt="task", authorization=auth)
    assert first.status == "failed"
    second = await supervisor.run_foreground(
        agent_def=definition, prompt="task", authorization=auth
    )
    assert second.status == "failed" and "quarantined" in second.error


async def test_lock_wait_counts_toward_timeout(stack):
    from tank_backend.agents.subagent import SubAgentAuthorization

    fake, runner, supervisor, definition, store = stack
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake",
        ExtensionManifest("agent", "subagent", "_subagent_test:create", permissions=("desktop",)),
    )
    async with runner._desktop_resource.acquire():
        result = await supervisor.run_foreground(
            agent_def=definition,
            prompt="task",
            timeout=0.01,
            authorization=SubAgentAuthorization(frozenset({"desktop"})),
        )
        assert result.status == "timeout" and fake.request is None


def test_wrong_factory_type_and_ambiguous_registration(monkeypatch):
    monkeypatch.setitem(sys.modules, "_bad_subagent", SimpleNamespace(create=lambda cfg: object()))
    registry = ExtensionRegistry()
    registry.register("bad", ExtensionManifest("agent", "subagent", "_bad_subagent:create"))
    with pytest.raises(TypeError, match="SubAgent"):
        registry.instantiate("bad:agent", {})
    with pytest.raises(ValueError, match="duplicate"):
        registry.register("bad", ExtensionManifest("agent", "subagent", "other:create"))


async def test_builtin_engine_and_extension_share_desktop_lock(stack, monkeypatch):
    from tank_backend.agents.base import Agent
    from tank_backend.agents.subagent import SubAgentAuthorization

    fake, runner, supervisor, definition, store = stack
    runner._approval_policy = ToolApprovalPolicy(
        tool_metadata={"screenshot": SimpleNamespace(category="computer")}
    )
    active = peak = 0

    async def occupy():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1

    class WaitingAgent(Agent):
        async def run(self, state):
            await occupy()
            yield AgentOutput(AgentOutputType.DONE)

    class WaitingSubAgent(FakeSubAgent):
        async def run(self, request, context):
            await occupy()
            yield AgentOutput(AgentOutputType.DONE, metadata={"stop_reason": "final_answer"})

    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: WaitingSubAgent())
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake",
        ExtensionManifest("agent", "subagent", "_subagent_test:create", permissions=("desktop",)),
    )
    runner._registry.register(
        "old", ExtensionManifest("agent", "agent", "unused:create", needs=("desktop_executor",))
    )
    monkeypatch.setattr(runner, "_create_engine_agent", lambda *args: WaitingAgent("old"))
    monkeypatch.setattr(
        "tank_backend.agents.runner.LLMAgent", lambda **kwargs: WaitingAgent("builtin")
    )
    definitions = [
        definition,
        AgentDefinition("n2", "", "", engine="old:agent"),
        AgentDefinition("computer_use", "", "", tool_filter=("screenshot",)),
    ]

    async def run(definition):
        return [
            o
            async for o in runner.run_agent(
                definition,
                [{"role": "user", "content": "task"}],
                authorization=SubAgentAuthorization(frozenset({"desktop"})),
            )
        ]

    await asyncio.gather(*(run(d) for d in definitions))
    assert peak == 1 and active == 0


async def test_parked_dispatch_token_cannot_run_before_confirmation(stack):
    fake, runner, supervisor, definition, store = stack
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake",
        ExtensionManifest("agent", "subagent", "_subagent_test:create", permissions=("desktop",)),
    )
    tool = AgentTool(runner, supervisor=supervisor)
    await tool.execute(prompt="task", subagent_type="fake")
    pending = runner._pending_store.get_oldest_pending()
    result = await tool.execute(**pending.tool_args)
    assert "APPROVAL REQUIRED" in str(result.content) and fake.request is None


async def test_rejected_token_and_changed_permission_scope_require_new_approval(stack):
    fake, runner, supervisor, definition, store = stack
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake",
        ExtensionManifest("agent", "subagent", "_subagent_test:create", permissions=("desktop",)),
    )
    tool = AgentTool(runner, supervisor=supervisor)
    await tool.execute(prompt="task", subagent_type="fake")
    first = runner._pending_store.get_oldest_pending()
    assert first.on_confirmation is not None
    first.on_confirmation(False)
    rejected = await tool.execute(**first.tool_args)
    assert "APPROVAL REQUIRED" in str(rejected.content) and fake.request is None
    second = runner._pending_store.list_pending()[-1]
    assert second.on_confirmation is not None
    second.on_confirmation(True)
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake",
        ExtensionManifest(
            "agent", "subagent", "_subagent_test:create", permissions=("desktop", "shell")
        ),
    )
    wider = await tool.execute(**second.tool_args)
    assert "APPROVAL REQUIRED" in str(wider.content) and fake.request is None
