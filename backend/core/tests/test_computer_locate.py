"""Split planner/locator integration; only HTTP and macOS boundaries are fake."""

import base64
import hashlib
import io
import json
import sys
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from openai import AsyncOpenAI
from PIL import Image

from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
from tank_backend.agents.base import AgentOutputType
from tank_backend.agents.definition import AgentDefinition
from tank_backend.agents.runner import AgentRunner
from tank_backend.llm import llm as llm_module
from tank_backend.pipeline.bus import Bus
from tank_backend.tools import computer_use_macos as macos
from tank_backend.tools.groups import ComputerUseToolGroup
from tank_backend.tools.manager import ToolManager


@pytest.fixture
def desktop(monkeypatch):
    quartz = MagicMock()
    quartz.CGMainDisplayID.return_value = 5
    quartz.CGDisplayBounds.return_value = ((0, 0), (100, 80))
    quartz.CGDisplayModeGetPixelWidth.return_value = 200
    quartz.CGDisplayModeGetPixelHeight.return_value = 160
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    monkeypatch.setattr(macos, "_load_quartz", lambda: quartz)
    image = io.BytesIO()
    Image.new("RGB", (100, 80), "red").save(image, "PNG")
    png = image.getvalue()
    monkeypatch.setattr(macos, "_capture_screenshot_macos", lambda **kw: png)
    click = MagicMock()
    monkeypatch.setattr(macos, "_click_macos", click)
    manager = ToolManager.__new__(ToolManager)
    manager.tools = {t.get_info().name: t for t in ComputerUseToolGroup()._create_macos_tools()}
    manager.tool_metadata = {n: t.get_metadata() for n, t in manager.tools.items()}
    manager._media_store = manager._bus = None
    manager.set_session_id("parent-session")
    return manager, click, png


