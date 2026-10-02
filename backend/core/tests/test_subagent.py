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
from tank_backend.agents.task_result import TaskResult
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
        self.reason = "completed"
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
        if self.reason == "completed":
            yield TaskResult(status="completed", summary="hello").to_output()
        elif self.reason:
            yield AgentOutput(AgentOutputType.DONE, metadata={"stop_reason": self.reason})

    async def aclose(self):
        self.closed = True
        if self.close_error:
            raise RuntimeError("cleanup failed")


class ResourceOnlyAgent(SubAgent):
    """A plugin supplies its run loop and release callbacks, not cleanup orchestration."""

    async def run(self, request, context):
        self.check_open()
        yield TaskResult(status="completed", summary="done").to_output()


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
def stack(tmp_path, monkeypatch, request):
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
    db = Database(getattr(request, "param", None) or f"sqlite+pysqlite:///{tmp_path}/db")
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
    data = json.loads(result.content)
    assert data["status"] == "unknown"
    assert data["task_result"]["reason"] == "cleanup_unconfirmed"
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
        yield TaskResult(status="completed", summary="done").to_output()

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


async def test_structured_input_requires_extension_and_is_advertised(stack):
    fake, runner, supervisor, definition, store = stack
    definition = AgentDefinition("legacy", "", "")
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


@pytest.mark.parametrize("reason", ["final_answer", "max_steps", "budget", "unknown", None])
async def test_subagent_requires_structured_result(stack, reason):
    fake, runner, supervisor, definition, store = stack
    fake.reason = reason
    result = await supervisor.run_foreground(agent_def=definition, prompt="task")
    assert result.status == "failed" and fake.closed


@pytest.mark.parametrize("status", ["completed", "partial", "unknown", "needs_input", "stopped"])
async def test_structured_task_result_is_not_confused_with_completion(stack, monkeypatch, status):
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
    assert result.status == "unknown" and "cleanup" in result.error
    assert result.task_result["cleanup"] == "unknown"


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


@pytest.mark.parametrize("extension", ["", "extension: new:agent\n"])
def test_removed_engine_configuration_is_rejected(tmp_path, extension):
    path = tmp_path / "agent.md"
    path.write_text(f"---\nname: test\nengine: old:agent\n{extension}---\nprompt")
    with pytest.raises(ValueError, match="engine.*unsupported"):
        parse_agent_file(path)


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
    assert first.status == "unknown"
    assert first.task_result["reason"] == "cleanup_unconfirmed"
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


