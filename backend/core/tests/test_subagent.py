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


@pytest.mark.parametrize("clarification", ["missing", "available", "filtered", "excluded", "named"])
async def test_desktop_prompt_at_http_has_no_self_delegation(
    monkeypatch: pytest.MonkeyPatch, clarification: str,
) -> None:
    """Exercise Runner → LLMAgent → SDK, replacing only HTTP."""
    from dataclasses import replace
    from pathlib import Path

    import httpx
    from openai import AsyncOpenAI

    from tank_backend.agents.ask_user_tool import AskUserTool
    from tank_backend.config.models import ToolsetProfileConfig, ToolsetsConfig
    from tank_backend.llm import llm as llm_module
    from tank_backend.tools.computer_use_macos import ScreenshotTool
    from tank_backend.tools.manager import ToolManager

    requests: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        chunk = {"id": "offline", "object": "chat.completion.chunk", "created": 1,
                 "model": "test", "choices": [{"index": 0, "delta": {"content": "done"},
                                                "finish_reason": "stop"}]}
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")

    client = AsyncOpenAI(api_key="test", base_url="https://offline.invalid/v1",
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(llm_module, "AsyncOpenAI", lambda **kwargs: client)
    monkeypatch.setattr(llm_module, "initialize_langfuse", lambda: None)
    llm = llm_module.LLM(api_key="test", model="test", base_url="https://offline.invalid/v1")
    manager = ToolManager.__new__(ToolManager)
    manager.tools = {"screenshot": ScreenshotTool()}
    if clarification != "missing":
        manager.tools["ask_user"] = AskUserTool()
    definition = parse_agent_file(Path(__file__).resolve().parents[2] / "agents/computer_use.md")
    definition = replace(
        definition,
        tool_filter=("screenshot",) if clarification == "filtered" else None,
        disallowed_tools=frozenset({"ask_user"}) if clarification == "excluded" else frozenset(),
    )
    toolsets = ToolsetsConfig(profiles={"computer_use": ToolsetProfileConfig(
        tools=("screenshot",) if clarification == "named" else ("screenshot", "ask_user"),
    )})
    runner = AgentRunner(llm, manager, Bus(), ToolApprovalPolicy(), PendingToolCallStore(),
                         {definition.name: definition}, toolsets_config=toolsets)
    try:
        outputs = [output async for output in runner.run_agent(
            definition, [{"role": "user", "content": "Inspect the desktop"}],
        )]
    finally:
        await client.close()
    assert outputs and len(requests) == 1
    system = requests[0]["messages"][0]["content"]
    assert "desktop automation agent with vision" in system
    assert "SECURITY BOUNDARIES" in system
    assert "NEVER write secrets" in system
    assert "ENVIRONMENT:" in system
    assert "ALWAYS delegate" not in system
    assert 'agent(subagent_type="computer_use"' not in system
    advertised = {tool["function"]["name"] for tool in requests[0]["tools"]}
    assert ("ask_user" in advertised) == (clarification == "available")
    assert ("`ask_user`" in system) == ("ask_user" in advertised)


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


class ResourceOnlyAgent(SubAgent):
    """A plugin supplies its run loop and release callbacks, not cleanup orchestration."""

    async def run(self, request, context):
        self.check_open()
        yield AgentOutput(AgentOutputType.DONE, metadata={"stop_reason": "final_answer"})


async def test_base_subagent_owns_and_releases_resources_without_running():
    plugin = ResourceOnlyAgent()
    released = []

    async def first():
        released.append("first")

    async def second():
        released.append("second")

    plugin.own_resource("first", first)
    plugin.own_resource("second", second)
    await plugin.aclose()
    await plugin.aclose()
    assert plugin.closed and released == ["second", "first"]
    with pytest.raises(RuntimeError, match="closed"):
        plugin.own_resource("late", first)


@pytest.mark.parametrize("failure", ["exception", "timeout"])
async def test_base_cleanup_attempts_other_resources_and_preserves_failure(failure):
    from tank_backend.agents.subagent import SubAgentCleanupError

    plugin = ResourceOnlyAgent(cleanup_timeout=0.02)
    released = []

    async def good():
        released.append("good")

    async def bad():
        released.append("bad")
        if failure == "timeout":
            await asyncio.Event().wait()
        raise OSError("failed")

    plugin.own_resource("good", good)
    plugin.own_resource("bad", bad)
    with pytest.raises(SubAgentCleanupError, match="bad") as first:
        await plugin.aclose()
    with pytest.raises(SubAgentCleanupError) as repeated:
        await plugin.aclose()
    assert repeated.value is first.value
    assert plugin.closed and released == ["bad", "good"]


async def test_base_cleanup_survives_caller_cancellation():
    plugin = ResourceOnlyAgent()
    started, finish = asyncio.Event(), asyncio.Event()
    released = []

    async def release():
        started.set()
        await finish.wait()
        released.append(True)

    plugin.own_resource("resource", release)
    caller = asyncio.create_task(plugin.aclose())
    await started.wait()
    assert plugin.closed
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    finish.set()
    await plugin.aclose()
    assert released == [True]


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


async def test_adapter_owns_runtime_cleanup_even_when_plugin_close_fails(stack, monkeypatch):
    fake, runner, supervisor, definition, store = stack
    original = fake.run
    released = []

    async def release():
        released.append(True)

    async def run(request, context):
        context.runtime.own("fake_file", release)
        async for output in original(request, context):
            yield output

    monkeypatch.setattr(fake, "run", run)
    fake.close_error = True
    result = await AgentTool(runner, supervisor=supervisor).execute(
        prompt="task", subagent_type="fake",
    )
    assert isinstance(result.content, str)
    assert json.loads(result.content)["status"] == "failed"
    assert released == [True]
    with pytest.raises(SubAgentStopped, match="runtime_closed"):
        fake.context.check()


async def test_adapter_stops_runtime_operations_before_releasing_plugin_resources(
    stack, monkeypatch,
):
    from tank_backend.agents.task_runtime import TaskOperation

    fake, runner, supervisor, definition, store = stack
    entered = asyncio.Event()
    order = []
    operation_task = None

    async def external_operation(value):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            order.append("operation_stopped")

    async def run(request, context):
        nonlocal operation_task
        context.runtime.register(operation)
        operation_task = asyncio.create_task(context.runtime.execute(operation, None))
        await entered.wait()
        yield AgentOutput(AgentOutputType.DONE, metadata={"stop_reason": "final_answer"})

    async def release():
        order.append("resources_released")

    operation = TaskOperation("wait", frozenset({"filesystem"}), "read", external_operation)
    # The ordinary fake registration carries no permissions; grant this test's read explicitly.
    from tank_backend.agents.subagent import SubAgentAuthorization

    monkeypatch.setattr(fake, "run", run)
    monkeypatch.setattr(fake, "aclose", release)
    try:
        outputs = [output async for output in runner.run_agent(
            definition, [{"role": "user", "content": "wait"}],
            authorization=SubAgentAuthorization(frozenset({"filesystem"})),
        )]
        assert outputs[-1].type == AgentOutputType.DONE
        assert order == ["operation_stopped", "resources_released"]
    finally:
        if operation_task is not None:
            await asyncio.gather(operation_task, return_exceptions=True)


async def test_adapter_cleans_up_if_output_iterator_creation_fails(stack, monkeypatch):
    fake, runner, supervisor, definition, store = stack

    def fail_before_iteration(request, context):
        fake.context = context
        raise RuntimeError("iterator creation failed")

    monkeypatch.setattr(fake, "run", fail_before_iteration)
    result = await supervisor.run_foreground(agent_def=definition, prompt="task")
    assert result.status == "failed"
    assert fake.closed
    with pytest.raises(SubAgentStopped, match="runtime_closed"):
        fake.context.check()


async def test_runtime_cleanup_failure_still_releases_plugin_and_preserves_result(
    stack, monkeypatch,
):
    from tank_backend.agents.task_result import TaskResult

    fake, runner, supervisor, definition, store = stack

    async def failed_release():
        raise OSError("runtime resource release failed")

    async def run(request, context):
        context.runtime.own("task_client", failed_release)
        yield TaskResult(
            status="partial", summary="save sent", details={"receipts": ["sent"]},
        ).to_output()

    monkeypatch.setattr(fake, "run", run)
    result = await supervisor.run_foreground(agent_def=definition, prompt="task")
    assert fake.closed and result.status == "unknown"
    assert result.task_result["cleanup"] == "unknown"
    assert result.task_result["details"] == {"receipts": ["sent"]}


@pytest.mark.parametrize("background", [False, True])
async def test_structured_task_input_reaches_plugin_and_survives_reload(stack, background):
    fake, runner, supervisor, definition, store = stack
    task_input = {"schema_version": 1, "inputs": {"filename": "报告.pdf", "overwrite": False}}
    result = await AgentTool(runner, supervisor=supervisor).execute(
        prompt="export document", subagent_type="fake", task_input=task_input,
        run_in_background=background,
    )
    assert isinstance(result.content, str)
    data = json.loads(result.content)
    if background:
        await supervisor.wait(data["task_id"], timeout=2)
    assert fake.request.task_input == task_input
    assert fake.request.task_id == data["task_id"]
    assert store.get(data["task_id"]).task_input == task_input
    task_input["inputs"]["filename"] = "changed.pdf"
    assert fake.request.task_input["inputs"]["filename"] == "报告.pdf"
    assert store.get(data["task_id"]).task_input["inputs"]["filename"] == "报告.pdf"


@pytest.mark.parametrize("task_input", [
    [], "goal", {"x": float("nan")}, {"x": float("inf")}, {1: "bad key"},
    {"x": (1, 2)}, {"x": object()}, {"x": "中" * 22000},
])
async def test_invalid_task_input_is_rejected_before_dispatch(stack, task_input):
    fake, runner, supervisor, definition, store = stack
    result = await AgentTool(runner, supervisor=supervisor).execute(
        prompt="task", subagent_type="fake", task_input=task_input,
    )
    assert result.error and "task_input" in result.content
    assert fake.request is None and store.count_active() == 0
    assert not runner._pending_store.list_pending()
    with pytest.raises(ValueError, match="task_input"):
        supervisor.run_background(agent_def=definition, prompt="task", task_input=task_input)
    with pytest.raises(ValueError, match="task_input"):
        _ = [output async for output in runner.run_agent(
            definition, [{"role": "user", "content": "task"}], task_input=task_input,
        )]


@pytest.mark.parametrize("structured_path", [False, True])
async def test_extension_receives_assembled_task_constraints(stack, structured_path):
    fake, runner, supervisor, definition, store = stack
    runner._prompt_assembler.get_workspace_rules_for = MagicMock(
        side_effect=lambda paths: "Do not overwrite" if "/tmp/report.pdf" in paths else "",
    )
    runner._prompt_assembler.get_base_rules = MagicMock(return_value="Keep secrets private")
    await supervisor.run_foreground(
        agent_def=definition, prompt="Export" if structured_path else "Export /tmp/report.pdf",
        task_input={"path": "/tmp/report.pdf"} if structured_path else None,
    )
    assert "context" in fake.request.context
    assert "Do not overwrite" in fake.request.context
    assert "Keep secrets private" in fake.request.context
    assert "`ask_user`" not in fake.request.context


@pytest.mark.parametrize("engine", [None, "old:agent"])
async def test_structured_input_requires_extension_and_is_advertised(stack, engine):
    fake, runner, supervisor, definition, store = stack
    definition = AgentDefinition("legacy", "", "", engine=engine)
    runner.definitions["legacy"] = definition
    tool = AgentTool(runner, supervisor=supervisor)
    parameter = next(p for p in tool.get_info().parameters if p.name == "task_input")
    assert parameter.type == "object" and not parameter.required
    result = await tool.execute(prompt="task", subagent_type="legacy", task_input={})
    assert result.error and "extension" in result.content
    with pytest.raises(ValueError, match="extension"):
        supervisor.run_background(agent_def=definition, prompt="task", task_input={})
    with pytest.raises(ValueError, match="extension"):
        _ = [o async for o in runner.run_agent(definition, [], task_input={})]
    assert store.count_active() == 0


@pytest.mark.parametrize("reason", ["max_steps", "budget", "context_limit", "unknown", None])
async def test_only_explicit_final_answer_completes(stack, reason):
    fake, runner, supervisor, definition, store = stack
    fake.reason = reason
    result = await supervisor.run_foreground(agent_def=definition, prompt="task")
    assert result.status == "failed" and fake.closed


@pytest.mark.parametrize("status", ["completed", "partial", "unknown", "needs_input", "stopped"])
async def test_structured_task_result_is_not_confused_with_completion(stack, monkeypatch, status):
    from tank_backend.agents.task_result import TaskResult
    from tank_backend.agents.worker_tools import AgentStatusTool

    fake, runner, supervisor, definition, store = stack

    class ResultAgent(FakeSubAgent):
        async def run(self, request, context):
            if status == "needs_input":
                yield AgentOutput(AgentOutputType.TOOL_RESULT, "filename?", {
                    "name": "ask_user", "status": "success",
                })
            yield TaskResult(
                status=status, summary="export result", reason="fixture",
                details={"milestones": ["dialog opened"], "pending_effects": ["save"]},
            ).to_output()

    plugin = ResultAgent()
    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: plugin)
    result = await AgentTool(runner, supervisor=supervisor).execute(
        prompt="export", subagent_type="fake",
    )
    assert isinstance(result.content, str)
    data = json.loads(result.content)
    assert data["status"] == status
    assert data["task_result"]["status"] == status
    assert data["task_result"]["reason"] == "fixture"
    run = store.get(data["task_id"])
    assert run is not None and run.status == status and run.output == "export result"
    assert run.task_result == data["task_result"]
    assert run.completed_at is not None and run.error is None and plugin.closed
    inspected = await AgentStatusTool(store, supervisor).execute(task_id=run.task_id)
    assert isinstance(inspected.content, str)
    assert json.loads(inspected.content)["task_result"] == data["task_result"]
    # Until plugin-aware resume exists, never restart an extension with chat history.
    assert not await supervisor.resume_with_answer(run.task_id, "continue")


