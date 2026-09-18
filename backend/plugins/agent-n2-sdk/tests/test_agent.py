"""Real pinned SDK + fake computer/completions; no paid calls or desktop input."""

import asyncio
import base64
import io
import inspect
import json
from unittest.mock import AsyncMock
from typing import Any

import pytest
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


def agent(computer, completions, **config):
    return N2SdkSubAgent(
        N2SdkConfig(api_key="test", screenshot_delay=0, **config),
        computer_factory=lambda ctx: GuardedComputer(computer, ctx),
        client_factory=lambda cfg: completions,
    )


async def collect(plugin, ctx):
    return [
        o async for o in plugin.run(SubAgentRequest("task", "context", "task-id"), ctx)
    ]


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
    with pytest.raises(SubAgentCleanupError, match="driver did not exit"):
        await collect(plugin, context())
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
    metered = MeteredCompletions(Completions([reply(), reply()]), ctx, queue)
    sdk = N2ComputerAgent(
        computer=Computer(), completions=metered, compactor=Compactor()
    )
    _ = [frame async for frame in sdk.run("task")]
    assert ctx.budget.total_tokens == 14 and len(ctx.budget.call_ids) == 2
    assert queue.qsize() == 2


async def test_backpressure_consumer_close_does_not_leave_sdk_loop():
    computer = Computer()
    actions = [{"name": "left_click", "arguments": {"coordinates": [20, 20]}}]
    response = reply(actions=actions)
    response["choices"][0]["message"]["tool_calls"] *= 80
    plugin = agent(computer, Completions([response]))
    outputs = plugin.run(SubAgentRequest("task", "", "id"), context(limit=1000))
    await anext(outputs)
    await outputs.aclose()
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


async def test_benchmark_create_and_observer_use_sdk_without_executor(
    tmp_path, monkeypatch
):
    from pathlib import Path
    import yaml
    import agent_n2_sdk
    from tank_backend.benchmarks.driver import SubAgentDriver
    from tank_backend.benchmarks.trace import TraceSink

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
    driver = SubAgentDriver.create("n2_sdk", config)
    trace = TraceSink(tmp_path / "trial")
    result = await driver.run("task", trace, timeout_s=10, max_steps=10)
    trace.close()
    assert result.stop_reason == "final_answer" and result.cleanup == "confirmed"
    assert result.tokens == 14 and result.llm_calls == 2 and result.screenshots == 1
    assert result.llm_ttft_s == 0 and result.llm_rtt_s > 0
    assert "secret-do-not-report" not in json.dumps(driver.describe())
    assert driver.describe()["display"] == {"width": 100, "height": 100}
