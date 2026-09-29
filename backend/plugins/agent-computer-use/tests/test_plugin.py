"""Real registry/Runner/Supervisor/SQLite integration, with fake UI boundaries."""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from agent_computer_use import create_subagent
from agent_computer_use.agent import ComputerUseSubAgent

from tank_backend.agents.agent_tool import AgentTool
from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.resources import DesktopResource
from tank_backend.agents.runner import AgentRunner
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.supervisor import WorkerSupervisor
from tank_backend.config.app_config import AppConfig
from tank_backend.persistence import Base, Database
from tank_backend.pipeline.bus import Bus
from tank_backend.plugin.manifest import read_manifest_from_yaml
from tank_backend.plugin.registry import ExtensionRegistry

from .test_ladder import ExportWorld, export_goal


@pytest.mark.parametrize("started", [False, True])
async def test_plugin_close_only_releases_its_resources(started):
    from agent_computer_use.controller import ComputerUseController

    from tank_backend.agents.subagent import SubAgentRequest

    from .test_ladder import context

    world = ExportWorld()
    plugin = ComputerUseSubAgent(ComputerUseController(world, world), resources=(world,))
    ctx = context()
    request = SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json"))
    if started:
        outputs = [output async for output in plugin.run(request, ctx)]
        assert outputs[-1].metadata["task_result"]["status"] == "completed"
    await plugin.aclose()
    await plugin.aclose()
    assert world.closed
    # The caller still owns the task runtime; plugin cleanup cannot close it.
    ctx.check("desktop")
    await ctx.runtime.aclose()


async def test_closed_unstarted_plugin_cannot_execute():
    from agent_computer_use.controller import ComputerUseController

    from tank_backend.agents.subagent import SubAgentRequest

    from .test_ladder import context

    world = ExportWorld()
    plugin = ComputerUseSubAgent(ComputerUseController(world, world), resources=(world,))
    await plugin.aclose()
    with pytest.raises(RuntimeError, match="closed"):
        async for _ in plugin.run(
            SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")),
            context(),
        ):
            pass
    assert world.observations == 0 and not world.dispatched


@pytest.mark.parametrize(
    "outcome", ["completed", "unknown", "stopped", "cleanup_failure", "cancel"]
)
async def test_plugin_through_worker_dispatch(tmp_path, monkeypatch, outcome):
    import agent_computer_use
    from agent_computer_use.contracts import DispatchReceipt
    from agent_computer_use.controller import ComputerUseController

    class World(ExportWorld):
        async def dispatch(self, binding, action, ctx):
            if outcome == "stopped":
                return DispatchReceipt(action.id, "not_sent")
            self.dispatched.append(action)
            if outcome == "cancel":
                raise asyncio.CancelledError()
            return DispatchReceipt(action.id, "sent")

        async def observe(self, scope, ctx):
            from dataclasses import replace

            snapshot = await super().observe(scope, ctx)
            return replace(snapshot, facts=()) if outcome == "unknown" else snapshot

        async def aclose(self):
            self.closed = True
            if outcome == "cleanup_failure":
                raise RuntimeError("release not confirmed")

    world = World()
    plugin = ComputerUseSubAgent(ComputerUseController(world, world), resources=(world,))
    monkeypatch.setattr(agent_computer_use, "create_subagent", lambda config: plugin)
    manifest = read_manifest_from_yaml(Path(__file__).parents[1] / "plugin.yaml")
    registry = ExtensionRegistry()
    registry.register(manifest.plugin_name, manifest.extensions[0])
    definition = AgentDefinition(
        "ladder", "test", "Never overwrite", extension="agent-computer-use:agent"
    )
    runner = AgentRunner(
        MagicMock(),
        MagicMock(),
        Bus(),
        ToolApprovalPolicy(computer_mode="allow"),
        PendingToolCallStore(),
        {"ladder": definition},
        registry=registry,
        app_config=AppConfig(),
        desktop_resource=DesktopResource(),
    )
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tasks.db")
    Base.metadata.create_all(db.engine)
    store = WorkerStore(db)
    try:
        tool = AgentTool(runner, supervisor=WorkerSupervisor(runner, store))
        dispatched = await tool.execute(
            prompt="Export PDF",
            subagent_type="ladder",
            task_input=export_goal().model_dump(mode="json"),
        )
        assert "APPROVAL REQUIRED" in dispatched.content
        assert not world.dispatched
        pending = runner._pending_store.get_oldest_pending()
        assert pending is not None and pending.on_confirmation is not None
        pending.on_confirmation(True)
        if outcome == "cancel":
            from tank_backend.agents.subagent import SubAgentCancelled

            with pytest.raises(SubAgentCancelled) as stopped:
                await tool.execute(**pending.tool_args)
            result = stopped.value.task_result
            assert result is not None and result.status == "unknown"
            assert result.cleanup == "confirmed" and result.details["receipts"]
            assert world.closed
            return
        dispatched = await tool.execute(**pending.tool_args)
        assert isinstance(dispatched.content, str)
        data = json.loads(dispatched.content)
        expected = "unknown" if outcome in {"cleanup_failure", "cancel"} else outcome
        assert data["task_result"]["status"] == expected
        assert world.closed
        persisted = store.get(data["task_id"])
        assert persisted is not None and persisted.task_result is not None
        assert persisted.task_result["status"] == expected
        assert data["task_result"]["details"]["receipts"]
    finally:
        db.dispose()


async def test_factory_is_explicitly_unavailable_without_channels():
    from tank_backend.agents.subagent import SubAgentRequest

    from .test_ladder import context

    plugin = create_subagent({})
    outputs = [
        item
        async for item in plugin.run(
            SubAgentRequest("Export", "", "task", export_goal().model_dump(mode="json")),
            context(),
        )
    ]
    assert outputs[-1].metadata["task_result"]["reason"] == "observation_unavailable"
    await plugin.aclose()


@pytest.mark.parametrize("config", [{"provider": "live"}, {"enabled": True}, {"max_steps": -1}])
def test_factory_rejects_unimplemented_configuration(config):
    with pytest.raises(ValueError):
        create_subagent(config)
