"""Real pinned SDK + fake computer/completions; no paid calls or desktop input."""

import asyncio
import base64
import io
import inspect
import json
from unittest.mock import AsyncMock
from typing import Any

import pytest
import httpx
from PIL import Image
from yutori.navigator.macos.types import CancellationLatch
from yutori.navigator.macos.computer import MacOSComputer

from tank_backend.agents.base import AgentOutputType
from tank_backend.agents.subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentContext,
    SubAgentRequest,
    SubAgentStopped,
)
from agent_n2_sdk.agent import N2SdkSubAgent
from agent_n2_sdk.config import N2SdkConfig
from agent_n2_sdk.environment import GuardedComputer
from agent_n2_sdk.model import N2ModelClient


class Computer:
    def __init__(self):
        self.cancellation = CancellationLatch()
        self.actions = []
        self.aclose = AsyncMock()
        self.__aenter__ = AsyncMock(return_value=self)
        self.fail_click = False
        self.run_bash_command: Any = None
        self.drag: Any = None
        self.hold_key: Any = None

    async def get_dimensions(self):
        return 100, 100

    async def click(self, x, y, button="left", modifier=None):
        self.actions.append((x, y, {"button": button, "modifier": modifier}))
        if self.fail_click:
            raise RuntimeError("click failed")

    async def screenshot(self):
        data = io.BytesIO()
        Image.new("RGB", (100, 100)).save(data, format="PNG")
        return base64.b64encode(data.getvalue()).decode()

    async def wait(self, ms):
        await asyncio.sleep(0)


class Completions:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
        self.aclose = AsyncMock()

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.replies)


def reply(content="done", actions=None, usage=True, finish="stop"):
    message: dict[str, Any] = {
        "role": "assistant",
        "content": content,
        "reasoning_content": "thinking",
    }
    if actions is not None:
        message["tool_calls"] = [
            {
                "id": "call1",
                "type": "function",
                "function": {
                    "name": "computer_batch",
                    "arguments": json.dumps({"actions": actions}),
                },
            }
        ]
    return {
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}
        if usage
        else None,
    }


def context(limit=100):
    return SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop", "shell", "filesystem", "network"})),
        SubAgentBudget(limit=limit),
        asyncio.Event(),
    )


def governed_client(completions, config, ctx):
    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            response = await completions.create(**json.loads(request.content))
            return httpx.Response(200, json={
                "id": "test", "model": "n2", "created": 1, "object": "chat.completion",
                **response,
            })

        async def aclose(self):
            await completions.aclose()

    return N2ModelClient(config, ctx, inner=Transport())


def agent(computer, completions, **config):
    return N2SdkSubAgent(
        N2SdkConfig(api_key="test", screenshot_delay=0, **config),
        computer_factory=lambda ctx: GuardedComputer(computer, ctx),
        client_factory=lambda cfg, ctx: governed_client(completions, cfg, ctx),
    )


async def collect(plugin, ctx):
    try:
        return [
            o async for o in plugin.run(SubAgentRequest("task", "context", "task-id"), ctx)
        ]
    finally:
        await plugin.aclose()


async def test_real_sdk_tool_events_usage_and_cleanup():
    computer = Computer()
    completions = Completions(
        [
            reply(
                "working",
                [{"name": "left_click", "arguments": {"coordinates": [500, 500]}}],
            ),
            reply(),
        ]
    )
    ctx = context()
    plugin = agent(computer, completions)
    outputs = await collect(plugin, ctx)
    assert len(computer.actions) == 1 and computer.actions[0][:2] == (50, 50)
    assert sum(o.type == AgentOutputType.TOOL_EXECUTING for o in outputs) == 1
    assert sum(o.type == AgentOutputType.USAGE for o in outputs) == 2
    assert ctx.budget.total_tokens == 14
    assert outputs[-1].metadata["stop_reason"] == "final_answer"
    await plugin.aclose()
    computer.aclose.assert_awaited_once()
    completions.aclose.assert_awaited_once()
    assert any(
        m.get("reasoning_content") == "thinking"
        for m in completions.calls[1]["messages"]
    )