def stream(
    name: str | None, arguments: dict[str, Any] | str, *, finish: str | None = None,
) -> httpx.Response:
    delta = (
        {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call",
                    "type": "function",
                    "function": {"name": name, "arguments": (arguments if isinstance(arguments, str)
                                                            else json.dumps(arguments))},
                }
            ]
        }
        if name
        else {"content": "done"}
    )
    chunk = {
        "id": "planner",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "test",
        "choices": [
            {"index": 0, "delta": delta,
             "finish_reason": finish or ("tool_calls" if name else "stop")}
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n",
    )


@pytest.mark.parametrize("benchmark", [False, True])
@pytest.mark.parametrize("separate_profile", [False, True])
@pytest.mark.parametrize("budget", [100, 5, 15, 20])
async def test_runner_split_locates_current_image_and_dispatches_reference(
    desktop, monkeypatch, budget, separate_profile, benchmark, tmp_path
):
    from types import SimpleNamespace

    from tank_backend.agents.definition import GroundingConfig
    from tank_backend.llm.profile import LLMProfile

    manager, click, png = desktop
    requests = []
    planner_turn = 0
    ledger = []

    class Observer:
        def on_event(self, kind, metadata):
            if kind == "grounding_usage":
                ledger.append(metadata)

    def respond(request):
        nonlocal planner_turn
        body = json.loads(request.content)
        requests.append(body)
        if not body.get("stream"):
            assert body["model"] == ("locator-model" if separate_profile else "test")
            assert len(body["messages"]) == 2
            assert "private task history" not in json.dumps(body)
            image = body["messages"][1]["content"][1]["image_url"]["url"]
            assert (
                hashlib.sha256(base64.b64decode(image.split(",")[1])).digest()
                == hashlib.sha256(png).digest()
            )
            assert [t["function"]["name"] for t in body["tools"]] == ["click"]
            return httpx.Response(
                200,
                json={
                    "id": "grounder",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "test",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "g",
                                        "type": "function",
                                        "function": {
                                            "name": "click",
                                            "arguments": json.dumps(
                                                {"status": "found", "x": 500, "y": 500}
                                            ),
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
                },
            )
        assert "Use the GUI." in body["messages"][0]["content"]
        planner_turn += 1
        schemas = {t["function"]["name"]: t["function"]["parameters"] for t in body["tools"]}
        assert "locate" in schemas
        assert "x" not in schemas["click"]["properties"]
        if planner_turn == 1:
            return stream("screenshot", {})
        if planner_turn == 2:
            text = next(
                p["text"]
                for m in body["messages"]
                if isinstance(m.get("content"), list)
                for p in m["content"]
                if p["type"] == "text" and "frame_id" in p["text"]
            )
            frame = json.loads(text[text.index("{") :])["frame_id"]
            return stream("locate", {"frame_id": frame, "target": "red center"})
        if planner_turn == 3:
            result = json.loads(
                next(m["content"] for m in body["messages"] if m.get("name") == "locate")
            )
            assert result["status"] == "found" and "point" not in result
            return stream("click", {"location_id": result["location_id"]})
        assert "dispatched" in json.dumps(body["messages"])
        return stream(None, {})

    client = AsyncOpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(llm_module, "AsyncOpenAI", lambda **kw: client)
    monkeypatch.setattr(llm_module, "initialize_langfuse", lambda: None)
    llm = llm_module.LLM(api_key="test", model="test", base_url="https://offline.invalid/v1")
    definition = AgentDefinition(
        "split",
        "",
        "Use the GUI.",
        tool_filter=("screenshot", "click"),
        grounding=GroundingConfig(profile="locator" if separate_profile else None),
    )
    runner = AgentRunner(
        llm,
        manager,
        Bus(),
        ToolApprovalPolicy(computer_mode="allow"),
        PendingToolCallStore(),
        {"split": definition},
        app_config=SimpleNamespace(
            llm_profiles={
                "locator": LLMProfile(
                    "locator",
                    "test",
                    "locator-model",
                    "https://offline.invalid/v1",
                )
            }
        ),
    )
    try:
        if benchmark:
            from dataclasses import replace

            from tank_backend.benchmarks import driver as driver_module
            from tank_backend.benchmarks.trace import TraceSink

            profiles = {
                "planner": LLMProfile("planner", "test", "test", "https://offline.invalid/v1"),
                "locator": LLMProfile("locator", "test", "locator-model",
                                      "https://offline.invalid/v1"),
            }
            app_config = SimpleNamespace(
                agents=SimpleNamespace(dirs=[], llm_profile="planner"),
                llm_profiles=profiles, get_llm_profile=profiles.__getitem__, toolsets=None,
            )
            monkeypatch.setattr(driver_module.AppConfig, "load", lambda _: app_config)
            monkeypatch.setattr(driver_module, "load_agent_definitions",
                                lambda _: {"split": definition})
            manager._approval_policy = ToolApprovalPolicy(computer_mode="allow")
            monkeypatch.setattr(driver_module, "ToolManager", lambda *a, **kw: manager)
            definition = replace(definition, model="planner", token_budget=budget)
            driver = driver_module.SubAgentDriver.create("split", tmp_path / "config.yaml")
            trace = TraceSink(tmp_path / "trial")
            result = await driver.run("private task history: click red center", trace,
                                      timeout_s=5, max_steps=10)
            trace.close()
            records = [json.loads(line) for line in
                       (tmp_path / "trial/trace.jsonl").read_text().splitlines()]
            outputs = [SimpleNamespace(type=AgentOutputType.DONE)] if not result.error else []
            if budget == 100:
                assert result.error is None, result.error
                assert result.tokens == 30
                assert result.llm_calls == 5
                assert result.non_gui_tools == ()
                assert result.screenshots == 2
                assert len([r for r in records if r["kind"] == "http_request"]) == 5
                responses = [r for r in records if r["kind"] == "http_response"]
                assert len(responses) == 5
                assert all(r["body_state"] == "complete" for r in responses)
                assert {r["request_id"] for r in responses} == {
                    r["request_id"] for r in records if r["kind"] == "http_request"}
                bodies = [(tmp_path / "trial" / r["file"]).read_bytes() for r in responses]
                assert [json.loads(body)["object"] for body in bodies
                        if body.startswith(b"{")] == ["chat.completion"]
                outcomes = [r for r in records if r["kind"] == "grounding_outcome"]
                assert len(outcomes) == 1 and outcomes[0]["outcome"] == "found"
                call_id = outcomes[0]["call_id"]
                requests_for_locate = [r for r in records if r["kind"] == "http_request"
                                       and r.get("grounding_call_id") == call_id]
                assert len(requests_for_locate) == 1
                assert len([r for r in records if r["kind"] == "http_request"
                            and r.get("grounding_call_id") is not None]) == 1
                assert len([r for r in records if r["kind"] == "grounding_usage"
                            and r["call_id"] == call_id]) == 1
                assert outcomes[0]["point"] == [50.0, 40.0]
                assert driver.describe()["grounding"]["protocol"] == "point"
                ledger.extend(r for r in records if r["kind"] == "grounding_usage")
        else:
            outputs = [
                o
                async for o in runner.run_agent(
                    definition,
                    [{"role": "user", "content": "private task history: click red center"}],
                    token_budget=budget,
                    observer=Observer(),
                )
            ]
    finally:
        await client.close()
    if budget < 100:
        assert not any(o.type == AgentOutputType.DONE for o in outputs)
        click.assert_not_called()
        assert len(requests) == (1 if budget == 5 else 3)
        return
    assert any(o.type == AgentOutputType.DONE for o in outputs)
    click.assert_called_once_with(50, 40, "left", 1)
    assert len(requests) == 5
    assert ledger[0]["total_tokens"] == 20  # two planner calls + one locate
    assert manager._session_id == "parent-session"
    assert "locate" not in manager.tools


@pytest.fixture
async def locator(desktop, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
    from tank_backend.tools.computer_grounding import GroundingAdapter
    from tank_backend.tools.computer_locate import LocateSession, LocateTool

    manager, click, png = desktop
    control = SimpleNamespace(
        status="found", raw=None, usage=True, finish="tool_calls", requests=[], during=None,
        events=[],
        refusal=None, tool_name="click", choices_count=1,
    )

    async def respond(request):
        control.requests.append(json.loads(request.content))
        if control.during is not None:
            await control.during()
        arguments = control.raw or json.dumps(
            {
                "status": control.status,
                "x": 500 if control.status == "found" else 0,
                "y": 500 if control.status == "found" else 0,
            }
        )
        body = {
            "id": "same-provider-id",
            "object": "chat.completion",
            "created": 1,
            "model": "grounding-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": control.finish,
                    "message": {
                        "role": "assistant",
                        "refusal": control.refusal,
                        "tool_calls": [
                            {
                                "id": "g",
                                "type": "function",
                                "function": {"name": control.tool_name, "arguments": arguments},
                            }
                        ],
                    },
                }
            ],
        }
        body["choices"] *= control.choices_count
        if control.usage:
            body["usage"] = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
        return httpx.Response(200, json=body)

    client = AsyncOpenAI(
        api_key="test",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(llm_module, "AsyncOpenAI", lambda **kw: client)
    monkeypatch.setattr(llm_module, "initialize_langfuse", lambda: None)
    llm = llm_module.LLM(api_key="test", model="test", base_url="https://offline.invalid/v1")
    class Observer:
        def on_event(self, kind, metadata):
            control.events.append((kind, metadata))

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop"})), SubAgentBudget(limit=100), asyncio.Event(),
        observer=Observer(),
    )
    session = LocateSession(
        manager.tools,
        {"primary": llm, "fallback": llm},
        GroundingAdapter(status_field=True),
        context,
        "locate-test",
    )
    manager.tools = {name: LocateTool(session, name) for name in session.tools}
    manager.tools["locate"] = LocateTool(session, "locate")
    control.manager, control.session, control.context = manager, session, context
    control.click, control.png = click, png
    try:
        yield control
    finally:
        await client.close()


async def observe(control):
    from tank_backend.core.content import TextBlock
    from tank_backend.tools.base import ToolResult

    result = await control.manager.execute_tool("screenshot")
    assert isinstance(result, ToolResult) and not result.error
    text = next(b.text for b in result.to_blocks() if isinstance(b, TextBlock))
    return json.loads(text[text.index("{") :])["frame_id"]


async def locate(control, frame, **kwargs):
    result = await control.manager.execute_tool("locate", frame_id=frame, target="red", **kwargs)
    assert not isinstance(result, str)
    return result


@pytest.mark.parametrize(
    "failure",
    [
        "not_found",
        "ambiguous",
        "malformed",
        "truncated",
        "stale",
        "changed",
        "window",
        "unknown_usage",
        "budget",
    ],
)
async def test_locate_failure_never_produces_executable_reference(locator, monkeypatch, failure):
    c = locator
    events = c.events
    frame = await observe(c)
    if failure in {"not_found", "ambiguous"}:
        c.status = failure
    elif failure == "malformed":
        c.raw = "[]"
    elif failure == "truncated":
        c.finish = "length"
    elif failure == "stale":
        await observe(c)
    elif failure == "window":
        result = await locate(c, frame, window_id=42)
        assert result.error
    elif failure == "changed":

        async def change():
            buf = io.BytesIO()
            Image.new("RGB", (100, 80), "blue").save(buf, "PNG")
            monkeypatch.setattr(macos, "_capture_screenshot_macos", lambda **kw: buf.getvalue())

        c.during = change
    elif failure == "unknown_usage":
        c.usage = False
    elif failure == "budget":
        c.context.budget.limit = 10
    if failure != "window":
        result = await locate(c, frame)
        assert "location_id" not in str(result.content)
    result = await c.manager.execute_tool("click", location_id="invented")
    assert result.error
    c.click.assert_not_called()
    assert len(c.requests) == (0 if failure in {"stale", "window"} else 1)
    if failure not in {"stale", "window", "unknown_usage"}:
        assert c.context.budget.total_tokens == 10
    outcomes = [metadata for kind, metadata in events if kind == "grounding_outcome"]
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["frame_id"] == frame and outcome["target"] == "red"
    assert outcome["call_id"].startswith("locate:")
    if failure in {"not_found", "ambiguous"}:
        assert outcome["outcome"] == failure
    elif failure == "truncated":
        assert outcome["reason"] == "incomplete_response"
        assert outcome["finish_reason"] == "length"
    elif failure == "malformed":
        assert outcome["reason"] == "invalid_location"
    elif failure in {"stale", "window", "changed"}:
        assert outcome["stage"] == ("observation_after" if failure == "changed"
                                    else "observation_before")
    else:
        assert outcome["stage"] == "accounting"
    if c.requests:
        assert outcome["usage_known"] == c.usage
        assert outcome["image_sha256"] == hashlib.sha256(c.png).hexdigest()


@pytest.mark.parametrize("field,value,reason", [
    ("refusal", "cannot locate", "refused_response"),
    ("tool_name", "other", "invalid_tool_call"),
    ("choices_count", 0, "invalid_response"),
    ("choices_count", 2, "invalid_response"),
    ("raw", '{"status":"found","x":500,"x":501,"y":500}', "invalid_location"),
])
async def test_locate_records_structured_rejection_without_repair(locator, field, value, reason):
    c = locator
    setattr(c, field, value)
    result = await locate(c, await observe(c))
    assert result.error and "location_id" not in str(result.content)
    outcomes = [m for kind, m in c.events if kind == "grounding_outcome"]
    assert len(outcomes) == 1
    assert outcomes[0]["stage"] == "parse" and outcomes[0]["reason"] == reason
    assert outcomes[0]["usage_known"] is True and c.context.budget.total_tokens == 10
    c.click.assert_not_called()


async def test_locate_request_failure_keeps_context_and_usage_unknown(locator):
    from tank_backend.tools.computer_grounding import grounding_call_id

    c = locator
    async def fail():
        assert grounding_call_id.get() is not None
        raise httpx.ReadError("synthetic connection failure")
    c.during = fail
    assert (await locate(c, await observe(c))).error
    assert grounding_call_id.get() is None
    outcomes = [m for kind, m in c.events if kind == "grounding_outcome"]
    assert len(outcomes) == 1
    assert outcomes[0]["stage"] == "request" and outcomes[0]["outcome"] == "error"
    assert outcomes[0]["error_type"] == "APIConnectionError"
    assert c.context.budget.unknown_calls == {outcomes[0]["call_id"]}
    assert len(c.requests) == 1
    c.click.assert_not_called()


async def test_cancel_while_locating_aborts_http_and_prevents_later_calls(locator):
    import asyncio

    c = locator
    entered, exited = asyncio.Event(), asyncio.Event()

    async def wait():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            exited.set()

    c.during = wait
    frame = await observe(c)
    task = asyncio.create_task(locate(c, frame))
    await asyncio.wait_for(entered.wait(), 1)
    c.context.cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 0.2)
    assert exited.is_set()
    with pytest.raises(asyncio.CancelledError):
        await locate(c, frame)
    c.click.assert_not_called()
    assert len(c.requests) == 1
    outcomes = [m for kind, m in c.events if kind == "grounding_outcome"]
    assert len(outcomes) == 1
    assert outcomes[0]["outcome"] == "cancelled" and outcomes[0]["stage"] == "request"


