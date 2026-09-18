from __future__ import annotations

import asyncio
import copy
import io
from types import SimpleNamespace
from typing import AsyncGenerator, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types.chat import ChatCompletionMessage
from PIL import Image

from agent_n2 import create_agent
from agent_n2.agent import N2Agent
from agent_n2.protocol import TOOL_SET, key_name
from tank_backend.agents.base import AgentOutput, AgentOutputType, AgentState
from tank_backend.computer.executor import BatchResult, BatchStep, DesktopExecutor, Screenshot
from tank_backend.llm.profile import LLMProfile


@pytest.fixture
def executor():
    ex = MagicMock(spec=DesktopExecutor)
    buffer = io.BytesIO()
    Image.new("RGB", (20, 10)).save(buffer, "PNG")
    ex.screenshot = AsyncMock(return_value=Screenshot(buffer.getvalue(), 20, 10))
    ex.batch = AsyncMock(return_value=BatchResult((BatchStep("click", True),), None, (), None))
    return ex


@pytest.fixture
def profile():
    return LLMProfile("n2", "test", "n2", "https://api.yutori.com/v1")


def completion(calls=(), content=None):
    message = ChatCompletionMessage.model_validate({
        "role": "assistant", "content": content,
        "reasoning_content": "unchanged reasoning", "tool_calls": list(calls) or None,
    })
    return SimpleNamespace(choices=[SimpleNamespace(message=message)],
                           usage=SimpleNamespace(total_tokens=20, prompt_tokens=12,
                                                 completion_tokens=8))


def call(name, arguments, ident="c1"):
    import json

    return {"id": ident, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}


async def test_loop_history_usage_and_multiple_results(executor, profile):
    responses = iter([
        completion([call("computer_batch", {"actions": [
            {"name": "left_click", "arguments": {"coordinates": [412, 380]}}
        ]}), call("write", {"file_path": "a", "content": "hello"}, "c2")]),
        completion(content="Done"),
    ])
    requests = []

    async def request(**kwargs):
        requests.append(copy.deepcopy(kwargs))
        return next(responses)

    client = MagicMock()
    client.chat.completions.create = request
    agent = N2Agent(executor, profile, client=client)
    outputs = [o async for o in agent.run(AgentState(messages=[{"role": "user", "content": "task"}]))]
    assert sum(o.type == AgentOutputType.USAGE for o in outputs) == 2
    assert outputs[-1].type == AgentOutputType.DONE
    assert "max_tokens" not in requests[0] and "temperature" not in requests[0]
    assert requests[0]["extra_body"]["tool_set"] == TOOL_SET
    history = requests[1]["messages"]
    assert history[1]["reasoning_content"] == "unchanged reasoning"
    assert [m["tool_call_id"] for m in history if m["role"] == "tool"] == ["c1", "c2"]
    assert history[2]["content"][1]["image_url"]["url"].startswith("data:image/webp;")
    assert len(requests[0]["messages"]) == 1
    executor.batch.assert_awaited_once_with(
        [{"action": "click", "x": 412, "y": 380, "button": "left", "clicks": 1}],
        screenshot_after=False,
    )


async def test_batch_fail_fast_single_screenshot(executor, profile):
    executor.batch.return_value = BatchResult((BatchStep("click", False, "denied"),), 0, (), None)
    text, png = await N2Agent(executor, profile)._batch([
        {"name": "left_click", "arguments": {"coordinates": [1, 2]}},
        {"name": "type", "arguments": {"text": "must not execute"}},
    ])
    assert "Action 0 failed: denied; skipped 1" in text
    assert png
    executor.batch.assert_awaited_once()
    executor.screenshot.assert_awaited_once()


async def test_modifier_release_and_mouse_cleanup_on_cancel(executor, profile):
    executor.batch.side_effect = asyncio.CancelledError
    agent = N2Agent(executor, profile)
    with pytest.raises(asyncio.CancelledError):
        await agent._batch([
            {"name": "mouse_down", "arguments": {}},
            {"name": "left_click", "arguments": {"coordinates": [1, 2], "modifier": "command"}},
        ])
    executor.key_down.assert_awaited_once_with("cmd")
    executor.key_up.assert_awaited_once_with("cmd")
    executor.mouse_up.assert_awaited_once()


async def test_left_mouse_aliases_preserve_drag_and_cleanup(executor, profile):
    text, png = await N2Agent(executor, profile)._batch([
        {"name": "left_mouse_down", "arguments": {"coordinates": [100, 200]}},
        {"name": "mouse_move", "arguments": {"coordinates": [300, 400]}},
        {"name": "left_mouse_up", "arguments": {}},
    ])
    assert text == "Executed 3 of 3 actions." and png
    executor.mouse_move.assert_awaited_once_with(100, 200)
    executor.mouse_down.assert_awaited_once()
    executor.mouse_up.assert_awaited_once()