@pytest.mark.parametrize("status", ["partial", "unknown", "needs_input", "stopped"])
async def test_background_task_outcome_reaches_notifications(stack, monkeypatch, status):
    from tank_backend.agents.notification_hub import NotificationHub, NotificationHubConfig
    from tank_backend.agents.task_result import TaskResult
    from tank_backend.agents.worker_inbox import WorkerInboxObserver
    from tank_backend.api.agents import get_agent
    from tank_backend.api.router import _worker_event_to_ws_msg

    fake, runner, supervisor, definition, store = stack
    bus = Bus()
    supervisor = WorkerSupervisor(runner, store, bus=bus)
    hub = NotificationHub(bus, NotificationHubConfig(proactive_delivery=False))
    inbox = WorkerInboxObserver(bus)
    events = []
    bus.subscribe("worker", lambda message: events.append(message.payload))

    class ResultAgent(FakeSubAgent):
        async def run(self, request, context):
            yield TaskResult(
                status=status, summary="save remains unverified", reason="fixture",
            ).to_output()

    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: ResultAgent())
    task_id = supervisor.run_background(
        agent_def=definition, prompt="export", originating_conversation_id="conversation",
    )
    run = await supervisor.wait(task_id, timeout=2)
    bus.poll()
    assert run is not None and run.status == status
    assert [event["event"] for event in events] == ["started", status]
    notifications = hub.drain("conversation")
    assert len(notifications) == 1 and status in notifications[0].summary
    assert "save remains unverified" in notifications[0].summary
    assert inbox.drain("conversation")[0].status == status
    monkeypatch.setattr("tank_backend.api.deps.worker_store", lambda: store)
    assert (await get_agent(task_id))["task_result"]["status"] == status
    message = _worker_event_to_ws_msg(events[-1], "session")
    assert message is not None and message.is_final
    assert status in message.content and "save remains unverified" in message.content


