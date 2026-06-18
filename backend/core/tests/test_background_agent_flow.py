"""End-to-end integration test for the background-agent flow.

Phase 2 wrap-up. Unit tests cover each component in isolation; this
test pins the full wire:

    AgentTool.execute(run_in_background=True)
        → WorkerSupervisor.run_background
        → BusMessage(type="worker", event="completed")
        → WorkerInboxObserver
        → inbox.drain returns the completion

The bus dispatch is poll-based, so this test patches ``Bus.post`` to
dispatch synchronously — the same harness we use in
``test_agent_tool_supervisor.py``. Real production flow uses the bus
poller running on the asyncio loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

import pytest

from tank_backend.agents.agent_tool import AgentTool
from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.supervisor import WorkerSupervisor
from tank_backend.agents.worker_inbox import WorkerInboxObserver
from tank_backend.persistence import Base, Database
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.tools.base import ToolContext


class FakeRunner:
    def __init__(
        self,
        *,
        events_factory: Callable[[], AsyncIterator[AgentOutput]] | None = None,
    ) -> None:
        self.definitions = {
            "coder": AgentDefinition(
                name="coder", description="d", system_prompt="s",
            ),
        }
        self._events_factory = events_factory

    def get_definition(self, name: str) -> AgentDefinition | None:
        return self.definitions.get(name)

    async def run_agent(
        self, *, agent_def, messages, parent_agent_id=None,
        background: bool = False, token_budget=None,
    ):
        if self._events_factory is not None:
            async for ev in self._events_factory():
                yield ev
            return
        yield AgentOutput(type=AgentOutputType.TOKEN, content="research summary")


@pytest.fixture()
def store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    yield WorkerStore(db)
    db.dispose()


@pytest.fixture()
def eager_bus():
    """A Bus that dispatches subscribers synchronously on ``post``.

    Production uses a poller; tests want the result of ``post`` to be
    visible to subscribers before the next line runs.
    """
    bus = Bus()
    original_post = bus.post

    def post_and_dispatch(msg: BusMessage) -> None:
        original_post(msg)
        bus.poll()

    bus.post = post_and_dispatch  # type: ignore[method-assign]
    return bus


class TestBackgroundAgentFlow:
    @pytest.mark.asyncio
    async def test_completion_lands_in_inbox_for_originating_conversation(
        self, store: WorkerStore, eager_bus: Bus,
    ):
        runner = FakeRunner()
        supervisor = WorkerSupervisor(
            runner=runner,  # type: ignore[arg-type]
            store=store,
            bus=eager_bus,
        )
        inbox = WorkerInboxObserver(eager_bus)
        tool = AgentTool(runner, supervisor=supervisor)  # type: ignore[arg-type]

        ctx = ToolContext(media_store=None, session_id="conv_user_a")
        dispatch = await tool.execute(
            prompt="research trip options",
            subagent_type="coder",
            description="trip research",
            run_in_background=True,
            ctx=ctx,
        )

        import json
        dispatch_data = json.loads(dispatch.content)

        assert dispatch_data["status"] == "running"
        task_id = dispatch_data["task_id"]
        assert task_id.startswith("t_")

        # Wait for the worker to complete; the supervisor will post
        # ``worker.completed`` to the bus, which the inbox subscribes to.
        await supervisor.wait(task_id, timeout=1.0)

        pending = inbox.drain("conv_user_a")
        assert len(pending) == 1
        completion = pending[0]
        assert completion.task_id == task_id
        assert completion.agent_def == "coder"
        assert completion.description == "trip research"
        assert completion.status == "completed"
        assert completion.output == "research summary"

        rendered = completion.to_system_message()
        assert "trip research" in rendered
        assert "research summary" in rendered

    @pytest.mark.asyncio
    async def test_failure_surfaces_to_inbox_with_error(
        self, store: WorkerStore, eager_bus: Bus,
    ):
        async def boom():
            yield AgentOutput(type=AgentOutputType.TOKEN, content="started... ")
            raise RuntimeError("kaboom")

        runner = FakeRunner(events_factory=boom)
        supervisor = WorkerSupervisor(
            runner=runner,  # type: ignore[arg-type]
            store=store,
            bus=eager_bus,
        )
        inbox = WorkerInboxObserver(eager_bus)
        tool = AgentTool(runner, supervisor=supervisor)  # type: ignore[arg-type]

        ctx = ToolContext(media_store=None, session_id="conv_b")
        dispatch = await tool.execute(
            prompt="x", subagent_type="coder",
            description="probe", run_in_background=True, ctx=ctx,
        )
        import json
        dispatch_data = json.loads(dispatch.content)
        await supervisor.wait(dispatch_data["task_id"], timeout=1.0)

        pending = inbox.drain("conv_b")
        assert len(pending) == 1
        completion = pending[0]
        assert completion.status == "failed"
        assert "kaboom" in (completion.error or "")
        # Partial output is preserved.
        assert "started" in completion.output

    @pytest.mark.asyncio
    async def test_cancellation_surfaces_to_inbox(
        self, store: WorkerStore, eager_bus: Bus,
    ):
        running = asyncio.Event()
        gate = asyncio.Event()

        async def block():
            running.set()
            await gate.wait()
            yield AgentOutput(type=AgentOutputType.TOKEN, content="never")

        runner = FakeRunner(events_factory=block)
        supervisor = WorkerSupervisor(
            runner=runner,  # type: ignore[arg-type]
            store=store,
            bus=eager_bus,
        )
        inbox = WorkerInboxObserver(eager_bus)
        tool = AgentTool(runner, supervisor=supervisor)  # type: ignore[arg-type]

        ctx = ToolContext(media_store=None, session_id="conv_c")
        dispatch = await tool.execute(
            prompt="x", subagent_type="coder",
            run_in_background=True, ctx=ctx,
        )
        import json
        dispatch_data = json.loads(dispatch.content)
        task_id = dispatch_data["task_id"]
        await running.wait()

        assert supervisor.stop(task_id) is True
        await supervisor.wait(task_id, timeout=1.0)

        pending = inbox.drain("conv_c")
        assert len(pending) == 1
        assert pending[0].status == "cancelled"