async def test_left_mouse_alias_released_on_cancel(executor, profile):
    executor.batch.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await N2Agent(executor, profile)._batch([
            {"name": "left_mouse_down", "arguments": {}},
            {"name": "mouse_move", "arguments": {"coordinates": [300, 400]}},
        ])
    executor.mouse_up.assert_awaited_once()


async def test_file_read_before_edit_and_numbering(executor, profile):
    agent = N2Agent(executor, profile)
    with pytest.raises(ValueError, match="before editing"):
        await agent.execute("edit", {"file_path": "a", "old_string": "x", "new_string": "y"})
    executor.read_file.return_value = "first\nsecond\nthird"
    text, _ = await agent.execute("read", {"file_path": "a", "offset": 2, "limit": 1})
    assert text == "     2\tsecond"
    await agent.execute("edit", {"file_path": "a", "old_string": "second", "new_string": "next"})
    executor.edit_file.assert_awaited_once_with("a", "second", "next")


@pytest.mark.parametrize(("name", "args", "expected"), [
    ("double_click", {"coordinates": [1, 2]}, {"action": "click", "x": 1, "y": 2, "button": "left", "clicks": 2}),
    ("triple_click", {"coordinates": [1, 2]}, {"action": "click", "x": 1, "y": 2, "button": "left", "clicks": 3}),
    ("right_click", {"coordinates": [1, 2]}, {"action": "click", "x": 1, "y": 2, "button": "right", "clicks": 1}),
    ("middle_click", {"coordinates": [1, 2]}, {"action": "click", "x": 1, "y": 2, "button": "middle", "clicks": 1}),
    ("mouse_move", {"coordinates": [1, 2]}, {"action": "mouse_move", "x": 1, "y": 2}),
    ("drag", {"start_coordinates": [1, 2], "coordinates": [3, 4]}, {"action": "drag", "x1": 1, "y1": 2, "x2": 3, "y2": 4}),
    ("scroll", {"coordinates": [1, 2], "direction": "down", "amount": 5}, {"action": "scroll", "x": 1, "y": 2, "amount": -5}),
    ("type", {"text": "张三"}, {"action": "type_text", "text": "张三"}),
    ("wait", {"duration": 2}, {"action": "wait", "delay_s": 2}),
    ("hold_key", {"key": "command", "duration": 2}, {"action": "hold_key", "keys": "cmd", "duration_s": 2}),
])
def test_action_mapping(name, args, expected):
    assert N2Agent._action(name, args) == expected


async def test_sequence_keys_and_screenshot_noop(executor, profile):
    await N2Agent(executor, profile)._batch([
        {"name": "key_press", "arguments": {"key": "super+a down esc"}},
        {"name": "screenshot", "arguments": {}},
    ])
    assert [c.args[0] for c in executor.key_press.await_args_list] == ["cmd+a", "down", "escape"]
    executor.screenshot.assert_awaited_once()
    assert key_name("ctrl+plus") == "ctrl+shift+="


def test_factory_validation(executor, profile):
    with pytest.raises(ValueError, match="desktop_executor"):
        create_agent({"llm_profile": profile})
    with pytest.raises(ValueError, match="llm_profile"):
        create_agent({"desktop_executor": executor})
    with pytest.raises(ValueError, match="max_steps"):
        create_agent({"desktop_executor": executor, "llm_profile": profile, "max_steps": 0})


def test_rejects_default_text_model_before_desktop_or_api(executor):
    profile = LLMProfile("default", "test", "deepseek-flash", "https://api.deepseek.com")
    with pytest.raises(ValueError, match="model.*n2"):
        N2Agent(executor, profile)
    with pytest.raises(ValueError, match="model.*n2"):
        create_agent({"desktop_executor": executor, "llm_profile": profile})
    executor.screenshot.assert_not_awaited()


async def test_usage_boundary_closes_client_without_actions(executor, profile, monkeypatch):
    client = MagicMock()
    client.close = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=completion([
        call("write", {"file_path": "a", "content": "x"})
    ]))
    monkeypatch.setattr("agent_n2.agent.AsyncOpenAI", lambda **kw: client)
    stream = cast(AsyncGenerator[AgentOutput, None], N2Agent(executor, profile).run(AgentState()))
    assert (await anext(stream)).type == AgentOutputType.USAGE
    await stream.aclose()
    client.close.assert_awaited_once()
    executor.write_file.assert_not_awaited()


async def test_step_limit(executor, profile):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion([
        call("computer_batch", {"actions": [{"name": "screenshot", "arguments": {}}]})
    ]))
    outputs = [o async for o in N2Agent(executor, profile, client=client, max_steps=1).run(AgentState())]
    assert "max_steps" in outputs[-2].content
    assert client.chat.completions.create.await_count == 1