async def test_retry_limit_survives_reobservation_and_counts_duplicate_response_ids(locator):
    c = locator
    c.status = "ambiguous"
    for _ in range(3):
        assert not (await locate(c, await observe(c))).error
    result = await locate(c, await observe(c))
    assert result.error and "exhausted" in str(result.content)
    assert len(c.requests) == 3 and c.context.budget.total_tokens == 30
    outcomes = [m for kind, m in c.events if kind == "grounding_outcome"]
    assert len(outcomes) == 4 and len({m["call_id"] for m in outcomes}) == 4
    assert outcomes[-1]["stage"] == "preflight"


async def test_fallback_cannot_switch_back(locator):
    c = locator
    frame = await observe(c)
    assert not (await locate(c, frame)).error
    assert not (await locate(c, frame, backend="fallback")).error
    assert (await locate(c, frame, backend="primary")).error
    assert len(c.requests) == 2


async def test_two_located_targets_support_drag(locator, monkeypatch):
    c = locator
    drag = MagicMock()
    monkeypatch.setattr(macos, "_drag_macos", drag)
    frame = await observe(c)
    first = json.loads((await locate(c, frame)).content)["location_id"]
    second = json.loads((await locate(c, frame)).content)["location_id"]
    result = await c.manager.execute_tool("drag", location_id=first, end_location_id=second)
    assert not result.error
    drag.assert_called_once_with(50, 40, 50, 40)