@pytest.mark.parametrize("status", ["completed", "partial", "unknown", "needs_input", "stopped"])
@pytest.mark.parametrize("summary", ["", "save unverified"])
async def test_legacy_tool_path_preserves_structured_outcome(stack, monkeypatch, status, summary):
    from tank_backend.agents.task_result import TaskResult

    fake, runner, supervisor, definition, store = stack

    class ResultAgent(FakeSubAgent):
        async def run(self, request, context):
            yield TaskResult(status=status, summary=summary).to_output()

    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: ResultAgent())
    result = await AgentTool(runner).execute(prompt="task", subagent_type="fake")
    assert isinstance(result.content, str)
    data = json.loads(result.content)
    assert data["status"] == status
    assert data["message"] == (summary or f"Agent 'fake' {status} (no text output).")
    assert data["task_result"]["cleanup"] == "confirmed"


async def test_cleanup_failure_retains_task_evidence_as_unknown(stack, monkeypatch):
    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.agents.task_result import TaskResult

    fake, runner, supervisor, definition, store = stack

    class ResultAgent(FakeSubAgent):
        async def run(self, request, context):
            yield TaskResult(
                status="partial", summary="save sent", details={"receipts": ["sent"]},
            ).to_output()

    plugin = ResultAgent()
    plugin.close_error = True
    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: plugin)
    runner._registry.unregister("fake:agent")
    runner._registry.register("fake", ExtensionManifest(
        "agent", "subagent", "_subagent_test:create", permissions=("desktop",),
    ))
    result = await supervisor.run_foreground(
        agent_def=definition, prompt="task",
        authorization=SubAgentAuthorization(frozenset({"desktop"})),
    )
    assert result.status == "unknown"
    assert result.task_result["cleanup"] == "unknown"
    assert result.task_result["details"] == {"receipts": ["sent"]}
    assert "cleanup" in result.error
    with pytest.raises(RuntimeError, match="quarantined"):
        async with runner._desktop_resource.acquire():
            pass


