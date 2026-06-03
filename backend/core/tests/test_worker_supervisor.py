"""Tests for ``WorkerSupervisor`` foreground path (Phase 2 Step 2).

The supervisor is exercised against a fake ``AgentRunner`` so no LLM
is required. The fake yields a configurable sequence of
``AgentOutput`` events; the supervisor's job is to map them onto the
``WorkerStore`` and bus correctly.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.supervisor import (
    ConcurrencyLimitExceeded,
    DepthLimitExceeded,
    WorkerSupervisor,
)
from tank_backend.persistence import Base, Database
from tank_backend.pipeline.bus import Bus, BusMessage

# ----------------------------------------------------------------------
# Fakes
# ----------------------------------------------------------------------

class FakeRunner:
    """Stub AgentRunner that yields a configurable script of outputs."""

    def __init__(
        self,
        *,
        outputs: list[AgentOutput] | None = None,
        events_factory: Callable[[], AsyncIterator[AgentOutput]] | None = None,
    ) -> None:
        self._outputs = outputs or []
        self._events_factory = events_factory
        self.calls: list[dict[str, Any]] = []

    async def run_agent(
        self,
        *,
        agent_def: AgentDefinition,
        messages: list[dict[str, Any]],
        parent_agent_id: str | None = None,
        background: bool = False,
        token_budget: int | None = None,
    ) -> AsyncIterator[AgentOutput]:
        self.calls.append({
            "agent_def": agent_def.name,
            "messages": list(messages),
            "parent_agent_id": parent_agent_id,
            "background": background,
        })
        if self._events_factory is not None:
            async for ev in self._events_factory():
                yield ev
            return
        for ev in self._outputs:
            yield ev


def _agent_def(name: str = "researcher") -> AgentDefinition:
    return AgentDefinition(
        name=name,
        description="test agent",
        system_prompt="be terse",
    )


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    yield WorkerStore(db)
    db.dispose()


class _BusHarness:
    """Helper that pairs a Bus with eager dispatch for tests.

    Tank's Bus is poll-based: subscribers only see messages after
    ``bus.poll()`` runs. Tests don't have a polling loop, so we wrap
    Bus.post and dispatch synchronously.
    """

    def __init__(self) -> None:
        self.bus = Bus()
        self.captured: list[BusMessage] = []
        self.bus.subscribe("worker", self.captured.append)
        # Patch post to also poll, so subscribers see events without
        # a manual poll() call.
        original_post = self.bus.post

        def post_and_dispatch(msg: BusMessage) -> None:
            original_post(msg)
            self.bus.poll()

        self.bus.post = post_and_dispatch  # type: ignore[method-assign]


@pytest.fixture()
def bus_harness():
    return _BusHarness()


@pytest.fixture()
def bus(bus_harness):
    return bus_harness.bus


@pytest.fixture()
def captured(bus_harness):
    return bus_harness.captured


def _make_supervisor(
    runner: FakeRunner,
    store: WorkerStore,
    bus: Bus | None = None,
    *,
    max_depth: int = 3,
    max_concurrent: int = 5,
) -> WorkerSupervisor:
    return WorkerSupervisor(
        runner=runner,  # type: ignore[arg-type]
        store=store,
        bus=bus,
        max_depth=max_depth,
        max_concurrent=max_concurrent,
    )


# ----------------------------------------------------------------------
# Happy path
# ----------------------------------------------------------------------

class TestForegroundHappyPath:
    @pytest.mark.asyncio
    async def test_run_returns_completed_with_accumulated_tokens(
        self, store, bus, captured,
    ):
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content="hel"),
            AgentOutput(type=AgentOutputType.TOKEN, content="lo "),
            AgentOutput(type=AgentOutputType.TOKEN, content="world"),
            AgentOutput(type=AgentOutputType.DONE),
        ])
        sup = _make_supervisor(runner, store, bus)

        result = await sup.run_foreground(
            agent_def=_agent_def(),
            prompt="say hello",
            description="say hi",
            originating_conversation_id="conv_1",
            originating_channel="voice:s1",
        )

        assert result.status == "completed"
        assert result.output == "hello world"
        assert result.error is None

        run = store.get(result.task_id)
        assert run is not None
        assert run.status == "completed"
        assert run.output == "hello world"
        assert run.completed_at is not None
        assert run.background is False
        assert run.originating_conversation_id == "conv_1"

        # Two bus events: started + completed.
        events = [m.payload["event"] for m in captured]
        assert events == ["started", "completed"]
        assert captured[1].payload["status"] == "completed"
        assert captured[1].payload["output"] == "hello world"

    @pytest.mark.asyncio
    async def test_non_token_outputs_are_ignored_for_output_text(self, store):
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.THOUGHT, content="thinking..."),
            AgentOutput(type=AgentOutputType.TOOL_CALLING, content="..."),
            AgentOutput(type=AgentOutputType.TOOL_RESULT, content="..."),
            AgentOutput(type=AgentOutputType.TOKEN, content="actual"),
            AgentOutput(type=AgentOutputType.DONE),
        ])
        sup = _make_supervisor(runner, store)
        result = await sup.run_foreground(
            agent_def=_agent_def(), prompt="x",
        )
        assert result.output == "actual"

    @pytest.mark.asyncio
    async def test_runner_receives_user_prompt_as_first_message(self, store):
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content="ok"),
        ])
        sup = _make_supervisor(runner, store)
        await sup.run_foreground(
            agent_def=_agent_def(), prompt="research X",
        )
        assert len(runner.calls) == 1
        msgs = runner.calls[0]["messages"]
        assert msgs == [{"role": "user", "content": "research X"}]


# ----------------------------------------------------------------------
# Failure modes
# ----------------------------------------------------------------------

class TestFailureMapping:
    @pytest.mark.asyncio
    async def test_runner_exception_maps_to_failed(self, store, bus, captured):
        async def boom():
            yield AgentOutput(type=AgentOutputType.TOKEN, content="partial")
            raise RuntimeError("kaboom")
        runner = FakeRunner(events_factory=boom)
        sup = _make_supervisor(runner, store, bus)

        result = await sup.run_foreground(
            agent_def=_agent_def(), prompt="x",
        )
        assert result.status == "failed"
        assert result.output == "partial"
        assert result.error is not None
        assert "kaboom" in result.error

        run = store.get(result.task_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error is not None and "kaboom" in run.error
        assert run.output == "partial"

        events = [m.payload["event"] for m in captured]
        assert events == ["started", "failed"]
        assert captured[1].payload["error"] == result.error

    @pytest.mark.asyncio
    async def test_timeout_maps_to_timeout_status(self, store):
        async def slow():
            await asyncio.sleep(10)
            yield AgentOutput(type=AgentOutputType.TOKEN, content="never")
        runner = FakeRunner(events_factory=slow)
        sup = _make_supervisor(runner, store)
        result = await sup.run_foreground(
            agent_def=_agent_def(), prompt="x", timeout=0.05,
        )
        assert result.status == "timeout"
        assert "timed out" in (result.error or "").lower()
        run = store.get(result.task_id)
        assert run is not None
        assert run.status == "timeout"

    @pytest.mark.asyncio
    async def test_cancellation_marks_row_then_propagates(self, store):
        # Outer task cancels the supervisor while the runner sleeps.
        runner_started = asyncio.Event()

        async def slow():
            runner_started.set()
            await asyncio.sleep(10)
            yield AgentOutput(type=AgentOutputType.TOKEN, content="never")

        runner = FakeRunner(events_factory=slow)
        sup = _make_supervisor(runner, store)

        async def run_it():
            return await sup.run_foreground(
                agent_def=_agent_def(),
                prompt="x",
                originating_conversation_id="conv_cancel",
            )

        task = asyncio.create_task(run_it())
        await runner_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # The supervisor wrote a finish() before re-raising; no row
        # remains in 'running' and the cancellation is recorded.
        assert store.count_active() == 0
        runs = store.list_for_conversation("conv_cancel")
        assert len(runs) == 1
        assert runs[0].status == "cancelled"
        assert runs[0].error is not None
        assert "cancel" in runs[0].error.lower()


# ----------------------------------------------------------------------
# Limits
# ----------------------------------------------------------------------

class TestLimits:
    @pytest.mark.asyncio
    async def test_concurrency_limit_blocks_dispatch(self, store):
        # Pre-populate the store with N "running" rows.
        for i in range(3):
            store.create(
                task_id=f"existing_{i}",
                agent_def="other",
                prompt="...",
            )
        runner = FakeRunner(outputs=[AgentOutput(type=AgentOutputType.DONE)])
        sup = _make_supervisor(runner, store, max_concurrent=3)
        with pytest.raises(ConcurrencyLimitExceeded):
            await sup.run_foreground(
                agent_def=_agent_def(), prompt="x",
            )
        # Original 3 rows should be untouched; no new row was created.
        assert store.count_active() == 3

    @pytest.mark.asyncio
    async def test_depth_limit_blocks_dispatch(self, store):
        # Build a chain: t1 -> t2 -> t3 (depth 3).
        store.create(task_id="t1", agent_def="x", prompt="x")
        store.create(task_id="t2", agent_def="x", prompt="x", parent_task_id="t1")
        store.create(task_id="t3", agent_def="x", prompt="x", parent_task_id="t2")
        runner = FakeRunner(outputs=[AgentOutput(type=AgentOutputType.DONE)])
        sup = _make_supervisor(runner, store, max_depth=3)
        with pytest.raises(DepthLimitExceeded):
            await sup.run_foreground(
                agent_def=_agent_def(), prompt="deeper",
                parent_task_id="t3",
            )

    @pytest.mark.asyncio
    async def test_within_depth_succeeds(self, store):
        store.create(task_id="root", agent_def="x", prompt="x")
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content="ok"),
        ])
        sup = _make_supervisor(runner, store, max_depth=3)
        result = await sup.run_foreground(
            agent_def=_agent_def(), prompt="x", parent_task_id="root",
        )
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_unknown_parent_is_treated_as_leaf_one_level_deep(self, store):
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content="ok"),
        ])
        sup = _make_supervisor(runner, store, max_depth=3)
        result = await sup.run_foreground(
            agent_def=_agent_def(), prompt="x",
            parent_task_id="t_nonexistent",
        )
        assert result.status == "completed"


# ----------------------------------------------------------------------
# Bus payload shape
# ----------------------------------------------------------------------

class TestBusPayload:
    @pytest.mark.asyncio
    async def test_started_event_carries_routing_metadata(
        self, store, bus, captured,
    ):
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content="hi"),
        ])
        sup = _make_supervisor(runner, store, bus)
        await sup.run_foreground(
            agent_def=_agent_def("researcher"),
            prompt="x",
            description="research X",
            originating_conversation_id="conv_42",
            originating_channel="telegram:99",
        )
        started = captured[0].payload
        assert started["event"] == "started"
        assert started["task_id"].startswith("t_")
        assert started["agent_def"] == "researcher"
        assert started["description"] == "research X"
        assert started["originating_conversation_id"] == "conv_42"
        assert started["originating_channel"] == "telegram:99"

    @pytest.mark.asyncio
    async def test_long_output_is_truncated_in_bus_event(
        self, store, bus, captured,
    ):
        big = "x" * 5000
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content=big),
        ])
        sup = _make_supervisor(runner, store, bus)
        result = await sup.run_foreground(
            agent_def=_agent_def(), prompt="x",
        )
        completed_payload = captured[1].payload
        # Full text in store, truncated in bus payload.
        assert len(result.output) == 5000
        assert len(completed_payload["output"]) <= 4096 + 1  # … char
        assert completed_payload["output"].endswith("…")