async def test_short_batch_uses_references_and_stops_before_changed_scene(locator, monkeypatch):
    from tank_backend.tools.computer_locate import LocateTool

    c = locator
    c.manager.tools["computer_batch"] = LocateTool(c.session, "computer_batch")
    frame = await observe(c)
    ref = json.loads((await locate(c, frame)).content)["location_id"]

    def changed(*args):
        buf = io.BytesIO()
        Image.new("RGB", (100, 80), "blue").save(buf, "PNG")
        monkeypatch.setattr(macos, "_capture_screenshot_macos", lambda **kw: buf.getvalue())

    c.click.side_effect = changed
    args = {"actions": [{"action": "click", "location_id": ref}] * 3}
    result = await c.manager.execute_tool("computer_batch", **args)
    assert result.error
    assert '"skipped": 1' in str(result.content)
    assert c.click.call_count == 1
    replay = await c.manager.execute_tool("computer_batch", **args)
    assert replay.error and c.click.call_count == 1


@pytest.mark.parametrize("stop", ["cancel", "deadline", "revoked"])
async def test_stop_during_action_validation_never_dispatches(locator, monkeypatch, stop):
    import asyncio
    import time
    from dataclasses import replace

    c = locator
    frame = await observe(c)
    ref = json.loads((await locate(c, frame)).content)["location_id"]

    def stop_before_input(**kwargs):
        if stop == "cancel":
            c.context.cancel.set()
        elif stop == "deadline":
            c.session.context = replace(c.context, deadline=time.monotonic() - 1)
            c.session.tools["click"].check = c.session.context.check
        else:
            c.context.authorization.revoke()
        return c.png

    monkeypatch.setattr(macos, "_capture_screenshot_macos", stop_before_input)
    try:
        result = await c.manager.execute_tool("click", location_id=ref)
        assert result.error
    except asyncio.CancelledError:
        assert stop == "cancel"
    c.click.assert_not_called()