async def test_extension_cannot_resume_through_legacy_chat_history(stack):
    fake, runner, supervisor, definition, store = stack
    store.create(task_id="waiting-plugin", agent_def="fake", prompt="export")
    store.pause("waiting-plugin", question="filename?")
    assert not await supervisor.resume_with_answer("waiting-plugin", "report.pdf")
    assert store.get("waiting-plugin").status == "waiting"
    assert fake.request is None


@pytest.mark.parametrize("change", [
    {"schema_version": 2}, {"schema_version": True}, {"status": "invented"},
    {"summary": 3}, {"details": []}, {"details": {"x": float("nan")}},
    {"extra": "not in contract"}, {"status": "unknown"},
])
async def test_invalid_result_envelope_never_completes(stack, monkeypatch, change):
    fake, runner, supervisor, definition, store = stack

    class InvalidAgent(FakeSubAgent):
        async def run(self, request, context):
            yield AgentOutput(AgentOutputType.DONE, metadata={
                "stop_reason": "completed",
                "task_result": {
                    "schema_version": 1, "status": "completed", "summary": "done", **change,
                },
            })

    plugin = InvalidAgent()
    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: plugin)
    result = await supervisor.run_foreground(agent_def=definition, prompt="task")
    assert result.status == "failed" and result.task_result is None and plugin.closed