async def test_builtin_and_extension_share_desktop_lock(stack, monkeypatch):
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
            yield TaskResult(status="completed", summary="done").to_output()

    monkeypatch.setattr(sys.modules["_subagent_test"], "create", lambda cfg: WaitingSubAgent())
    runner._registry.unregister("fake:agent")
    runner._registry.register(
        "fake",
        ExtensionManifest("agent", "subagent", "_subagent_test:create", permissions=("desktop",)),
    )
    monkeypatch.setattr(
        "tank_backend.agents.runner.LLMAgent", lambda **kwargs: WaitingAgent("builtin")
    )
    definitions = [
        definition,
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


@pytest.mark.parametrize("telemetry", ["normal", "full", "observer_failure", "invalid_reply"])
async def test_runner_assembles_governed_text_model(stack, monkeypatch, telemetry):
    from dataclasses import replace

    import httpx

    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.llm.profile import LLMProfile
    from tank_backend.pipeline.bus import BusMessage
    from tank_backend.pipeline.observers.token_usage import TokenUsageObserver

    _, runner, _, definition, _ = stack
    events = []
    runner._bus.subscribe_all(events.append)
    usage = TokenUsageObserver(runner._bus)
    sent, closed, delegated = [], [], []
    if telemetry == "full":
        for _ in range(256):
            runner._bus.post(BusMessage("existing", "test"))

    class FailingObserver:
        def on_event(self, kind, metadata):
            delegated.append(kind)
            raise RuntimeError("observer unavailable")

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            sent.append(request)
            return httpx.Response(200, json={
                "id": "reply", "object": "chat.completion", "created": 1, "model": "test",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ready"},
                             "finish_reason": (
                                 "length" if telemetry == "invalid_reply" else "stop"
                             )}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            })

        async def aclose(self):
            closed.append(True)

    class TextAgent(SubAgent):
        async def run(self, request, context):
            self.context = context
            assert context.runtime.model is not None
            text = await context.runtime.model.complete([{"role": "user", "content": request.task}])
            yield TaskResult(status="completed", summary=text).to_output()

    plugin = TextAgent()
    monkeypatch.setitem(sys.modules, "_subagent_test", SimpleNamespace(create=lambda cfg: plugin))
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    runner._app_config.llm_profiles["advisor"] = LLMProfile(
        "advisor", "host-secret", "test", "https://offline.invalid/v1", max_tokens=20,
    )
    definition = replace(definition, model="advisor")
    outputs = [out async for out in runner.run_agent(
        definition, [{"role": "user", "content": "inspect text"}], task_id="bound-task",
        authorization=SubAgentAuthorization(frozenset({"network"})),
        observer=FailingObserver() if telemetry == "observer_failure" else None,
    )]
    runner._bus.poll()
    model_events = [event for event in events if event.type == "task_model_call"]
    if telemetry == "full":
        assert model_events == [] and usage.total_tokens == 0
    else:
        assert [event.payload["phase"] for event in model_events] == ["started", "finished"]
        terminal = model_events[-1].payload
        assert terminal["task_id"] == "bound-task"
        assert terminal["call_id"] in plugin.context.budget.call_ids
        assert usage.total_tokens == 10
    assert plugin.context.budget.total_tokens == 10
    if telemetry == "observer_failure":
        assert delegated == ["model_call", "model_call"]
    assert "host-secret" not in repr(model_events)
    assert "inspect text" not in repr(model_events)
    assert len(sent) == 1
    assert sent[0].headers["authorization"] == "Bearer host-secret"
    assert json.loads(sent[0].content)["max_tokens"] == 20
    if telemetry == "invalid_reply":
        assert outputs[-1].metadata["stop_reason"] == "model_error"
    else:
        assert outputs[-1].content == "ready"
        assert outputs[-1].metadata["total_tokens"] == 10
    assert closed == [True] and plugin.closed
    assert "host-secret" not in repr(outputs)
    assert plugin.context.runtime.model is not None
    with pytest.raises(SubAgentStopped):
        await plugin.context.runtime.model.complete([{"role": "user", "content": "late"}])
    assert len(sent) == 1


def test_extension_model_adds_network_to_approval(stack):
    from dataclasses import replace

    _, runner, _, definition, _ = stack
    assert runner.extension_permissions(definition) == frozenset()
    assert runner.extension_permissions(replace(definition, model="advisor")) == {"network"}


@pytest.mark.parametrize(
    "invalid", ["missing", "http", "query", "headers", "body", "tokens", "grant"],
)
async def test_runner_rejects_model_before_plugin_factory(stack, monkeypatch, invalid):
    from dataclasses import replace

    import httpx

    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.llm.profile import LLMProfile

    _, runner, _, definition, _ = stack
    created = []
    monkeypatch.setitem(sys.modules, "_subagent_test", SimpleNamespace(
        create=lambda cfg: created.append("plugin"),
    ))
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda: created.append("http"))
    profile = LLMProfile("advisor", "secret", "test", "https://offline.invalid/v1")
    changes = {
        "http": {"base_url": "http://offline.invalid/v1"},
        "query": {"base_url": "https://offline.invalid/v1?secret=hidden"},
        "headers": {"extra_headers": {"X-Secret": "hidden"}},
        "body": {"extra_body": {"reasoning": True}},
        "tokens": {"max_tokens": 0},
    }
    runner._app_config.llm_profiles["default"] = profile
    if invalid != "missing":
        runner._app_config.llm_profiles["advisor"] = replace(profile, **changes.get(invalid, {}))
    definition = replace(definition, model="advisor")
    with pytest.raises((ValueError, SubAgentStopped)):
        _ = [out async for out in runner.run_agent(
            definition, [{"role": "user", "content": "task"}],
            authorization=SubAgentAuthorization(
                frozenset() if invalid == "grant" else frozenset({"network"}),
            ),
        )]
    assert created == []