async def test_deadline_aborts_grounding_http(locator):
    import asyncio
    import time
    from dataclasses import replace

    c = locator
    frame = await observe(c)
    c.session.context = replace(c.context, deadline=time.monotonic() + 0.05)
    exited = asyncio.Event()

    async def wait():
        try:
            await asyncio.Event().wait()
        finally:
            exited.set()

    c.during = wait
    result = await locate(c, frame)
    assert result.error and exited.is_set()
    assert len(c.requests) == 1
    assert c.context.budget.unknown_calls
    assert (await locate(c, frame)).error
    assert len(c.requests) == 1
    c.click.assert_not_called()


@pytest.mark.parametrize("failure", ["ambiguous", "malformed", "truncated", "refused"])
async def test_failed_locate_invalidates_previous_reference(locator, failure):
    c = locator
    frame = await observe(c)
    ref = json.loads((await locate(c, frame)).content)["location_id"]
    if failure == "ambiguous":
        c.status = "ambiguous"
    elif failure == "malformed":
        c.raw = "[]"
    elif failure == "truncated":
        c.finish = "length"
    else:
        c.refusal = "cannot locate"
    await locate(c, frame)
    assert (await c.manager.execute_tool("click", location_id=ref)).error
    c.click.assert_not_called()


@pytest.mark.parametrize(
    "bad", [{"x": 1, "y": 2}, {"coordinate_space": "legacy"}, {"ctx": {"session_id": "other"}}]
)
async def test_split_rejects_planner_coordinates_and_context(locator, bad):
    c = locator
    frame = await observe(c)
    ref = json.loads((await locate(c, frame)).content)["location_id"]
    result = await c.manager.execute_tool("click", location_id=ref, **bad)
    assert result.error
    c.click.assert_not_called()


