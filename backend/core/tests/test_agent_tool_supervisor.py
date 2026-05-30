"""Tests for AgentTool when wired through WorkerSupervisor (Phase 2 Step 3).

These pin the contract that the LLM sees: when AgentTool dispatches
through the supervisor, the return shape stays bit-for-bit identical
to the legacy runner-only path — same keys, same error format, same
graceful handling of depth/concurrency limits and worker failures.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from tank_backend.agents.agent_tool import AgentTool
from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.store import WorkerStore
from tank_backend.agents.supervisor import WorkerSupervisor
from tank_backend.persistence import Base, Database
from tank_backend.pipeline.bus import Bus, BusMessage

# ----------------------------------------------------------------------
# Fakes / helpers
# ----------------------------------------------------------------------

class FakeRunner:
    """Minimal AgentRunner stub.

    Exposes the two attributes AgentTool reaches for (``definitions``,
    ``get_definition``) plus an async ``run_agent`` whose output is
    scripted per test.
    """

    def __init__(
        self,
        definitions: dict[str, AgentDefinition] | None = None,
        *,
        outputs: list[AgentOutput] | None = None,
        events_factory: Callable[[], AsyncIterator[AgentOutput]] | None = None,
    ) -> None:
        self.definitions = definitions or {
            "coder": AgentDefinition(
                name="coder",
                description="execute code",
                system_prompt="be terse",
                max_turns=5,
            ),
        }
        self._outputs = outputs or [
            AgentOutput(type=AgentOutputType.TOKEN, content="ok"),
        ]
        self._events_factory = events_factory

    def get_definition(self, name: str) -> AgentDefinition | None:
        return self.definitions.get(name)

    async def run_agent(
        self,
        *,
        agent_def: AgentDefinition,
        messages: list[dict[str, Any]],
        parent_agent_id: str | None = None,
        background: bool = False,
        max_turns: int | None = None,
    ) -> AsyncIterator[AgentOutput]:
        if self._events_factory is not None:
            async for ev in self._events_factory():
                yield ev
            return
        for ev in self._outputs:
            yield ev


@pytest.fixture()
def store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    yield WorkerStore(db)
    db.dispose()


def _make_supervisor(
    runner: FakeRunner,
    store: WorkerStore,
    *,
    bus: Bus | None = None,
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
# Happy path — return shape preserved
# ----------------------------------------------------------------------

class TestSupervisorReturnShape:
    @pytest.mark.asyncio
    async def test_returns_legacy_keys_plus_supervisor_extras(
        self, store: WorkerStore,
    ):
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content="hello "),
            AgentOutput(type=AgentOutputType.TOKEN, content="world"),
        ])
        sup = _make_supervisor(runner, store)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]

        result = await tool.execute(
            prompt="say hi",
            subagent_type="coder",
            description="greet",
        )

        # Legacy keys — these must not regress.
        assert result["agent_type"] == "coder"
        assert result["description"] == "greet"
        assert result["message"] == "hello world"
        # New keys layered on top.
        assert result["status"] == "completed"
        assert result["task_id"].startswith("t_")

    @pytest.mark.asyncio
    async def test_no_text_output_falls_back_to_legacy_message(
        self, store: WorkerStore,
    ):
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.THOUGHT, content="..."),
        ])
        sup = _make_supervisor(runner, store)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]
        result = await tool.execute(prompt="x", subagent_type="coder")
        assert (
            result["message"]
            == "Agent 'coder' completed (no text output)."
        )

    @pytest.mark.asyncio
    async def test_unknown_agent_type_returns_error_shape(
        self, store: WorkerStore,
    ):
        runner = FakeRunner(definitions={})
        sup = _make_supervisor(runner, store)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]
        result = await tool.execute(prompt="x", subagent_type="nonexistent")
        assert "error" in result
        assert "nonexistent" in result["error"]
        # And it returned without dispatching — no row was created.
        assert store.count_active() == 0


# ----------------------------------------------------------------------
# Failure mapping — limit / cancellation / runner-error paths
# ----------------------------------------------------------------------

class TestFailureMapping:
    @pytest.mark.asyncio
    async def test_concurrency_limit_returns_graceful_message(
        self, store: WorkerStore,
    ):
        # Pre-fill so the next dispatch trips the limit.
        for i in range(3):
            store.create(
                task_id=f"existing_{i}", agent_def="other", prompt="...",
            )
        runner = FakeRunner()
        sup = _make_supervisor(runner, store, max_concurrent=3)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]
        result = await tool.execute(prompt="x", subagent_type="coder")

        assert result["agent_type"] == "coder"
        assert "error" in result
        assert "max concurrent" in result["error"]
        assert "Cannot spawn agent 'coder'" in result["message"]
        # Pre-existing rows untouched; no new dispatch row created.
        assert store.count_active() == 3

    @pytest.mark.asyncio
    async def test_depth_limit_returns_graceful_message(
        self, store: WorkerStore,
    ):
        # The supervisor evaluates depth via parent_task_id chains.
        # AgentTool always passes parent_task_id=None for now (Step 3
        # doesn't expose nested dispatch from the LLM), so we exercise
        # the depth-limit path through a max_depth=0 supervisor.
        runner = FakeRunner()
        sup = _make_supervisor(runner, store, max_depth=0)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]
        result = await tool.execute(prompt="x", subagent_type="coder")
        assert "error" in result
        assert "max depth" in result["error"]

    @pytest.mark.asyncio
    async def test_runner_exception_surfaces_failure_in_message(
        self, store: WorkerStore,
    ):
        async def boom():
            yield AgentOutput(type=AgentOutputType.TOKEN, content="part")
            raise RuntimeError("kaboom")
        runner = FakeRunner(events_factory=boom)
        sup = _make_supervisor(runner, store)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]

        result = await tool.execute(prompt="x", subagent_type="coder")

        # The LLM sees a structured failure rather than an exception.
        assert result["status"] == "failed"
        assert "kaboom" in result["message"]
        assert "Partial output" in result["message"]
        assert "part" in result["message"]


# ----------------------------------------------------------------------
# ToolContext — originating_conversation_id capture
# ----------------------------------------------------------------------

class TestOriginatingConversationCapture:
    @pytest.mark.asyncio
    async def test_session_id_from_ctx_lands_on_worker_row(
        self, store: WorkerStore,
    ):
        from tank_backend.tools.base import TOOL_CONTEXT_KWARG, ToolContext

        runner = FakeRunner()
        sup = _make_supervisor(runner, store)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]

        ctx = ToolContext(media_store=None, session_id="conv_xyz")
        result = await tool.execute(
            prompt="x",
            subagent_type="coder",
            **{TOOL_CONTEXT_KWARG: ctx},
        )
        row = store.get(result["task_id"])
        assert row is not None
        assert row.originating_conversation_id == "conv_xyz"

    @pytest.mark.asyncio
    async def test_no_ctx_leaves_originating_conversation_id_none(
        self, store: WorkerStore,
    ):
        runner = FakeRunner()
        sup = _make_supervisor(runner, store)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]
        result = await tool.execute(prompt="x", subagent_type="coder")
        row = store.get(result["task_id"])
        assert row is not None
        assert row.originating_conversation_id is None


# ----------------------------------------------------------------------
# Bus
# ----------------------------------------------------------------------

class TestBusIntegration:
    @pytest.mark.asyncio
    async def test_supervisor_path_posts_started_and_completed_events(
        self, store: WorkerStore,
    ):
        bus = Bus()
        captured: list[BusMessage] = []
        bus.subscribe("worker", captured.append)
        # Bus is poll-based; eager-dispatch in tests.
        original_post = bus.post

        def post_and_dispatch(msg: BusMessage) -> None:
            original_post(msg)
            bus.poll()

        bus.post = post_and_dispatch  # type: ignore[method-assign]

        runner = FakeRunner()
        sup = _make_supervisor(runner, store, bus=bus)
        tool = AgentTool(runner, supervisor=sup)  # type: ignore[arg-type]

        await tool.execute(prompt="x", subagent_type="coder")

        events = [m.payload["event"] for m in captured]
        assert events == ["started", "completed"]


# ----------------------------------------------------------------------
# Legacy fallback — supervisor=None preserves the pre-Phase-2 path
# ----------------------------------------------------------------------

class TestLegacyFallback:
    @pytest.mark.asyncio
    async def test_no_supervisor_falls_back_to_runner_path(self):
        runner = FakeRunner(outputs=[
            AgentOutput(type=AgentOutputType.TOKEN, content="legacy "),
            AgentOutput(type=AgentOutputType.TOKEN, content="path"),
        ])
        tool = AgentTool(runner)  # type: ignore[arg-type] — no supervisor

        result = await tool.execute(prompt="x", subagent_type="coder")
        assert result["agent_type"] == "coder"
        assert result["message"] == "legacy path"
        # Legacy path doesn't add task_id / status keys.
        assert "task_id" not in result
        assert "status" not in result


# ----------------------------------------------------------------------
# tools.manager wiring — set_agent_runner accepts a supervisor
# ----------------------------------------------------------------------

class TestManagerWiring:
    def test_set_agent_runner_accepts_supervisor_kwarg(self):
        # Smoke test: the public ToolManager.set_agent_runner signature
        # accepts ``supervisor=`` so api/server.py and Brain can pass
        # it without monkeypatching.
        from tank_backend.tools.manager import ToolManager
        sig_compat = ToolManager.set_agent_runner
        # Bound on a fresh instance without bringing in real LLM/policy.
        # Just check the function accepts the kwarg name.
        import inspect
        params = inspect.signature(sig_compat).parameters
        assert "supervisor" in params
        assert params["supervisor"].kind == inspect.Parameter.KEYWORD_ONLY

    def test_manager_registers_agent_tool_with_supervisor(self):
        """Construct a real ToolManager + register agent tool with a
        supervisor and confirm AgentTool resolves the supervisor path."""
        from tank_backend.config.models import (
            AuditConfig,
            CommandSecurityConfig,
            FileAccessConfig,
            NetworkAccessConfig,
            SandboxConfig,
            SkillsConfig,
        )
        from tank_backend.tools.manager import ToolManager

        cfg = MagicMock()
        cfg.network_access = NetworkAccessConfig()
        cfg.file_access = FileAccessConfig()
        cfg.audit = AuditConfig()
        cfg.command_security = CommandSecurityConfig()
        cfg.sandbox = SandboxConfig(enabled=False)
        cfg.skills = SkillsConfig(enabled=False)
        cfg.get_llm_profile = MagicMock(
            side_effect=lambda name: MagicMock(
                api_key="test", model="test", base_url="http://test",
                extra_headers={}, stream_options=False,
            ),
        )

        bus = Bus()
        manager = ToolManager(app_config=cfg, bus=bus)
        runner = FakeRunner()
        # Build a real supervisor on a temp DB.
        import tempfile
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            suffix=".db", delete=False,
        )
        tmp.close()
        db = Database(f"sqlite+pysqlite:///{tmp.name}")
        Base.metadata.create_all(db.engine)
        sup = _make_supervisor(runner, WorkerStore(db))

        manager.set_agent_runner(runner, supervisor=sup)
        tool = manager.tools["agent"]
        assert isinstance(tool, AgentTool)
        # Internal pointer should be the supervisor we passed (not None).
        assert tool._supervisor is sup  # type: ignore[attr-defined]

        db.dispose()


def _MagicMock():  # pragma: no cover — workaround for pyright
    return MagicMock()
