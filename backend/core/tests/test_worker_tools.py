"""Tests for the worker control tools (status / stop / list).

Phase 2 step 4 of the workflow & orchestration roadmap. These tools
are companions to ``agent`` — they let the LLM introspect and manage
in-flight workers without leaving the tool surface. The tests pin
the JSON shape returned to the LLM so prompt engineering can rely on
stable keys.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import pytest

from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.supervisor import WorkerSupervisor
from tank_backend.agents.worker_tools import (
    AgentStatusTool,
    AgentStopTool,
    ListActiveAgentsTool,
)
from tank_backend.persistence import Base, Database
from tank_backend.tools.base import ToolResult


def _decode(result: ToolResult) -> dict:
    """Tools always set ``content`` as a JSON string here — narrow for pyright."""
    assert isinstance(result.content, str)
    return json.loads(result.content)


class FakeRunner:
    def __init__(
        self,
        *,
        events_factory: Callable[[], AsyncIterator[AgentOutput]] | None = None,
    ) -> None:
        self.definitions = {
            "coder": AgentDefinition(
                name="coder", description="d", system_prompt="s", max_turns=5,
            ),
        }
        self._events_factory = events_factory

    def get_definition(self, name: str) -> AgentDefinition | None:
        return self.definitions.get(name)

    async def run_agent(
        self, *, agent_def, messages, parent_agent_id=None,
        background: bool = False, max_turns=None,
    ):
        if self._events_factory is not None:
            async for ev in self._events_factory():
                yield ev
            return
        yield AgentOutput(type=AgentOutputType.TOKEN, content="done")


@pytest.fixture()
def store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    yield WorkerStore(db)
    db.dispose()


def _make_supervisor(runner: FakeRunner, store: WorkerStore) -> WorkerSupervisor:
    return WorkerSupervisor(
        runner=runner,  # type: ignore[arg-type]
        store=store,
    )


class TestAgentStatusTool:
    @pytest.mark.asyncio
    async def test_unknown_task_id_returns_error(self, store: WorkerStore):
        sup = _make_supervisor(FakeRunner(), store)
        tool = AgentStatusTool(store, sup)
        result = await tool.execute(task_id="t_missing")
        assert isinstance(result, ToolResult)
        assert result.error
        data = _decode(result)
        assert "not found" in data["error"]

    @pytest.mark.asyncio
    async def test_returns_run_shape_for_completed_run(
        self, store: WorkerStore,
    ):
        runner = FakeRunner()
        sup = _make_supervisor(runner, store)
        agent_def = runner.get_definition("coder")
        assert agent_def is not None
        task_id = sup.run_background(
            agent_def=agent_def, prompt="x", description="probe",
        )
        await sup.wait(task_id, timeout=1.0)

        tool = AgentStatusTool(store, sup)
        result = await tool.execute(task_id=task_id)

        assert isinstance(result, ToolResult)
        assert not result.error
        data = _decode(result)
        assert data["task_id"] == task_id
        assert data["status"] == "completed"
        assert data["agent_def"] == "coder"
        assert data["description"] == "probe"
        assert data["output"] == "done"

    @pytest.mark.asyncio
    async def test_wait_blocks_until_terminal(self, store: WorkerStore):
        gate = asyncio.Event()

        async def deferred():
            await gate.wait()
            yield AgentOutput(type=AgentOutputType.TOKEN, content="late")

        runner = FakeRunner(events_factory=deferred)
        sup = _make_supervisor(runner, store)
        agent_def = runner.get_definition("coder")
        assert agent_def is not None
        task_id = sup.run_background(agent_def=agent_def, prompt="x")

        tool = AgentStatusTool(store, sup)

        async def release_after_short_delay():
            await asyncio.sleep(0.05)
            gate.set()

        asyncio.create_task(release_after_short_delay())
        result = await tool.execute(task_id=task_id, wait=True, timeout_ms=2000)
        data = _decode(result)
        assert data["status"] == "completed"
        assert data["output"] == "late"


class TestAgentStopTool:
    @pytest.mark.asyncio
    async def test_unknown_task_id_returns_error(self, store: WorkerStore):
        sup = _make_supervisor(FakeRunner(), store)
        tool = AgentStopTool(store, sup)
        result = await tool.execute(task_id="t_missing")
        assert isinstance(result, ToolResult)
        assert result.error

    @pytest.mark.asyncio
    async def test_already_terminal_is_noop(self, store: WorkerStore):
        runner = FakeRunner()
        sup = _make_supervisor(runner, store)
        agent_def = runner.get_definition("coder")
        assert agent_def is not None
        task_id = sup.run_background(agent_def=agent_def, prompt="x")
        await sup.wait(task_id, timeout=1.0)

        tool = AgentStopTool(store, sup)
        result = await tool.execute(task_id=task_id)
        data = _decode(result)
        assert data["status"] == "completed"
        assert "already terminal" in data["note"]
        assert not result.error

    @pytest.mark.asyncio
    async def test_running_task_is_cancelled(self, store: WorkerStore):
        running = asyncio.Event()
        gate = asyncio.Event()

        async def blocking():
            running.set()
            await gate.wait()
            yield AgentOutput(type=AgentOutputType.TOKEN, content="never")

        runner = FakeRunner(events_factory=blocking)
        sup = _make_supervisor(runner, store)
        agent_def = runner.get_definition("coder")
        assert agent_def is not None
        task_id = sup.run_background(agent_def=agent_def, prompt="x")
        await running.wait()

        tool = AgentStopTool(store, sup)
        result = await tool.execute(task_id=task_id)
        data = _decode(result)
        assert data["status"] == "cancelling"

        await sup.wait(task_id, timeout=1.0)
        row = store.get(task_id)
        assert row is not None
        assert row.status == "cancelled"


class TestListActiveAgentsTool:
    @pytest.mark.asyncio
    async def test_empty_when_no_workers(self, store: WorkerStore):
        tool = ListActiveAgentsTool(store)
        result = await tool.execute()
        data = _decode(result)
        assert data == {"workers": []}

    @pytest.mark.asyncio
    async def test_returns_active_workers_only(self, store: WorkerStore):
        # Two terminal, one running.
        store.create(task_id="t_done", agent_def="x", prompt="...")
        store.finish("t_done", status="completed", output="x")
        store.create(task_id="t_fail", agent_def="x", prompt="...")
        store.finish("t_fail", status="failed", output="", error="boom")
        store.create(task_id="t_run", agent_def="x", prompt="...")

        tool = ListActiveAgentsTool(store)
        result = await tool.execute()
        data = _decode(result)
        ids = [w["task_id"] for w in data["workers"]]
        assert ids == ["t_run"]
        # Output is elided in list view.
        assert "output" not in data["workers"][0]