async def test_real_macos_adapter_through_sdk_without_host_input():
    data = io.BytesIO()
    Image.new("RGB", (100, 100)).save(data, format="PNG")
    frame = {
        "content": [{"type": "image", "data": base64.b64encode(data.getvalue()).decode(),
                     "mimeType": "image/png"}],
        "structuredContent": {"screenshot_width": 100, "screenshot_height": 100},
    }
    transport = AsyncMock()
    transport.call_tool.return_value = frame
    computer = MacOSComputer(transport=transport, owns_transport=True,
                             presentation=False, verify_focus=False)
    actions = [
        {"name": "left_click", "arguments": {"coordinates": [500, 500], "modifier": "shift"}},
        {"name": "key_press", "arguments": {"key": "command+a"}},
        {"name": "type", "arguments": {"text": "hello"}},
        {"name": "mouse_move", "arguments": {"coordinates": [400, 400]}},
        {"name": "drag", "arguments": {"start_coordinates": [400, 400], "coordinates": [600, 600]}},
    ]
    outputs = await collect(
        agent(computer, Completions([reply(actions=actions), reply()])), context()
    )
    results = [o for o in outputs if o.type == AgentOutputType.TOOL_RESULT]
    assert len(results) == 1 and results[0].metadata["status"] == "success"
    assert results[0].metadata["completed_primitives"] == 5
    assert outputs[-1].metadata["primitives"] == 5
    names = [c.args[0] for c in transport.call_tool.await_args_list]
    assert all(name in names for name in ["click", "hotkey", "type_text", "move_cursor", "drag"])
    click = next(c.args[1] for c in transport.call_tool.await_args_list if c.args[0] == "click")
    assert click["x"] == 50 and click["y"] == 50 and click["modifier"] == ["shift"]
    assert "end_session" in names
    transport.close.assert_awaited_once()


@pytest.mark.parametrize("name", ["click", "keypress", "type", "move", "drag", "wait", "hold_key"])
def test_guard_preserves_macos_method_signatures(name):
    computer = MacOSComputer(transport=AsyncMock(), owns_transport=True)
    guarded = GuardedComputer(computer, context())
    assert inspect.signature(getattr(guarded, name)) == inspect.signature(getattr(computer, name))


@pytest.mark.parametrize("stop", ["cancel", "revoke"])
async def test_guard_checks_stop_before_action(stop):
    computer, ctx = Computer(), context()
    guarded = GuardedComputer(computer, ctx)
    if stop == "cancel":
        ctx.cancel.set()
        error = asyncio.CancelledError
    else:
        ctx.authorization.revoke()
        error = SubAgentStopped
    with pytest.raises(error):
        await guarded.click(10, 20)
    assert computer.actions == []


async def test_budget_before_actions_and_no_observer():
    computer = Computer()
    completions = Completions(
        [reply(actions=[{"name": "left_click", "arguments": {"coordinates": [1, 1]}}])]
    )
    outputs = await collect(agent(computer, completions), context(limit=7))
    assert computer.actions == []
    assert outputs[-1].metadata["stop_reason"] == "budget"


async def test_missing_usage_stops():
    completions = Completions([reply(usage=False)])
    ctx = context()
    outputs = await collect(agent(Computer(), completions), ctx)
    assert outputs[-1].metadata["stop_reason"] == "budget"
    assert len(ctx.budget.unknown_calls) == 1


async def test_format_retry_is_counted_once_per_response():
    completions = Completions([reply(finish="length"), reply()])
    ctx = context()
    await collect(agent(Computer(), completions), ctx)
    assert ctx.budget.total_tokens == 14 and len(ctx.budget.call_ids) == 2


async def test_cancel_model_call_drains_producer_and_records_unknown():
    started = asyncio.Event()
    client = Completions([])

    async def blocked(**kwargs):
        started.set()
        await asyncio.Event().wait()

    client.create = blocked
    computer, ctx = Computer(), context()
    plugin = agent(computer, client)
    task = asyncio.create_task(collect(plugin, ctx))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await plugin.aclose()
    computer.aclose.assert_awaited_once()
    assert len(ctx.budget.unknown_calls) == 1


