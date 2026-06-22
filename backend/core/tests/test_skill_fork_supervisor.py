"""Tests for skill fork mode routed through WorkerSupervisor.

Covers:
- Allowlist construction (baseline ∪ declared)
- Runner honoring inline tool_filter
- ctx → originating_conversation_id on worker row
- Status mapping (completed, waiting, failed)
- Fallback path (supervisor None)
- Manager wiring (supervisor reaches UseSkillTool)
- Integration: ask_user pause → resume_with_answer with dynamic skill def
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock

import pytest

from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.supervisor import WorkerSupervisor
from tank_backend.persistence import Base, Database
from tank_backend.pipeline.bus import Bus
from tank_backend.tools.base import ToolContext
from tank_backend.tools.skill_tools import (
    _SKILL_FORK_DISALLOWED,
    SKILL_FORK_BASELINE_TOOLS,
    UseSkillTool,
)

# ----------------------------------------------------------------------
# Fakes / helpers
# ----------------------------------------------------------------------


class FakeRunner:
    """Minimal AgentRunner stub for skill fork tests."""

    def __init__(
        self,
        *,
        outputs: list[AgentOutput] | None = None,
        events_factory: Any = None,
    ) -> None:
        self.definitions: dict[str, AgentDefinition] = {}
        self._outputs = outputs or [
            AgentOutput(type=AgentOutputType.TOKEN, content="skill output"),
        ]
        self._events_factory = events_factory
        self.last_agent_def: AgentDefinition | None = None

    def get_definition(self, name: str) -> AgentDefinition | None:
        return self.definitions.get(name)

    async def run_agent(
        self,
        *,
        agent_def: AgentDefinition,
        messages: list[dict[str, Any]],
        parent_agent_id: str | None = None,
        background: bool = False,
        token_budget: int | None = None,
    ) -> AsyncIterator[AgentOutput]:
        self.last_agent_def = agent_def
        if self._events_factory is not None:
            async for ev in self._events_factory():
                yield ev
            return
        for ev in self._outputs:
            yield ev


class FakeSkillManager:
    """Minimal SkillManager stub that returns a canned invoke result."""

    def __init__(self, invoke_result: dict[str, Any]) -> None:
        self._invoke_result = invoke_result

    async def invoke(self, name: str, args: str) -> dict[str, Any]:
        return self._invoke_result


@pytest.fixture()
def db(tmp_path):
    database = Database(url=f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(database.engine)
    yield database
    database.dispose()


@pytest.fixture()
def store(db):
    return WorkerStore(db)


@pytest.fixture()
def bus():
    return Bus()


def _make_supervisor(
    runner: FakeRunner,
    store: WorkerStore,
    *,
    bus: Bus | None = None,
) -> WorkerSupervisor:
    return WorkerSupervisor(
        runner=runner,  # type: ignore[arg-type]
        store=store,
        bus=bus,
        max_depth=3,
        max_concurrent=5,
    )


def _invoke_result(
    *,
    name: str = "test-skill",
    instructions: str = "Do the thing.",
    context: str = "fork",
    allowed_tools: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "skill_name": name,
        "instructions": instructions,
        "context": context,
        "allowed_tools": allowed_tools or [],
    }


# ----------------------------------------------------------------------
# Allowlist construction
# ----------------------------------------------------------------------


class TestAllowlistConstruction:
    @pytest.mark.asyncio
    async def test_baseline_tools_always_included(self, store, bus):
        """Forked skill with no allowed_tools gets baseline only."""
        runner = FakeRunner()
        sup = _make_supervisor(runner, store, bus=bus)
        mgr = FakeSkillManager(_invoke_result(allowed_tools=[]))
        tool = UseSkillTool(mgr, agent_runner=runner, supervisor=sup)

        await tool.execute(skill="test-skill")

        # The dynamic def should be registered in runner.definitions
        skill_def = runner.definitions.get("skill_test-skill")
        assert skill_def is not None
        assert skill_def.tool_filter is not None
        assert set(skill_def.tool_filter) == set(SKILL_FORK_BASELINE_TOOLS)

    @pytest.mark.asyncio
    async def test_skill_allowed_tools_merged_with_baseline(self, store, bus):
        """Skill-declared tools are merged with the baseline."""
        runner = FakeRunner()
        sup = _make_supervisor(runner, store, bus=bus)
        mgr = FakeSkillManager(
            _invoke_result(allowed_tools=["run_command", "persistent_shell"]),
        )
        tool = UseSkillTool(mgr, agent_runner=runner, supervisor=sup)

        await tool.execute(skill="test-skill")

        skill_def = runner.definitions.get("skill_test-skill")
        assert skill_def is not None
        expected = SKILL_FORK_BASELINE_TOOLS | {"run_command", "persistent_shell"}
        assert set(skill_def.tool_filter) == expected

    @pytest.mark.asyncio
    async def test_anti_recursion_in_disallowed(self, store, bus):
        """Anti-recursion tools are always in disallowed_tools."""
        runner = FakeRunner()
        sup = _make_supervisor(runner, store, bus=bus)
        mgr = FakeSkillManager(_invoke_result())
        tool = UseSkillTool(mgr, agent_runner=runner, supervisor=sup)

        await tool.execute(skill="test-skill")

        skill_def = runner.definitions["skill_test-skill"]
        assert skill_def.disallowed_tools == _SKILL_FORK_DISALLOWED


# ----------------------------------------------------------------------
# Runner honors inline tool_filter
# ----------------------------------------------------------------------


class TestRunnerInlineToolFilter:
    @pytest.mark.asyncio
    async def test_tool_filter_passed_to_llm_agent(self):
        """AgentRunner.run_agent() uses agent_def.tool_filter as allowlist."""
        # We can't easily instantiate a full AgentRunner, so verify the
        # definition field propagation by checking the fallback path which
        # exercises the same definition.
        runner = FakeRunner()
        mgr = FakeSkillManager(_invoke_result(allowed_tools=["run_command"]))
        tool = UseSkillTool(mgr, agent_runner=runner)

        await tool.execute(skill="test-skill")

        # In fallback mode, runner.run_agent is called with the def
        assert runner.last_agent_def is not None
        assert runner.last_agent_def.tool_filter is not None
        assert "run_command" in runner.last_agent_def.tool_filter
        assert "file_read" in runner.last_agent_def.tool_filter  # baseline

    @pytest.mark.asyncio
    async def test_toolset_fallback_when_no_tool_filter(self):
        """When tool_filter is None, runner falls back to named toolset."""
        defn = AgentDefinition(
            name="test", description="", system_prompt="",
            toolset="research",
        )
        assert defn.tool_filter is None
        assert defn.toolset == "research"


# ----------------------------------------------------------------------
# ctx → originating_conversation_id on worker row
# ----------------------------------------------------------------------


class TestCtxFlowsToWorkerRow:
    @pytest.mark.asyncio
    async def test_session_id_from_ctx_lands_on_worker_row(self, store, bus):
        """ctx.session_id becomes originating_conversation_id on the row."""
        runner = FakeRunner()
        sup = _make_supervisor(runner, store, bus=bus)
        mgr = FakeSkillManager(_invoke_result())
        tool = UseSkillTool(mgr, agent_runner=runner, supervisor=sup)

        ctx = ToolContext(media_store=None, session_id="conv_abc")
        result = await tool.execute(ctx=ctx, skill="test-skill")

        data = json.loads(result.content)
        task_id = data["task_id"]
        row = store.get(task_id)
        assert row is not None
        assert row.originating_conversation_id == "conv_abc"

    @pytest.mark.asyncio
    async def test_no_ctx_leaves_conversation_id_none(self, store, bus):
        """Without ctx, originating_conversation_id is None."""
        runner = FakeRunner()
        sup = _make_supervisor(runner, store, bus=bus)
        mgr = FakeSkillManager(_invoke_result())
        tool = UseSkillTool(mgr, agent_runner=runner, supervisor=sup)

        result = await tool.execute(skill="test-skill")

        data = json.loads(result.content)
        row = store.get(data["task_id"])
        assert row is not None
        assert row.originating_conversation_id is None


# ----------------------------------------------------------------------
# Status mapping
# ----------------------------------------------------------------------


class TestStatusMapping:
    @pytest.mark.asyncio
    async def test_completed_status(self, store, bus):
        """Completed dispatch returns output in ToolResult."""
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content="done!"),
        ])
        sup = _make_supervisor(runner, store, bus=bus)
        mgr = FakeSkillManager(_invoke_result())
        tool = UseSkillTool(mgr, agent_runner=runner, supervisor=sup)

        result = await tool.execute(skill="test-skill")

        assert not result.error
        data = json.loads(result.content)
        assert data["status"] == "completed"
        assert data["output"] == "done!"
        assert data["skill_name"] == "test-skill"
        assert "task_id" in data

    @pytest.mark.asyncio
    async def test_waiting_status(self, store, bus):
        """When skill agent calls ask_user, status is 'waiting'."""

        async def ask_user_stream():
            yield AgentOutput(type=AgentOutputType.TOKEN, content="partial")
            yield AgentOutput(
                type=AgentOutputType.TOOL_RESULT,
                content="What color?",
                metadata={"name": "ask_user", "status": "success"},
            )
            yield AgentOutput(
                type=AgentOutputType.DONE,
                metadata={"turn_messages": [
                    {"role": "assistant", "content": None, "tool_calls": [
                        {"id": "tc_1", "type": "function", "function": {
                            "name": "ask_user",
                            "arguments": '{"question":"What color?"}',
                        }},
                    ]},
                    {"role": "tool", "tool_call_id": "tc_1",
                     "name": "ask_user", "content": "What color?"},
                ]},
            )

        runner = FakeRunner(events_factory=ask_user_stream)
        sup = _make_supervisor(runner, store, bus=bus)
        mgr = FakeSkillManager(_invoke_result())
        tool = UseSkillTool(mgr, agent_runner=runner, supervisor=sup)

        result = await tool.execute(skill="test-skill")

        assert not result.error
        data = json.loads(result.content)
        assert data["status"] == "waiting"
        assert "task_id" in data
        assert "agent_reply" in data["message"]

    @pytest.mark.asyncio
    async def test_failed_status(self, store, bus):
        """When runner raises, supervisor returns failed → error ToolResult."""

        async def failing_stream():
            yield AgentOutput(type=AgentOutputType.TOKEN, content="start")
            raise RuntimeError("LLM exploded")

        runner = FakeRunner(events_factory=failing_stream)
        sup = _make_supervisor(runner, store, bus=bus)
        mgr = FakeSkillManager(_invoke_result())
        tool = UseSkillTool(mgr, agent_runner=runner, supervisor=sup)

        result = await tool.execute(skill="test-skill")

        assert result.error
        data = json.loads(result.content)
        assert data["status"] == "failed"
        assert "RuntimeError" in data["error"]


# ----------------------------------------------------------------------
# Fallback path (no supervisor)
# ----------------------------------------------------------------------


class TestFallbackPath:
    @pytest.mark.asyncio
    async def test_no_supervisor_uses_runner_directly(self):
        """Without supervisor, fork falls back to direct runner path."""
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content="fallback output"),
        ])
        mgr = FakeSkillManager(_invoke_result())
        tool = UseSkillTool(mgr, agent_runner=runner)  # no supervisor

        result = await tool.execute(skill="test-skill")

        data = json.loads(result.content)
        assert data["status"] == "completed"
        assert data["output"] == "fallback output"
        # Allowlist is still enforced via the def
        assert runner.last_agent_def is not None
        assert runner.last_agent_def.tool_filter is not None

    @pytest.mark.asyncio
    async def test_no_runner_falls_back_to_inline(self):
        """Without runner, fork falls back to inline mode wrapped in ToolResult."""
        mgr = FakeSkillManager(_invoke_result())
        tool = UseSkillTool(mgr)  # no runner, no supervisor

        result = await tool.execute(skill="test-skill")

        # Falls back to inline content wrapped in a ToolResult
        assert hasattr(result, "content")
        assert "SKILL ACTIVATED" in result.content


# ----------------------------------------------------------------------
# Manager wiring
# ----------------------------------------------------------------------


class TestSkillManagerWiring:
    def test_set_agent_runner_passes_supervisor(self):
        """SkillToolGroup.set_agent_runner wires supervisor to UseSkillTool."""
        from tank_backend.config.models import SkillsConfig
        from tank_backend.tools.groups import SkillToolGroup

        group = SkillToolGroup(SkillsConfig(enabled=False))
        # Simulate what create_tools would do
        mgr = FakeSkillManager(_invoke_result())
        group._use_skill_tool = UseSkillTool(mgr)

        fake_runner = MagicMock()
        fake_sup = MagicMock()
        group.set_agent_runner(fake_runner, supervisor=fake_sup)

        assert group._use_skill_tool._agent_runner is fake_runner
        assert group._use_skill_tool._supervisor is fake_sup


# ----------------------------------------------------------------------
# Integration: ask_user → pause → resume with dynamic skill def
# ----------------------------------------------------------------------


class TestSkillForkAskUserResume:
    @pytest.mark.asyncio
    async def test_resume_with_answer_rebuilds_dynamic_skill_def(
        self, store, bus,
    ):
        """Full flow: fork → ask_user → waiting → resume → completed.

        Proves that the dynamic skill_<name> definition registered at fork
        time is found by resume_with_answer (which does get_definition by
        name on the runner).
        """
        call_count = {"n": 0}

        async def first_pass_stream():
            """First invocation: partial work, then ask_user."""
            yield AgentOutput(type=AgentOutputType.TOKEN, content="researching...")
            yield AgentOutput(
                type=AgentOutputType.TOOL_RESULT,
                content="Which city do you prefer?",
                metadata={"name": "ask_user", "status": "success"},
            )
            yield AgentOutput(
                type=AgentOutputType.DONE,
                metadata={"turn_messages": [
                    {"role": "assistant", "content": None, "tool_calls": [
                        {"id": "tc_1", "type": "function", "function": {
                            "name": "ask_user",
                            "arguments": '{"question":"Which city?"}',
                        }},
                    ]},
                    {"role": "tool", "tool_call_id": "tc_1",
                     "name": "ask_user", "content": "Which city?"},
                ]},
            )

        async def second_pass_stream():
            """Second invocation (after resume): completes."""
            yield AgentOutput(type=AgentOutputType.TOKEN, content="Paris it is!")
            yield AgentOutput(
                type=AgentOutputType.DONE, metadata={"turn_messages": []},
            )

        async def switching_stream(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                async for ev in first_pass_stream():
                    yield ev
            else:
                async for ev in second_pass_stream():
                    yield ev

        runner = FakeRunner()
        runner.run_agent = switching_stream  # type: ignore[assignment]
        sup = _make_supervisor(runner, store, bus=bus)
        mgr = FakeSkillManager(
            _invoke_result(allowed_tools=["web_search"]),
        )
        tool = UseSkillTool(mgr, agent_runner=runner, supervisor=sup)

        # Step 1: Fork — should pause with status "waiting"
        result = await tool.execute(skill="test-skill")
        data = json.loads(result.content)
        assert data["status"] == "waiting"
        task_id = data["task_id"]

        # Verify the dynamic def was registered
        assert "skill_test-skill" in runner.definitions
        skill_def = runner.definitions["skill_test-skill"]
        assert "web_search" in skill_def.tool_filter

        # Verify row is in waiting state
        row = store.get(task_id)
        assert row is not None
        assert row.status == "waiting"
        assert row.question == "Which city do you prefer?"

        # Step 2: Resume — supervisor looks up "skill_test-skill" def by name
        resumed = await sup.resume_with_answer(task_id, "Paris")
        assert resumed is True

        # Wait for the background task to finish
        await asyncio.sleep(0.2)

        # Verify completion
        final_row = store.get(task_id)
        assert final_row is not None
        assert final_row.status == "completed"
        assert "Paris it is!" in (final_row.output or "")
