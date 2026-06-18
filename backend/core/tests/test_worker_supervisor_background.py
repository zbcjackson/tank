"""Tests for the run_in_background path of AgentTool / WorkerSupervisor.

Phase 2 step 4 of the workflow & orchestration roadmap. The background
path returns ``task_id`` immediately while the worker continues
running on the event loop. Tests pin:

- foreground vs background return shape
- the supervisor tracks in-flight tasks, ``stop`` cancels them
- ``wait`` blocks until terminal state, returns the final row
- limits apply to background dispatch identically
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

import pytest

from tank_backend.agents.agent_tool import AgentTool
from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.supervisor import (
    ConcurrencyLimitExceeded,
    WorkerSupervisor,
)
from tank_backend.persistence import Base, Database


class FakeRunner:
    """Scriptable AgentRunner — yields a controlled output stream."""

    def __init__(
        self,
        definitions: dict[str, AgentDefinition] | None = None,
        *,
        events_factory: Callable[[], AsyncIterator[AgentOutput]] | None = None,
    ) -> None:
        self.definitions = definitions or {
            "coder": AgentDefinition(
                name="coder",
                description="execute code",
                system_prompt="be terse",
            ),
        }
        self._events_factory = events_factory

    def get_definition(self, name: str) -> AgentDefinition | None:
        return self.definitions.get(name)

    async def run_agent(
        self,
        *,
        agent_def: AgentDefinition,
        messages,
        parent_agent_id=None,
        background: bool = False,
        token_budget=None,
    ) -> AsyncIterator[AgentOutput]:
        if self._events_factory is not None:
            async for ev in self._events_factory():
                yield ev
            return
        yield AgentOutput(type=AgentOutputType.TOKEN, content="ok")


@pytest.fixture()
def store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    yield WorkerStore(db)
    db.dispose()


def _make_supervisor(
    runner: FakeRunner, store: WorkerStore, **kw,
) -> WorkerSupervisor:
    return WorkerSupervisor(
        runner=runner,  # type: ignore[arg-type]
        store=store,
        max_depth=kw.get("max_depth", 3),
        max_concurrent=kw.get("max_concurrent", 5),
    )


# ----------------------------------------------------------------------
# AgentTool background return shape
# ----------------------------------------------------------------------

class TestAgentToolBackground:
    @pytest.mark.asyncio
    async def test_returns_task_id_and_running_status_immediately(
        self, store: WorkerStore,
    ):
        # Block forever so we can prove the parent does not await.
        gate = asyncio.Event()

        async def block_forever():
            await gate.wait()
            yield AgentOutput(type=AgentOutputType.TOKEN, content="late")

        runner = FakeRunner(events_factory=block_forever)
        sup = _make_supervisor(runner, store)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]

        result = await tool.execute(
            prompt="x",
            subagent_type="coder",
            description="bg-task",
            run_in_background=True,
        )

        import json
        data = json.loads(result.content)
        assert data["status"] == "running"
        assert data["task_id"].startswith("t_")
        assert data["agent_type"] == "coder"
        assert data["description"] == "bg-task"
        # Worker row exists in store, still running.
        row = store.get(data["task_id"])
        assert row is not None
        assert row.status == "running"
        # Cleanup — let the worker finish so the test event loop
        # doesn't leak a pending task.
        gate.set()
        await sup.wait(data["task_id"], timeout=1.0)

    @pytest.mark.asyncio
    async def test_background_concurrency_limit_returns_graceful_message(
        self, store: WorkerStore,
    ):
        for i in range(3):
            store.create(task_id=f"existing_{i}", agent_def="x", prompt="...")
        runner = FakeRunner()
        sup = _make_supervisor(runner, store, max_concurrent=3)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]

        result = await tool.execute(
            prompt="x", subagent_type="coder", run_in_background=True,
        )
        import json
        data = json.loads(result.content)
        assert "error" in data
        assert "max concurrent" in data["error"]


# ----------------------------------------------------------------------
# WorkerSupervisor — background lifecycle
# ----------------------------------------------------------------------

class TestSupervisorBackgroundLifecycle:
    @pytest.mark.asyncio
    async def test_run_background_completes_and_persists(
        self, store: WorkerStore,
    ):
        runner = FakeRunner()
        sup = _make_supervisor(runner, store)
        agent_def = runner.get_definition("coder")
        assert agent_def is not None
        task_id = sup.run_background(agent_def=agent_def, prompt="x")
        assert task_id.startswith("t_")
        await sup.wait(task_id, timeout=1.0)
        row = store.get(task_id)
        assert row is not None
        assert row.status == "completed"
        assert row.output == "ok"

    @pytest.mark.asyncio
    async def test_stop_cancels_inflight_worker(self, store: WorkerStore):
        running = asyncio.Event()
        gate = asyncio.Event()

        async def blocking():
            running.set()
            await gate.wait()  # never set
            yield AgentOutput(type=AgentOutputType.TOKEN, content="never")

        runner = FakeRunner(events_factory=blocking)
        sup = _make_supervisor(runner, store)
        agent_def = runner.get_definition("coder")
        assert agent_def is not None
        task_id = sup.run_background(agent_def=agent_def, prompt="x")
        await running.wait()
        assert sup.stop(task_id) is True
        await sup.wait(task_id, timeout=1.0)
        row = store.get(task_id)
        assert row is not None
        assert row.status == "cancelled"

    @pytest.mark.asyncio
    async def test_stop_returns_false_for_unknown_or_finished(
        self, store: WorkerStore,
    ):
        runner = FakeRunner()
        sup = _make_supervisor(runner, store)
        # Unknown task.
        assert sup.stop("t_nope") is False
        # Already finished.
        agent_def = runner.get_definition("coder")
        assert agent_def is not None
        task_id = sup.run_background(agent_def=agent_def, prompt="x")
        await sup.wait(task_id, timeout=1.0)
        assert sup.stop(task_id) is False

    @pytest.mark.asyncio
    async def test_concurrency_limit_raises_synchronously_for_background(
        self, store: WorkerStore,
    ):
        for i in range(3):
            store.create(task_id=f"existing_{i}", agent_def="x", prompt="...")
        runner = FakeRunner()
        sup = _make_supervisor(runner, store, max_concurrent=3)
        agent_def = runner.get_definition("coder")
        assert agent_def is not None
        with pytest.raises(ConcurrencyLimitExceeded):
            sup.run_background(agent_def=agent_def, prompt="x")