async def test_consumer_early_close_drains_producer():
    computer = Computer()
    client = Completions([reply()])
    plugin = agent(computer, client)
    outputs = plugin.run(SubAgentRequest("task", "", "id"), context())
    await anext(outputs)
    await outputs.aclose()
    await plugin.aclose()
    assert plugin.producer is None or plugin.producer.done()
    computer.aclose.assert_awaited_once()


async def test_batch_first_error_skips_remaining_action():
    computer = Computer()
    computer.fail_click = True
    actions = [{"name": "left_click", "arguments": {"coordinates": [10, 10]}}] * 2
    outputs = await collect(
        agent(computer, Completions([reply(actions=actions), reply()])), context()
    )
    assert len(computer.actions) == 1
    assert any(
        o.type == AgentOutputType.TOOL_RESULT and o.metadata["status"] == "error"
        for o in outputs
    )
    assert outputs[-1].metadata["primitives"] == 0


async def test_shell_output_cannot_inflate_gui_action_count():
    from agent_n2_sdk.callbacks import Callbacks

    queue = asyncio.Queue()
    callbacks = Callbacks(queue, context())
    await callbacks.on_computer_call_end(
        {"name": "bash", "call_id": "shell"},
        [{"output": "[0:left_click] arbitrary shell output"}],
    )
    assert callbacks.primitives == 0
    assert (await queue.get()).metadata["completed_primitives"] == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_steps": 0},
        {"reasoning_effort": "bad"},
        {"api_key": ""},
        {"environment": "remote"},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        N2SdkConfig.from_dict(kwargs)


async def test_sdk_max_steps_and_context_limit_are_incomplete():
    computer = Computer()
    actions = [{"name": "screenshot", "arguments": {}}]
    outputs = await collect(
        agent(computer, Completions([reply(actions=actions)]), max_steps=1), context()
    )
    assert outputs[-1].metadata["stop_reason"] == "max_steps"


async def test_tool_limit_checked_before_next_call():
    computer = Computer()
    actions = [{"name": "left_click", "arguments": {"coordinates": [20, 20]}}]
    ctx = context()
    from dataclasses import replace

    ctx = replace(ctx, max_steps=1)
    outputs = await collect(
        agent(computer, Completions([reply(actions=actions), reply(actions=actions)])),
        ctx,
    )
    assert (
        len(computer.actions) == 1
        and outputs[-1].metadata["stop_reason"] == "max_steps"
    )


async def test_click_modifiers_pass_through_sdk_in_pixels():
    computer = Computer()
    actions = [
        {
            "name": "left_click",
            "arguments": {"coordinates": [500, 500], "modifier": "shift"},
        }
    ]
    await collect(
        agent(computer, Completions([reply(actions=actions), reply()])), context()
    )
    assert computer.actions[0][:2] == (50, 50)
    assert computer.actions[0][2]["modifier"] == ["shift"]


async def test_timeout_initialization_closes_owned_environment():
    computer = Computer()

    async def blocked():
        await asyncio.Event().wait()

    computer.__aenter__ = AsyncMock(side_effect=blocked)
    plugin = agent(computer, Completions([]), timeout_s=0.02)
    with pytest.raises(TimeoutError):
        await collect(plugin, context())
    computer.aclose.assert_awaited_once()


async def test_platform_refusal_precedes_model_and_driver(monkeypatch):
    from agent_n2_sdk import environment

    monkeypatch.setattr(environment.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="macOS only"):
        environment.create_computer(context())


async def test_authorization_revoked_blocks_next_primitive():
    from tank_backend.agents.subagent import SubAgentStopped

    computer, ctx = Computer(), context()
    ctx.runtime.bind("task-id")
    guarded = GuardedComputer(computer, ctx)
    await guarded.click(1, 2)
    ctx.authorization.revoke()
    with pytest.raises(SubAgentStopped, match="authorization"):
        await guarded.click(3, 4)
    assert len(computer.actions) == 1