async def test_real_factory_runner_dispatch_and_budget(executor, profile, monkeypatch):
    from pathlib import Path

    from tank_backend.agents.agent_tool import AgentTool
    from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
    from tank_backend.agents.definition import parse_agent_file
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.plugin.manifest import read_manifest_from_yaml
    from tank_backend.plugin.registry import ExtensionRegistry

    plugin = Path(__file__).parents[1]
    definition = parse_agent_file(plugin.parents[1] / "agents/n2.md")
    registry = ExtensionRegistry()
    manifest = read_manifest_from_yaml(plugin / "plugin.yaml")
    registry.register(manifest.plugin_name, manifest.extensions[0])
    app_config = MagicMock()
    app_config.get_section.return_value = {"agent-n2:agent": {"llm_profile": "n2", "max_steps": 2}}
    app_config.llm_profiles = {"n2": profile}
    client = MagicMock()
    client.close = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=completion([
        call("write", {"file_path": "a", "content": "x"})
    ]))
    monkeypatch.setattr("agent_n2.agent.AsyncOpenAI", lambda **kw: client)
    monkeypatch.setattr("tank_backend.computer.executor.create_desktop_executor", lambda: executor)
    runner = AgentRunner(llm=MagicMock(), tool_manager=MagicMock(), bus=MagicMock(),
                         app_config=app_config, registry=registry,
                         approval_policy=ToolApprovalPolicy(computer_mode="require"),
                         pending_store=PendingToolCallStore(),
                         definitions={definition.name: definition})
    # Dispatch approval is reached before constructing the remote client.
    result = await AgentTool(runner).execute(prompt="task", subagent_type=definition.name)
    assert str(result.content).startswith("APPROVAL REQUIRED")
    client.chat.completions.create.assert_not_awaited()
    # Runner consumes usage and closes the engine before executing an over-budget action.
    outputs = [o async for o in runner.run_agent(
        definition, [{"role": "user", "content": "task"}], token_budget=10,
    )]
    assert any("token budget" in o.content for o in outputs)
    executor.write_file.assert_not_awaited()
    client.close.assert_awaited_once()


async def test_benchmark_engine_records_usage_and_screenshots(executor, profile, tmp_path, monkeypatch):
    from tank_backend.benchmarks.driver import CountingLLM, _MeasuredEngine, _MeasuredRegistry
    from tank_backend.benchmarks.trace import TraceSink
    from tank_backend.plugin.manifest import ExtensionManifest

    trace = TraceSink(tmp_path)
    llm = CountingLLM(MagicMock())
    registry = _MeasuredRegistry(llm, lambda: trace)
    registry.register("agent-n2", ExtensionManifest(
        name="agent", type="agent", factory="agent_n2:create_agent", needs=("desktop_executor",),
    ))
    client = MagicMock()
    client.close = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=completion(content="Done"))
    monkeypatch.setattr("agent_n2.agent.AsyncOpenAI", lambda **kw: client)
    engine = registry.instantiate("agent-n2:agent", {"desktop_executor": executor, "llm_profile": profile})
    assert isinstance(engine, _MeasuredEngine)
    try:
        outputs = [o async for o in engine.run(AgentState())]
        assert outputs[-1].type == AgentOutputType.DONE
        assert llm.total_tokens == 20
        assert len(llm.call_stats) == 1
        assert trace.screenshot_count == 1
        assert (tmp_path / "screenshots/shot_001.png").exists()
    finally:
        trace.close()


async def test_missing_n2_profile_fails_without_using_default(executor, monkeypatch):
    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.agents.runner import AgentRunner
    from tank_backend.config.app_config import AppConfig
    from tank_backend.plugin.manifest import ExtensionManifest
    from tank_backend.plugin.registry import ExtensionRegistry

    registry = ExtensionRegistry()
    registry.register("agent-n2", ExtensionManifest(
        name="agent", type="agent", factory="agent_n2:create_agent", needs=("desktop_executor",),
    ))
    app_config = AppConfig(llm_profiles={
        "default": LLMProfile("default", "test", "deepseek-flash", "https://api.deepseek.com"),
    })
    client_factory = MagicMock()
    monkeypatch.setattr("agent_n2.agent.AsyncOpenAI", client_factory)
    monkeypatch.setattr("tank_backend.computer.executor.create_desktop_executor", lambda: executor)
    runner = AgentRunner(
        llm=MagicMock(), tool_manager=MagicMock(), bus=MagicMock(),
        app_config=app_config, registry=registry, approval_policy=MagicMock(),
        pending_store=MagicMock(), definitions={},
    )
    definition = AgentDefinition(name="n2", description="", system_prompt="", engine="agent-n2:agent")
    with pytest.raises(ValueError, match="llm_profile"):
        _ = [o async for o in runner.run_agent(definition, [{"role": "user", "content": "task"}])]
    client_factory.assert_not_called()
    executor.screenshot.assert_not_awaited()
    assert not any(t.active for t in runner._active_agents.values())