@pytest.mark.parametrize("stack", [None, "sqlite+pysqlite:///:memory:"], indirect=True)
async def test_supervisor_persists_native_audit_before_dispatch(stack, monkeypatch):
    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.agents.task_runtime import TaskOperation

    fake, _, supervisor, definition, store = stack
    sent = []

    async def run(request, context):
        async def invoke(value):
            records = store.audit_records(request.task_id)
            assert [record.status for record in records] == ["not_sent", "unknown"]
            sent.append(value)
            return value

        operation = TaskOperation("inspect", frozenset({"filesystem"}), "read", invoke)
        context.runtime.register(operation)
        await context.runtime.execute(operation, "document")
        yield TaskResult(status="completed", summary="done").to_output()

    monkeypatch.setattr(fake, "run", run)
    result = await supervisor.run_foreground(
        agent_def=definition, prompt="task",
        authorization=SubAgentAuthorization(frozenset({"filesystem"})),
    )
    assert result.status == "completed" and sent == ["document"]
    assert [record.status for record in store.audit_records(result.task_id)] == [
        "not_sent", "unknown", "returned",
    ]


@pytest.mark.parametrize("fail_phase", [None, "prepared", "dispatch", "finished"])
async def test_supervisor_persists_model_intent_before_http_and_usage_after(
    stack, monkeypatch, fail_phase,
):
    from dataclasses import replace

    import httpx

    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.llm.profile import LLMProfile

    fake, runner, supervisor, definition, store = stack
    before_http, errors = [], []
    append = store.append_audit

    def append_or_fail(record):
        if record.phase == fail_phase:
            raise OSError("private-database-path")
        append(record)

    monkeypatch.setattr(store, "append_audit", append_or_fail)

    async def provider(request):
        records = store.audit_records(fake.request.task_id)
        before_http.extend(records)
        assert [record.status for record in records] == ["not_sent", "unknown"]
        return httpx.Response(200, json={
            "id": "reply", "object": "chat.completion", "created": 1, "model": "test",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ready"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        })

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda: httpx.MockTransport(provider))
    runner._app_config.llm_profiles["advisor"] = LLMProfile(
        "advisor", "private-secret", "test", "https://offline.invalid/v1", max_tokens=20,
    )

    async def run(request, context):
        fake.request, fake.context = request, context
        assert context.runtime.model is not None
        for _ in range(2 if fail_phase else 1):
            try:
                await context.runtime.model.complete(
                    [{"role": "user", "content": "private-prompt"}],
                )
            except SubAgentStopped as exc:
                errors.append(exc.reason)
        yield TaskResult(status="completed", summary="done").to_output()

    monkeypatch.setattr(fake, "run", run)
    result = await supervisor.run_foreground(
        agent_def=replace(definition, model="advisor"), prompt="task",
        authorization=SubAgentAuthorization(frozenset({"network"})),
    )
    records = store.audit_records(result.task_id)
    if fail_phase:
        assert result.status == "unknown"
        assert result.task_result["reason"] == "audit_failed"
        assert result.task_result["cleanup"] == "confirmed"
        assert errors == ["audit_failed", "audit_failed"]
        assert fake.context.budget.total_tokens == (10 if fail_phase == "finished" else 0)
        assert len(before_http) == (2 if fail_phase == "finished" else 0)
        assert "private" not in str(result)
        return
    assert result.status == "completed"
    assert [record.phase for record in records] == ["prepared", "dispatch", "finished"]
    assert len({record.call_id for record in records}) == 1
    assert records[-1].call_id in fake.context.budget.call_ids
    assert records[-1].prompt_tokens == 7 and records[-1].completion_tokens == 3
    assert before_http == records[:2]
    assert "private" not in repr(records)


async def test_output_quota_retains_partial_output_and_closes_the_task():
    from tank_backend.agents.base import AgentState
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentContext, SubAgentRequest
    from tank_backend.agents.subagent_adapter import SubAgentAdapter

    class Chatty(SubAgent):
        async def run(self, request, context):
            yield AgentOutput(AgentOutputType.TOKEN, "kept")
            yield AgentOutput(AgentOutputType.TOKEN, "overflow")
            pytest.fail("producer must be stopped at the output boundary")

    plugin = Chatty()
    ctx = SubAgentContext(
        SubAgentAuthorization(), SubAgentBudget(), asyncio.Event(), max_output_events=1,
    )
    adapter = SubAgentAdapter("chatty", plugin, SubAgentRequest("task", "", "quota"), ctx)
    outputs = [output async for output in adapter.run(AgentState())]
    assert outputs[0].content == "kept" and len(outputs) == 2
    assert outputs[-1].metadata["task_result"]["status"] == "partial"
    assert outputs[-1].metadata["task_result"]["reason"] == "output_limit"
    assert plugin.closed


async def test_success_cannot_hide_an_unknown_native_effect(stack, monkeypatch):
    from contextlib import suppress

    from tank_backend.agents.subagent import SubAgentAuthorization
    from tank_backend.agents.task_runtime import TaskOperation

    fake, _, supervisor, definition, _ = stack

    async def run(request, context):
        async def failed(value):
            raise OSError("acknowledgement lost")

        operation = TaskOperation("write", frozenset({"filesystem"}), "action", failed)
        context.runtime.register(operation)
        with suppress(OSError):
            await context.runtime.execute(operation, None)
        yield TaskResult(status="completed", summary="done").to_output()

    monkeypatch.setattr(fake, "run", run)
    result = await supervisor.run_foreground(
        agent_def=definition, prompt="task",
        authorization=SubAgentAuthorization(frozenset({"filesystem"})),
    )
    assert result.status == "unknown"
    assert result.task_result["reason"] == "effect_unknown"


@pytest.mark.parametrize("caller", ["text", "computer_use", "llm"])
@pytest.mark.parametrize("outcome", ["ok", "revoked", "audit_failure"])
async def test_retained_callers_share_governance(stack, monkeypatch, caller, outcome):
    """One acceptance contract over real Runner/SDK paths; only HTTP and OS are fake."""
    from pathlib import Path

    import agent_computer_use
    import httpx
    from agent_computer_use.agent import ComputerUseSubAgent
    from agent_computer_use.contracts import AdvisorResult, DispatchReceipt, Element, Fact, Snapshot
    from agent_computer_use.controller import ComputerUseController
    from openai import AsyncOpenAI

    from tank_backend.agents import runner as runner_module
    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentContext
    from tank_backend.llm.llm import LLM
    from tank_backend.llm.profile import LLMProfile
    from tank_backend.plugin.manifest import read_manifest_from_yaml

    _, runner, _, _, _ = stack
    contexts, sent, audit_records, closed, actions = [], [], [], [], []
    grant = SubAgentAuthorization(frozenset({"desktop", "network", "filesystem", "shell"}))
    original_context = SubAgentContext

    def context_factory(*args, **kwargs):
        ctx = original_context(*args, **kwargs)
        contexts.append(ctx)
        return ctx

    monkeypatch.setattr(runner_module, "SubAgentContext", context_factory)

    async def audit(record):
        audit_records.append(record)
        if outcome == "audit_failure" and record.category == "model":
            raise OSError("required audit unavailable")

    class HTTP(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            # Evidence must exist before the external boundary, not be added afterwards.
            assert any(r.category == "model" and r.phase == "dispatch" for r in audit_records)
            sent.append(request)
            body = json.loads(request.content)
            usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
            if outcome == "revoked":
                grant.revoke()
            if body.get("stream"):
                chunk = {"id": "reply", "object": "chat.completion.chunk", "created": 1,
                         "model": "test-model", "usage": usage,
                         "choices": [{"index": 0, "delta": {"content": "ready"},
                                      "finish_reason": "stop"}]}
                return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                      content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")
            return httpx.Response(200, json={
                "id": "reply", "object": "chat.completion", "created": 1, "model": "test-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ready"},
                             "finish_reason": "stop"}], "usage": usage,
            })

        async def aclose(self):
            closed.append(self)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", HTTP)
    profile = LLMProfile(
        "shared", "host-secret", "test-model", "https://offline.invalid/v1", max_tokens=20,
    )
    runner._app_config.llm_profiles.update(shared=profile)
    client = AsyncOpenAI(api_key="host-secret", base_url=profile.base_url,
                         http_client=httpx.AsyncClient(transport=HTTP()))
    runner._llm = LLM(api_key="host-secret", model="test-model", base_url=profile.base_url,
                      max_tokens=20, client=client)
    runner._tool_manager.get_openai_tools.return_value = []
    manifest = read_manifest_from_yaml(
        Path(__file__).parents[2] / "plugins/agent-computer-use/plugin.yaml",
    )
    runner._registry.register(manifest.plugin_name, manifest.extensions[0])

    class TextAgent(SubAgent):
        async def run(self, request, context):
            assert context.runtime.model is not None
            text = await context.runtime.model.complete([{"role": "user", "content": request.task}])
            yield TaskResult(status="completed", summary=text).to_output()

    class World:
        observations = 0

        async def observe(self, scope, ctx):
            self.observations += 1
            return Snapshot(str(self.observations), scope, len(actions),
                            (Element("field", "textbox", "Name", ("fill",)),),
                            facts=(Fact(key="name", value="ready"),) if actions else ())

        async def is_current(self, binding, action, ctx):
            return binding.generation == len(actions)

        async def dispatch(self, binding, action, ctx):
            actions.append(action)
            return DispatchReceipt(action.id, "sent")

    class Advisor:
        async def assist(self, request, goal, snapshot, action_set, ctx):
            assert ctx.runtime.model is not None
            value = await ctx.runtime.model.complete([{"role": "user", "content": request.task}])
            return AdvisorResult(
                action_set.binding, "inputs", inputs=(Fact(key="name", value=value),),
            )

    world = World()
    monkeypatch.setattr(agent_computer_use, "create_subagent", lambda config:
                        ComputerUseSubAgent(ComputerUseController(world, world, advisor=Advisor())))
    monkeypatch.setitem(
        sys.modules, "_subagent_test", SimpleNamespace(create=lambda cfg: TextAgent()),
    )
    task_input = None
    if caller == "llm":
        definition = AgentDefinition("shared", "", "")
    else:
        extension = {"text": "fake:agent", "computer_use": "agent-computer-use:agent"}[caller]
        definition = AgentDefinition("shared", "", "", extension=extension, model="shared")
        if caller == "computer_use":
            task_input = {
                "schema_version": 1, "objective": "Fill name", "scope": "document", "inputs": [],
                "milestones": [{"id": "name", "operation": "fill", "role": "textbox",
                                "label": "Name", "input_key": "name",
                                "postcondition": {"key": "name", "value": "ready"}}],
                "completion": [{"key": "name", "value": "ready"}],
            }
    try:
        outputs = [item async for item in runner.run_agent(
            definition, [{"role": "user", "content": "Fill name"}], task_id="shared-task",
            authorization=grant, audit=audit, task_input=task_input,
        )]
        assert len(contexts) == 1
        ctx = contexts[0]
        assert ctx.authorization is grant and ctx.runtime.task_id == "shared-task"
        assert len(sent) == (0 if outcome == "audit_failure" else 1)
        model_records = [r for r in audit_records if r.category == "model"]
        assert len({r.call_id for r in model_records}) == 1
        assert all(r.task_id == "shared-task" for r in audit_records)
        terminals = [o for o in outputs if o.type == AgentOutputType.DONE]
        if outcome == "ok":
            assert ctx.budget.total_tokens == 10 and len(ctx.budget.call_ids) == 1
            assert model_records[-1].status == "returned"
            assert model_records[-1].call_id in ctx.budget.call_ids
            assert not any(o.metadata.get("status") == "error" for o in outputs)
            assert len(terminals) == 1
            if caller == "computer_use":
                result = terminals[0].metadata["task_result"]
                assert result["status"] == "completed" and result["cleanup"] == "confirmed"
            elif caller != "llm":
                assert terminals[0].metadata["stop_reason"] == "completed"
            assert len(actions) == (1 if caller == "computer_use" else 0)
        else:
            assert actions == []
            assert not any(o.type == AgentOutputType.DONE
                           and o.metadata.get("stop_reason") == "completed" for o in outputs)
            assert not any(o.metadata.get("task_result", {}).get("status") == "completed"
                           for o in terminals)
        assert "host-secret" not in repr(audit_records) + repr(outputs)
        with pytest.raises(SubAgentStopped, match="runtime_closed"):
            ctx.check()
        # Closing the task must not close the borrowed main LLM connection pool.
        assert not client.is_closed()
        if caller != "llm":
            assert len(closed) == 1
    finally:
        await client.close()