@pytest.mark.parametrize("close_error", [False, True])
@pytest.mark.parametrize("status", ["completed", "partial"])
async def test_cleanup_exception_cannot_report_success(stack, monkeypatch, close_error, status):
    from tank_backend.agents.subagent import SubAgentCleanupError
    from tank_backend.agents.task_result import TaskResult

    fake, runner, supervisor, definition, store = stack

    class ErrorAgent(FakeSubAgent):
        async def run(self, request, context):
            yield AgentOutput(AgentOutputType.TOKEN, "action sent")
            raise SubAgentCleanupError("cleanup failed", TaskResult(
                status=status, summary="saved", details={"receipt": "sent"},
            ))

    plugin = ErrorAgent()
    plugin.close_error = close_error
    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: plugin)
    result = await supervisor.run_foreground(agent_def=definition, prompt="task")
    assert result.status == "unknown" and result.task_result["cleanup"] == "unknown"
    assert result.task_result["details"] == {"receipt": "sent"}


@pytest.mark.parametrize("evidence_source", ["terminal", "cleanup_error"])
async def test_cleanup_error_preserves_each_evidence_source(stack, monkeypatch, evidence_source):
    from tank_backend.agents.subagent import SubAgentCleanupError
    from tank_backend.agents.task_result import TaskResult

    fake, runner, supervisor, definition, store = stack
    evidence = TaskResult(status="partial", summary="save sent", details={"receipts": ["sent"]})

    class ErrorAgent(FakeSubAgent):
        async def run(self, request, context):
            if evidence_source == "terminal":
                yield evidence.to_output()
                raise SubAgentCleanupError("producer cleanup failed")
            yield AgentOutput(AgentOutputType.TOKEN, "action sent")

        async def aclose(self):
            self.closed = True
            if evidence_source == "cleanup_error":
                raise SubAgentCleanupError("environment cleanup failed", evidence)

    plugin = ErrorAgent()
    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: plugin)
    result = await supervisor.run_foreground(agent_def=definition, prompt="export")
    assert plugin.closed and result.status == "unknown"
    assert result.task_result["cleanup"] == "unknown"
    assert result.task_result["details"] == {"receipts": ["sent"]}
    assert store.get(result.task_id).task_result == result.task_result