@pytest.mark.parametrize("config", ["[]", "null", "{profile: ''}", "{unknown: true}"])
def test_invalid_grounding_configuration_is_a_clear_parse_error(tmp_path, config):
    from tank_backend.agents.definition import parse_agent_file

    path = tmp_path / "agent.md"
    path.write_text(f"---\nname: split\ngrounding: {config}\n---\nUse the GUI")
    with pytest.raises(ValueError):
        parse_agent_file(path)


def test_grounding_configuration_is_opt_in_and_parsed(tmp_path):
    from tank_backend.agents.definition import parse_agent_file

    path = tmp_path / "agent.md"
    path.write_text(
        "---\nname: split\ngrounding: {profile: locator, protocol: bbox}\n---\nUse the GUI"
    )
    config = parse_agent_file(path).grounding
    assert config is not None and config.profile == "locator" and config.protocol == "bbox"
    assert AgentDefinition("legacy", "", "").grounding is None


async def test_batch_rejects_unavailable_actions_before_any_input(locator):
    from tank_backend.tools.computer_locate import LocateTool

    c = locator
    c.session.tools.pop("type_text")
    c.manager.tools["computer_batch"] = LocateTool(c.session, "computer_batch")
    frame = await observe(c)
    ref = json.loads((await locate(c, frame)).content)["location_id"]
    result = await c.manager.execute_tool(
        "computer_batch",
        actions=[
            {"action": "click", "location_id": ref},
            {"action": "type_text", "text": "blocked"},
        ],
    )
    assert result.error
    c.click.assert_not_called()


@pytest.mark.parametrize("native_error", [False, True])
async def test_cancel_joins_started_native_input_before_task_finishes(
    locator, monkeypatch, native_error,
):
    import asyncio
    import threading

    c = locator
    entered = asyncio.Event()
    release = threading.Event()
    finished = threading.Event()
    loop = asyncio.get_running_loop()
    def type_text(*args):
        loop.call_soon_threadsafe(entered.set)
        release.wait(2)
        finished.set()
        if native_error:
            raise RuntimeError("native failure during cancellation")
        return "typed"
    monkeypatch.setattr(macos, "_type_macos", type_text)
    task = asyncio.create_task(c.manager.execute_tool("type_text", text="a"))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        c.context.cancel.set()
        await asyncio.sleep(0.02)
        assert not task.done(), "Task must not release desktop while native input is still running"
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert finished.is_set()