async def test_cleanup_failure_attempts_other_resources():
    from tank_backend.agents.subagent import SubAgentCleanupError

    computer, client = Computer(), Completions([reply()])
    computer.aclose.side_effect = RuntimeError("driver did not exit")
    plugin = agent(computer, client)
    # Shared cleanup identifies the failed resource instead of copying vendor error text.
    with pytest.raises(SubAgentCleanupError, match="computer"):
        await collect(plugin, context())
    client.aclose.assert_awaited_once()


async def test_repeated_close_preserves_cleanup_failure():
    from tank_backend.agents.subagent import SubAgentCleanupError

    computer, client = Computer(), Completions([reply()])
    computer.aclose.side_effect = RuntimeError("driver did not exit")
    plugin = agent(computer, client)
    with pytest.raises(SubAgentCleanupError):
        await collect(plugin, context())
    for _ in range(2):
        with pytest.raises(SubAgentCleanupError):
            await plugin.aclose()
    computer.aclose.assert_awaited_once()
    client.aclose.assert_awaited_once()


async def test_inherited_cleanup_stops_producer_before_sdk_and_clients(monkeypatch):
    from yutori.navigator.n2 import N2ComputerAgent

    order = []
    started = asyncio.Event()
    computer, client = Computer(), Completions([])

    async def blocked(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            order.append("producer_stopped")

    async def close_computer():
        order.append("computer")

    async def close_client():
        order.append("client")

    original_close = N2ComputerAgent.aclose

    async def close_sdk(sdk):
        order.append("sdk")
        await original_close(sdk)

    monkeypatch.setattr(N2ComputerAgent, "aclose", close_sdk)
    client.create = blocked
    computer.aclose.side_effect = close_computer
    client.aclose.side_effect = close_client
    plugin = agent(computer, client)
    running = asyncio.create_task(collect(plugin, context()))
    await asyncio.wait_for(started.wait(), 1)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    await plugin.aclose()
    assert order == ["producer_stopped", "sdk", "computer", "client"]


async def test_run_leaves_owned_resource_shutdown_to_the_host():
    computer, client = Computer(), Completions([reply()])
    plugin = agent(computer, client)
    try:
        outputs = [
            item async for item in plugin.run(
                SubAgentRequest("task", "", "task-id"), context(),
            )
        ]
        assert outputs[-1].metadata["stop_reason"] == "final_answer"
        assert not plugin.closed
        computer.aclose.assert_not_awaited()
        client.aclose.assert_not_awaited()
    finally:
        await plugin.aclose()
    computer.aclose.assert_awaited_once()
    client.aclose.assert_awaited_once()


async def test_compaction_and_actor_share_unique_ledger():
    from agent_n2_sdk.callbacks import MeteredCompletions
    from yutori.navigator.n2 import N2ComputerAgent

    class Compactor:
        async def compact(self, items, *, completions, **kwargs):
            await completions.create(messages=items, model="n2")
            return None

    ctx = context()
    queue = asyncio.Queue()
    ctx.runtime.bind("compaction")
    client = governed_client(Completions([reply(), reply()]), N2SdkConfig(api_key="test"), ctx)
    metered = MeteredCompletions(client, ctx, queue)
    sdk = N2ComputerAgent(
        computer=Computer(), completions=metered, compactor=Compactor()
    )
    _ = [frame async for frame in sdk.run("task")]
    assert ctx.budget.total_tokens == 14 and len(ctx.budget.call_ids) == 2
    assert queue.qsize() == 2
    await client.aclose()


async def test_backpressure_consumer_close_does_not_leave_sdk_loop():
    computer = Computer()
    actions = [{"name": "left_click", "arguments": {"coordinates": [20, 20]}}]
    response = reply(actions=actions)
    response["choices"][0]["message"]["tool_calls"] *= 80
    plugin = agent(computer, Completions([response]))
    outputs = plugin.run(SubAgentRequest("task", "", "id"), context(limit=1000))
    await anext(outputs)
    await outputs.aclose()
    await plugin.aclose()
    assert plugin.producer is not None
    assert plugin.producer.done() and computer.aclose.await_count == 1


@pytest.mark.parametrize("action", ["drag", "hold_key", "bash"])
async def test_cancel_during_environment_action_drains_producer(action):
    computer, started = Computer(), asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    if action == "bash":
        computer.run_bash_command = blocked
        response = reply()
        response["choices"][0]["message"]["tool_calls"] = [
            {
                "id": "bash",
                "type": "function",
                "function": {"name": "bash", "arguments": '{"command":"fake command"}'},
            }
        ]
    elif action == "drag":
        computer.drag = blocked
        response = reply(
            actions=[
                {
                    "name": "drag",
                    "arguments": {
                        "start_coordinates": [100, 100],
                        "coordinates": [200, 200],
                    },
                }
            ]
        )
    else:
        computer.hold_key = blocked
        response = reply(
            actions=[{"name": "hold_key", "arguments": {"key": "shift", "duration": 1}}]
        )
    plugin = agent(computer, Completions([response]))
    task = asyncio.create_task(collect(plugin, context()))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert plugin.producer is not None
    assert plugin.producer.done()
    computer.aclose.assert_awaited_once()


@pytest.mark.parametrize("request_allowance", [None, 0, 2])
async def test_benchmark_create_and_observer_use_sdk_without_executor(
    tmp_path, monkeypatch, request_allowance,
):
    from pathlib import Path
    import yaml
    import agent_n2_sdk
    from tank_backend.benchmarks.driver import SubAgentDriver
    from tank_backend.benchmarks.trace import TraceSink
    from tank_backend.benchmarks.request_budget import RequestLimits

    computer = Computer()
    actions = [{"name": "left_click", "arguments": {"coordinates": [500, 500]}}]
    client = Completions([reply(actions=actions), reply()])
    plugin = agent(computer, client)
    monkeypatch.setattr(agent_n2_sdk, "create_subagent", lambda cfg: plugin)
    config = tmp_path / "config.yaml"
    agents_dir = Path(__file__).resolve().parents[3] / "agents"
    config.write_text(
        yaml.safe_dump(
            {
                "llm": {
                    "default": {
                        "api_key": "fake",
                        "model": "fake",
                        "base_url": "https://example.com",
                    }
                },
                "agents": {"dirs": [str(agents_dir)]},
                "skills": {"enabled": False, "dirs": []},
                "subagents": {
                    "agent-n2-sdk:agent": {
                        "config": {"api_key": "secret-do-not-report", "model": "n2"}
                    }
                },
            }
        )
    )
    driver = SubAgentDriver.create(
        "n2_sdk", config, request_limits=(
            RequestLimits(request_allowance, 0, request_allowance)
            if request_allowance is not None else None
        ),
    )
    trace = TraceSink(tmp_path / "trial")
    result = await driver.run("task", trace, timeout_s=10, max_steps=10)
    trace.close()
    events = [json.loads(line) for line in (tmp_path / "trial/trace.jsonl").read_text().splitlines()]
    captured = [event for event in events if event["kind"] == "http_request"]
    if request_allowance == 0:
        assert result.stop_reason == "request_limit"
        assert client.calls == [] and result.tokens == 0 and captured == []
        return
    assert len(captured) == 2
    assert result.stop_reason == "final_answer" and result.cleanup == "confirmed"
    assert result.tokens == 14 and result.llm_calls == 2 and result.screenshots == 1
    assert result.llm_ttft_s is None and result.llm_rtt_s > 0
    assert result.primitives == 1 and result.model_turns == 2
    assert "secret-do-not-report" not in json.dumps(driver.describe())
    assert driver.describe()["display"] == {"width": 100, "height": 100}


async def test_sdk_keeps_the_original_task_runtime_when_applying_its_timeout():
    ctx = context()
    ctx.runtime.bind("task-id")
    plugin = agent(Computer(), Completions([reply()]), timeout_s=1)
    await collect(plugin, ctx)
    assert plugin.computer.context is ctx
    assert plugin.computer.context.runtime is ctx.runtime


async def test_sdk_native_calls_use_original_runtime_audit():
    records = []

    async def audit(record):
        records.append(record)

    from dataclasses import replace

    ctx = replace(context(), audit=audit)
    ctx.runtime.bind("task-id")
    computer = Computer()
    guarded = GuardedComputer(computer, ctx)
    await guarded.click(1, 2)
    assert [record.status for record in records] == ["not_sent", "unknown", "returned"]
    assert all(record.task_id == "task-id" for record in records)
    assert computer.actions == [(1, 2, {"button": "left", "modifier": None})]


async def test_zero_task_model_allowance_sends_no_sdk_http():
    from dataclasses import replace

    class Denied:
        blocked = False

        def check(self):
            if self.blocked:
                raise SubAgentStopped("budget")

        def reserve(self, call_id, request):
            self.blocked = True
            raise SubAgentStopped("budget")

        def settle(self, call_id, inputs, outputs):
            pytest.fail("no HTTP was sent")

        def release_unsent(self, call_id):
            pass

    client = Completions([])
    ctx = replace(context(), model_policy=Denied())
    outputs = await collect(agent(Computer(), client), ctx)
    assert outputs[-1].metadata["stop_reason"] == "budget"
    assert client.calls == [] and ctx.budget.call_count == 0


async def test_file_write_rechecks_revocation_at_the_sdk_native_boundary(tmp_path):
    from agent_n2_sdk.environment import create_task_computer

    ctx = context()
    computer = create_task_computer(
        ctx, transport=AsyncMock(), owns_transport=True, allow_local_shell=True,
    )
    target = tmp_path / "blocked"
    ctx.authorization.revoke()
    with pytest.raises(SubAgentStopped, match="authorization"):
        await computer.write_file(str(target), "must not be written")
    assert not target.exists()
    await computer.aclose()


async def test_stopped_sdk_cleanup_does_not_complete_an_emulated_click():
    from agent_n2_sdk.environment import create_task_computer

    ctx = context()
    computer = create_task_computer(
        ctx, transport=AsyncMock(), owns_transport=True, allow_local_shell=True,
    )
    computer.click = AsyncMock()
    await computer.left_mouse_down(10, 20)
    ctx.authorization.revoke()
    await computer.release_held_mouse_button()
    computer.click.assert_not_awaited()
    await computer.aclose()


async def test_concurrent_completion_events_keep_their_own_core_call_ids():
    from dataclasses import replace

    from agent_n2_sdk.callbacks import MeteredCompletions

    entered, respond, auditing, finish_audit = (asyncio.Event() for _ in range(4))
    count = 0

    async def audit(record):
        if record.phase == "finished" and not auditing.is_set():
            auditing.set()
            await finish_audit.wait()

    client = Completions([])

    async def create(**kwargs):
        nonlocal count
        count += 1
        if count == 2:
            entered.set()
        await respond.wait()
        return reply()

    client.create = create
    ctx = replace(context(), audit=audit)
    ctx.runtime.bind("parallel")
    governed = governed_client(client, N2SdkConfig(api_key="test"), ctx)
    queue = asyncio.Queue()
    metered = MeteredCompletions(governed, ctx, queue)
    requests = [asyncio.create_task(metered.create(messages=[{"role": "user", "content": "go"}]))
                for _ in range(2)]
    await entered.wait()
    respond.set()
    await auditing.wait()
    await asyncio.sleep(0)
    finish_audit.set()
    try:
        await asyncio.gather(*requests)
        events = [queue.get_nowait() for _ in range(2)]
        assert len({event.metadata["call_id"] for event in events}) == 2
        assert {event.metadata["call_id"] for event in events} == ctx.budget.call_ids
    finally:
        await governed.aclose()