@pytest.mark.parametrize("trigger", [
    "timeout", "stop", "repeat_stop", "timeout_then_stop", "stop_then_timeout",
])
@pytest.mark.parametrize("close_error", [False, True, "cancel"])
async def test_interruption_during_cleanup_keeps_lock_and_evidence(
    stack, monkeypatch, trigger, close_error,
):
    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.agents.task_result import TaskResult

    fake, runner, supervisor, definition, store = stack
    entered, release = asyncio.Event(), asyncio.Event()

    class ClosingAgent(FakeSubAgent):
        async def run(self, request, context):
            yield TaskResult(
                status="partial", summary="save sent", details={"receipts": ["sent"]},
            ).to_output()

        async def aclose(self):
            entered.set()
            await release.wait()
            self.closed = True
            if close_error == "cancel":
                raise asyncio.CancelledError("plugin aborted cleanup")
            if close_error:
                raise RuntimeError("cleanup failed")

    plugin = ClosingAgent()
    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: plugin)
    runner._registry.unregister("fake:agent")
    runner._registry.register("fake", ExtensionManifest(
        "agent", "subagent", "_subagent_test:create", permissions=("desktop",),
    ))
    task_id = supervisor.run_background(
        agent_def=definition, prompt="export",
        authorization=SubAgentAuthorization(frozenset({"desktop"})),
        timeout=0.1 if "timeout" in trigger else None,
    )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if trigger in {"timeout", "timeout_then_stop"}:
            await asyncio.sleep(0.15)
        if trigger != "timeout":
            assert supervisor.stop(task_id)
            await asyncio.sleep(0.15 if trigger == "stop_then_timeout" else 0.01)
            if trigger in {"repeat_stop", "timeout_then_stop", "stop_then_timeout"}:
                assert supervisor.stop(task_id)
                await asyncio.sleep(0.01)
        assert runner._desktop_resource.lock.locked()
        assert not plugin.closed and store.get(task_id).status == "running"
    finally:
        release.set()
        run = await supervisor.wait(task_id, timeout=2)
    assert plugin.closed and run is not None
    assert run.status == ("unknown" if close_error else
                          "timeout" if trigger == "timeout" else "cancelled")
    assert run.task_result["details"] == {"receipts": ["sent"]}
    assert run.task_result["cleanup"] == ("unknown" if close_error else "confirmed")
    if close_error:
        with pytest.raises(RuntimeError, match="quarantined"):
            async with runner._desktop_resource.acquire():
                pass


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
    from tank_protocol.factories import update

    fake, runner, supervisor, definition, store = stack
    approvals = []
    runner._bus.subscribe("ui_message", lambda message: approvals.append(message.payload))
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
    runner._bus.poll()
    assert len(approvals) == 1
    assert all(
        scope in approvals[0].text for scope in ("desktop", "shell", "filesystem", "network")
    )
    assert "permissions" not in approvals[0].metadata
    update("UpdateType.APPROVAL", content=approvals[0].text, metadata=approvals[0].metadata)
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


