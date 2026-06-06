"""Unit tests for the worker pause-and-ask flow."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from tank_backend.agents.ask_user_tool import AskUserTool
from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.notification_hub import (
    NotificationHub,
    NotificationHubConfig,
)
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.supervisor import WorkerSupervisor
from tank_backend.agents.worker_tools import AgentReplyTool
from tank_backend.pipeline.bus import Bus, BusMessage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus():
    return Bus()


@pytest.fixture
def db(tmp_path):
    from tank_backend.persistence import Base, Database

    database = Database(url=f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(database.engine)
    yield database
    database.dispose()


@pytest.fixture
def store(db):
    return WorkerStore(db)


@pytest.fixture
def mock_runner():
    runner = MagicMock()
    runner.get_definition = MagicMock(return_value=MagicMock(name="coder"))
    return runner


@pytest.fixture
def supervisor(mock_runner, store, bus):
    return WorkerSupervisor(
        runner=mock_runner, store=store, bus=bus,
        max_depth=3, max_concurrent=5,
    )


# ---------------------------------------------------------------------------
# AskUserTool tests
# ---------------------------------------------------------------------------


class TestAskUserTool:
    @pytest.mark.asyncio
    async def test_returns_sentinel_content(self):
        tool = AskUserTool()
        result = await tool.execute(question="Which option?", options="A, B, C")
        assert "Which option?" in result.content
        assert "A, B, C" in result.content
        assert "Which option?" in result.display
        assert "A, B, C" in result.display

    @pytest.mark.asyncio
    async def test_without_options(self):
        tool = AskUserTool()
        result = await tool.execute(question="What city?")
        assert result.content == "What city?"
        assert result.display == "What city?"

    def test_tool_info(self):
        tool = AskUserTool()
        info = tool.get_info()
        assert info.name == "ask_user"
        assert any(p.name == "question" for p in info.parameters)


# ---------------------------------------------------------------------------
# WorkerStore pause/resume tests
# ---------------------------------------------------------------------------


class TestWorkerStorePauseResume:
    def test_pause_transitions_running_to_waiting(self, store):
        store.create(
            task_id="t_1", agent_def="coder", prompt="do stuff",
        )
        assert store.pause("t_1", output="partial", question="which?")
        run = store.get("t_1")
        assert run is not None
        assert run.status == "waiting"
        assert run.output == "partial"
        assert run.question == "which?"

    def test_pause_fails_if_not_running(self, store):
        store.create(task_id="t_1", agent_def="coder", prompt="x")
        store.finish("t_1", status="completed", output="done")
        assert not store.pause("t_1", question="too late")

    def test_pause_persists_messages(self, store):
        store.create(task_id="t_1", agent_def="coder", prompt="x")
        msgs = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
        store.pause("t_1", messages=msgs, question="q")
        run = store.get("t_1")
        assert run is not None
        assert run.messages == msgs

    def test_resume_transitions_waiting_to_running(self, store):
        store.create(task_id="t_1", agent_def="coder", prompt="x")
        store.pause("t_1", question="q")
        assert store.resume("t_1")
        run = store.get("t_1")
        assert run is not None
        assert run.status == "running"
        assert run.question == ""

    def test_resume_fails_if_not_waiting(self, store):
        store.create(task_id="t_1", agent_def="coder", prompt="x")
        assert not store.resume("t_1")  # still running, not waiting

    def test_resume_nonexistent_returns_false(self, store):
        assert not store.resume("nope")

    def test_pause_nonexistent_returns_false(self, store):
        assert not store.pause("nope", question="q")


# ---------------------------------------------------------------------------
# Supervisor ask_user detection + _drive_to_completion tests
# ---------------------------------------------------------------------------


class TestSupervisorAskUser:
    @pytest.mark.asyncio
    async def test_ask_user_signal_transitions_to_waiting(self, store, bus):
        """When _consume_stream detects ask_user, supervisor pauses the worker."""
        runner = MagicMock()

        async def fake_run_agent(**kwargs):
            yield AgentOutput(type=AgentOutputType.TOKEN, content="partial output")
            yield AgentOutput(
                type=AgentOutputType.TOOL_RESULT,
                content="Which city do you prefer?",
                metadata={"name": "ask_user", "status": "success"},
            )
            yield AgentOutput(
                type=AgentOutputType.DONE,
                metadata={"turn_messages": [
                    {"role": "assistant", "content": None, "tool_calls": [
                        {
                            "id": "tc_1",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": '{"question":"Which city?"}',
                            },
                        },
                    ]},
                    {
                        "role": "tool",
                        "tool_call_id": "tc_1",
                        "name": "ask_user",
                        "content": "Which city?",
                    },
                ]},
            )

        runner.run_agent = fake_run_agent
        runner.get_definition = MagicMock(return_value=MagicMock(name="coder"))

        supervisor = WorkerSupervisor(
            runner=runner, store=store, bus=bus,
            max_depth=3, max_concurrent=5,
        )

        # Create a run manually
        run = store.create(
            task_id="t_ask", agent_def="coder", prompt="research cities",
            originating_conversation_id="conv_1", background=True,
        )

        from tank_backend.agents.definition import AgentDefinition

        agent_def = AgentDefinition(name="coder", description="", system_prompt="")

        result = await supervisor._drive_to_completion(
            run=run, agent_def=agent_def, timeout=None,
        )

        assert result.status == "waiting"
        assert result.output == "partial output"

        # Verify store state
        stored = store.get("t_ask")
        assert stored is not None
        assert stored.status == "waiting"
        assert stored.question == "Which city do you prefer?"
        assert len(stored.messages) > 0

    @pytest.mark.asyncio
    async def test_resume_with_answer(self, store, bus):
        """resume_with_answer transitions waiting → running and re-dispatches."""
        runner = MagicMock()
        call_count = {"n": 0}

        async def fake_run_agent(**kwargs):
            call_count["n"] += 1
            yield AgentOutput(type=AgentOutputType.TOKEN, content="final answer")
            yield AgentOutput(type=AgentOutputType.DONE, metadata={"turn_messages": []})

        runner.run_agent = fake_run_agent
        runner.get_definition = MagicMock(return_value=MagicMock(name="coder"))

        from tank_backend.agents.definition import AgentDefinition

        runner.get_definition.return_value = AgentDefinition(
            name="coder", description="", system_prompt="",
        )

        supervisor = WorkerSupervisor(
            runner=runner, store=store, bus=bus,
            max_depth=3, max_concurrent=5,
        )

        # Set up a waiting worker
        store.create(task_id="t_wait", agent_def="coder", prompt="research")
        store.pause(
            "t_wait",
            output="partial",
            question="which city?",
            messages=[
                {"role": "user", "content": "research"},
                {"role": "assistant", "content": None, "tool_calls": []},
                {"role": "tool", "content": "which city?"},
            ],
        )

        result = await supervisor.resume_with_answer("t_wait", "Paris")

        assert result is True

        # Wait for background task to complete
        await asyncio.sleep(0.1)

        stored = store.get("t_wait")
        assert stored is not None
        assert stored.status == "completed"


# ---------------------------------------------------------------------------
# NotificationHub question delivery tests
# ---------------------------------------------------------------------------


class TestNotificationHubQuestion:
    def test_waiting_event_creates_high_priority_notification(self, bus):
        config = NotificationHubConfig(proactive_delivery=False)
        hub = NotificationHub(bus, config=config)

        payload = {
            "event": "waiting",
            "task_id": "t_q",
            "agent_def": "researcher",
            "description": "trip research",
            "originating_conversation_id": "conv_1",
            "originating_channel": None,
            "parent_msg_id": None,
            "question": "Which destination?",
        }
        bus.post(BusMessage(type="worker", source="test", payload=payload))
        bus.poll()

        notifications = hub.drain("conv_1")
        assert len(notifications) == 1
        n = notifications[0]
        assert n.event_type == "question"
        assert n.priority == "high"
        assert "Which destination?" in n.summary
        assert n.metadata["task_id"] == "t_q"
        assert n.metadata["question"] == "Which destination?"

    def test_waiting_event_does_not_affect_cohort_tracking(self, bus):
        """A waiting event should not remove the worker from pending_workers."""
        config = NotificationHubConfig(proactive_delivery=False)
        hub = NotificationHub(bus, config=config)

        # Start a worker
        bus.post(BusMessage(
            type="worker", source="test",
            payload={
                "event": "started",
                "task_id": "t_1",
                "originating_conversation_id": "conv_1",
            },
        ))
        bus.poll()

        # Worker enters waiting
        bus.post(BusMessage(
            type="worker", source="test",
            payload={
                "event": "waiting",
                "task_id": "t_1",
                "agent_def": "coder",
                "description": "task",
                "originating_conversation_id": "conv_1",
                "question": "which?",
            },
        ))
        bus.poll()

        # Worker is still in pending_workers (it hasn't completed)
        assert "t_1" in hub._pending_workers.get("conv_1", set())


# ---------------------------------------------------------------------------
# AgentReplyTool tests
# ---------------------------------------------------------------------------


class TestAgentReplyTool:
    @pytest.mark.asyncio
    async def test_reply_to_waiting_worker(self, store, bus):
        runner = MagicMock()

        async def fake_run_agent(**kwargs):
            yield AgentOutput(type=AgentOutputType.TOKEN, content="done")
            yield AgentOutput(type=AgentOutputType.DONE, metadata={"turn_messages": []})

        runner.run_agent = fake_run_agent
        from tank_backend.agents.definition import AgentDefinition

        runner.get_definition = MagicMock(return_value=AgentDefinition(
            name="coder", description="", system_prompt="",
        ))

        supervisor = WorkerSupervisor(
            runner=runner, store=store, bus=bus,
            max_depth=3, max_concurrent=5,
        )

        # Create and pause a worker
        store.create(task_id="t_r", agent_def="coder", prompt="research")
        store.pause("t_r", question="which?", messages=[{"role": "user", "content": "research"}])

        tool = AgentReplyTool(store=store, supervisor=supervisor)
        result = await tool.execute(task_id="t_r", answer="option A")

        assert not result.error
        assert "running" in result.content

    @pytest.mark.asyncio
    async def test_reply_to_non_waiting_worker_errors(self, store, bus):
        runner = MagicMock()
        supervisor = WorkerSupervisor(
            runner=runner, store=store, bus=bus,
            max_depth=3, max_concurrent=5,
        )

        store.create(task_id="t_r2", agent_def="coder", prompt="x")

        tool = AgentReplyTool(store=store, supervisor=supervisor)
        result = await tool.execute(task_id="t_r2", answer="hello")

        assert result.error
        assert "running" in result.content  # tells user the status

    @pytest.mark.asyncio
    async def test_reply_to_nonexistent_task_errors(self, store, bus):
        runner = MagicMock()
        supervisor = WorkerSupervisor(
            runner=runner, store=store, bus=bus,
            max_depth=3, max_concurrent=5,
        )

        tool = AgentReplyTool(store=store, supervisor=supervisor)
        result = await tool.execute(task_id="nope", answer="hello")

        assert result.error
        assert "not found" in result.content