def test_integrated_grounding_config_keeps_factors_independent(tmp_path):
    from tank_backend.agents.definition import GroundingConfig, parse_agent_file

    for protocol in ("legacy", "point", "pixels", "bbox"):
        for host_restore in (False, True):
            path = tmp_path / "integrated.md"
            path.write_text(
                "---\nname: integrated\ngrounding:\n  mode: integrated\n"
                f"  protocol: {protocol}\n  host_restore: {str(host_restore).lower()}\n"
                "---\nUse the GUI."
            )
            config = parse_agent_file(path).grounding
            assert config is not None and config.mode == "integrated"
            assert config.protocol == protocol and config.host_restore is host_restore
    assert GroundingConfig().mode == "split"
    invalid: list[dict[str, Any]] = [
        {"mode": "unknown"}, {"host_restore": "false"},
        {"host_restore": False}, {"protocol": "legacy"},
        {"mode": "integrated", "profile": "locator"},
        {"mode": "integrated", "fallback_profile": "fallback"},
        {"mode": "integrated", "strict": True},
    ]
    for kwargs in invalid:
        with pytest.raises(ValueError):
            GroundingConfig(**kwargs)


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("ending", ["success", "truncated", "duplicate"])
@pytest.mark.parametrize("protocol", ["legacy", "point", "pixels", "bbox"])
@pytest.mark.parametrize("host_restore", [False, True])
async def test_integrated_runner_uses_one_model_and_independent_host_mapping(
    desktop, monkeypatch, tmp_path, protocol, host_restore, ending, batch
):
    from tank_backend.agents.definition import GroundingConfig
    from tank_backend.benchmarks.driver import CountingLLM, SubAgentDriver
    from tank_backend.benchmarks.trace import TraceSink

    manager, click, _ = desktop
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["stream"] is True  # no hidden locator request
        schemas = {t["function"]["name"]: t["function"]["parameters"] for t in body["tools"]}
        assert "locate" not in schemas
        assert "Use the GUI." in body["messages"][0]["content"]
        if len(requests) == 1:
            return stream("screenshot", {"region": [500, 500, 1000, 1000]})
        if len(requests) == 2:
            text = next(p["text"] for m in body["messages"]
                        if isinstance(m.get("content"), list) for p in m["content"]
                        if p["type"] == "text" and "frame_id" in p["text"])
            observation = json.loads(text[text.index("{") :])
            if protocol == "legacy":
                location = {"x": 500, "y": 500}
            elif protocol == "bbox":
                location = {"status": "found", "left": 400, "top": 400,
                            "right": 600, "bottom": 600}
            elif protocol == "pixels":
                w, h = observation["image_size" if host_restore else "screen_size"]
                location = {"status": "found", "x": w // 2, "y": h // 2}
            else:
                location = {"status": "found", "x": 500, "y": 500}
            arguments = {"frame_id": observation["frame_id"], "location": location}
            name = "computer_batch" if batch else "click"
            payload = {"actions": [{"action": "click", **arguments}]} if batch else arguments
            if ending == "duplicate":
                return stream(name, json.dumps(payload).replace(
                    '"location":', '"location": {}, "location":',
                ))
            return stream(name, payload, finish="length" if ending == "truncated" else None)
        assert "dispatched" in json.dumps(body["messages"])
        return stream(None, {})

    client = AsyncOpenAI(api_key="test", max_retries=0,
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(llm_module, "AsyncOpenAI", lambda **kw: client)
    monkeypatch.setattr(llm_module, "initialize_langfuse", lambda: None)
    llm = CountingLLM(llm_module.LLM(api_key="test", model="test",
                                    base_url="https://offline.invalid/v1"))
    definition = AgentDefinition(
        "integrated", "", "Use the GUI.", tool_filter=("screenshot", "click", "computer_batch"),
        grounding=GroundingConfig(mode="integrated", protocol=protocol, host_restore=host_restore),
    )
    from typing import cast
    runner = AgentRunner(cast(llm_module.LLM, llm), manager, Bus(),
                         ToolApprovalPolicy(computer_mode="allow"), PendingToolCallStore(), {})
    trace = TraceSink(tmp_path / "trial")
    try:
        result = await SubAgentDriver(runner, definition, llm, manager).run(
            "Click the center", trace, timeout_s=5, max_steps=10,
        )
    finally:
        trace.close()
        await client.close()
    if ending != "success":
        assert result.error is not None
        click.assert_not_called()
        assert len(requests) == 2 and result.tokens == 10
        return
    assert result.error is None, result.error
    assert len(requests) == 3 and result.tokens == 15 and result.llm_calls == 3
    assert result.screenshots == 2 and result.non_gui_tools == ()
    assert result.primitives == 2
    click.assert_called_once_with(*( (75, 60) if host_restore else (50, 40)), "left", 1)
    assert "locate" not in manager.tools and manager._session_id == "parent-session"


@pytest.mark.parametrize("status", ["not_found", "ambiguous", "invalid", "stale", "changed"])
async def test_integrated_batch_stops_without_input_on_failed_location(
    locator, monkeypatch, status,
):
    from tank_backend.agents.definition import GroundingConfig
    from tank_backend.tools.computer_integrated import IntegratedSession, IntegratedTool

    c = locator
    session = IntegratedSession(c.session.tools, {}, c.session.adapter, c.context, "integrated")
    session.config = GroundingConfig(mode="integrated")
    c.session = session
    c.manager.tools = {n: IntegratedTool(session, n) for n in session.tools}
    c.manager.tools["computer_batch"] = IntegratedTool(session, "computer_batch")
    typed = MagicMock()
    monkeypatch.setattr(macos, "_type_macos", typed)
    frame = await observe(c)
    if status == "stale":
        await observe(c)
    if status == "changed":
        image = io.BytesIO()
        Image.new("RGB", (100, 80), "blue").save(image, "PNG")
        monkeypatch.setattr(macos, "_capture_screenshot_macos", lambda **kw: image.getvalue())
    location = {"status": status if status in {"not_found", "ambiguous"} else "found",
                "x": 0 if status in {"not_found", "ambiguous"} else 500, "y": 0}
    if status == "invalid":
        location["x"] = "500"
    actions = [{"action": "click", "frame_id": frame, "location": location},
               {"action": "type_text", "text": "must not type"}]
    result = await c.manager.execute_tool("computer_batch", actions=actions)
    assert result.error
    c.click.assert_not_called()
    typed.assert_not_called()
    assert not c.requests  # no locator HTTP


async def test_integrated_factor_schema_reuses_adapter_and_preserves_tool_allowlist(locator):
    from tank_backend.agents.definition import GroundingConfig
    from tank_backend.tools.computer_grounding import GroundingAdapter
    from tank_backend.tools.computer_integrated import IntegratedSession, IntegratedTool

    c = locator
    # A restricted mouse-move agent must not need a registered click tool for schema generation.
    tools = {n: t for n, t in c.session.tools.items() if n in {"screenshot", "mouse_move"}}
    for protocol in ("legacy", "point", "pixels", "bbox"):
        schemas = []
        for host_restore in (False, True):
            adapter = GroundingAdapter("point" if protocol == "legacy" else protocol,
                                       status_field=True)
            session = IntegratedSession(tools, {}, adapter, c.context, "paired")
            session.config = GroundingConfig(mode="integrated", protocol=protocol,
                                             host_restore=host_restore)
            schema = IntegratedTool(session, "mouse_move").get_raw_schema()
            schemas.append(schema)
            if protocol != "legacy":
                assert schema["properties"]["location"] == adapter.schema()
            batch = IntegratedTool(session, "computer_batch").get_raw_schema()
            actions = batch["properties"]["actions"]["items"]["oneOf"]
            assert [s["properties"]["action"]["const"] for s in actions] == ["mouse_move"]
            assert actions[0]["properties"]["location"] == schema["properties"]["location"]
        assert schemas[0] == schemas[1]  # host restoration never changes the wire schema