async def test_approval_binds_a_detached_structured_input(stack):
    fake, runner, supervisor, definition, store = stack
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake", ExtensionManifest(
            "agent", "subagent", "_subagent_test:create", permissions=("desktop",),
        ),
    )
    tool = AgentTool(runner, supervisor=supervisor)
    task_input = {"inputs": {"overwrite": False}}
    await tool.execute(prompt="export", subagent_type="fake", task_input=task_input)
    pending = runner._pending_store.get_oldest_pending()
    task_input["inputs"]["overwrite"] = True
    assert pending.tool_args["task_input"] == {"inputs": {"overwrite": False}}
    pending.on_confirmation(True)
    # Even mutation of the parked arguments must invalidate the confirmed grant.
    pending.tool_args["task_input"]["inputs"]["overwrite"] = True
    result = await tool.execute(**pending.tool_args)
    assert "APPROVAL REQUIRED" in result.content
    assert fake.request is None and store.count_active() == 0
    fresh = runner._pending_store.list_pending()[-1]
    fresh.on_confirmation(True)
    approved = await tool.execute(**fresh.tool_args)
    assert isinstance(approved.content, str)
    assert json.loads(approved.content)["status"] == "completed"
    assert fake.request is not None
    assert fake.request.task_input == {"inputs": {"overwrite": True}}


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


def test_usage_ledger_records_without_limits_and_deduplicates_calls():
    from tank_backend.core.token_usage import TokenUsageLedger

    ledger = TokenUsageLedger()
    ledger.record("large", 10_000_000, 5_000_000)
    ledger.record("large", 10_000_000, 5_000_000)
    ledger.record_unknown("lost")
    ledger.record("later", 2, 3)
    assert ledger.total_tokens == 15_000_005
    assert ledger.unknown_calls == {"lost"}
    assert ledger.call_ids == {"large", "later"}


def test_usage_ledger_reconciles_estimated_and_unknown_usage_once():
    from tank_backend.core.token_usage import TokenUsageLedger

    ledger = TokenUsageLedger()
    ledger.record_estimate("estimated", 20)
    ledger.record_estimate("estimated", 20)
    ledger.record_unknown("lost")
    assert ledger.snapshot()["estimated_tokens"] == 20
    assert ledger.total_tokens == 20
    ledger.record("estimated", 12, 3)
    ledger.record("lost", 4, 1)
    ledger.record_unknown("lost")
    assert ledger.total_tokens == 20
    assert ledger.estimated_tokens == 0
    assert not ledger.unknown_calls
    assert ledger.snapshot()["known_calls"] == 2


@pytest.mark.parametrize("value", [True, -1, "3", 1.5])
def test_usage_ledger_rejects_invalid_known_counts_without_turning_them_into_estimates(value):
    from tank_backend.core.token_usage import TokenUsageLedger

    ledger = TokenUsageLedger()
    with pytest.raises(ValueError):
        ledger.record_event("bad", {
            "prompt_tokens": value, "completion_tokens": 1, "total_tokens": 4,
        })
    assert ledger.total_tokens == 0
    assert not ledger.call_ids
