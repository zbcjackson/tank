"""M7 AX semantic addressing; HTTP and OS/AX boundaries are fake."""

import asyncio
import io
import json
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from PIL import Image

from tank_backend.agents.approval import PendingToolCallStore, ToolApprovalPolicy
from tank_backend.agents.base import AgentOutputType
from tank_backend.agents.definition import AgentDefinition, GroundingConfig
from tank_backend.agents.runner import AgentRunner
from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
from tank_backend.core.content import TextBlock
from tank_backend.llm import llm as llm_module
from tank_backend.pipeline.bus import Bus
from tank_backend.tools import computer_ax
from tank_backend.tools import computer_use_macos as macos
from tank_backend.tools.base import ToolResult
from tank_backend.tools.computer_ax import AXCandidate, AXElementRef
from tank_backend.tools.computer_grounding import GroundingResponseError
from tank_backend.tools.computer_locate import LocateSession, LocateTool
from tank_backend.tools.groups import ComputerUseToolGroup
from tank_backend.tools.manager import ToolManager

WINDOW = {"kCGWindowNumber": 7, "kCGWindowOwnerPID": 42, "kCGWindowLayer": 0,
          "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 100, "Height": 80}}


@pytest.fixture
def desktop(monkeypatch):
    quartz = MagicMock()
    quartz.CGMainDisplayID.return_value = 5
    quartz.CGDisplayBounds.return_value = ((0, 0), (100, 80))
    quartz.CGDisplayModeGetPixelWidth.return_value = 200
    quartz.CGDisplayModeGetPixelHeight.return_value = 160
    quartz.CGWindowListCopyWindowInfo.return_value = [WINDOW]
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
    return SimpleNamespace(manager=manager, click=click, png=png, quartz=quartz)


class _Point:
    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y


class _Size:
    def __init__(self, w: float, h: float) -> None:
        self.width, self.height = w, h


class _AXValue:
    def __init__(self, *, x: float = 0.0, y: float = 0.0, w: float = 0.0, h: float = 0.0,
                 point: bool = True) -> None:
        self._point, self._x, self._y, self._w, self._h = point, x, y, w, h

    def CGPointValue(self) -> _Point:
        return _Point(self._x, self._y)

    def pointValue(self) -> _Point:
        return _Point(self._x, self._y)

    def CGSizeValue(self) -> _Size:
        return _Size(self._w, self._h)

    def sizeValue(self) -> _Size:
        return _Size(self._w, self._h)


class _Element:
    def __init__(self, attrs: dict[str, Any], children: Any = None) -> None:
        self.attrs, self.children = dict(attrs), children if children is not None else []


class _App:
    def __init__(self, pid: int, windows: list[_Element]) -> None:
        self.pid, self.windows = pid, windows


def make_api(app: _App, *, windows_error: int = 0) -> dict[str, Any]:
    def copy_attr(element: Any, name: str, _: Any = None) -> tuple[int, Any]:
        if isinstance(element, _App):
            if name == "AXWindows":
                return (windows_error, None if windows_error else app.windows)
            return (-25204, None)
        if name == "AXChildren":
            return (0, element.children or None)
        return (0, element.attrs.get(name))

    def create_app(pid: int) -> _App:
        if pid != app.pid:
            raise ValueError(f"unexpected pid {pid}")
        return app

    def perform(element: Any, action: str) -> int:
        return 0

    return {"AXUIElementCreateApplication": create_app,
            "AXUIElementCopyAttributeValue": copy_attr,
            "AXUIElementPerformAction": perform}


def button(title: str, x: float, y: float, w: float = 10.0, h: float = 10.0) -> _Element:
    return _Element({
        "AXRole": "AXButton", "AXTitle": title, "AXValue": "", "AXDescription": "",
        "AXIdentifier": "", "AXActions": ["AXPress"], "AXEnabled": True,
        "AXPosition": _AXValue(x=x, y=y), "AXSize": _AXValue(w=w, h=h),
    })


def fake_candidates(window_id: int, geometry: tuple[int, ...]) -> tuple[list[AXCandidate], bool]:
    assert window_id == 7
    element = object()
    ref = AXElementRef(element, flip=False, screen_height=geometry[4])
    return [
        AXCandidate(index=1, role="AXButton", title="7", value="", description="",
                    identifier="", actions=("AXPress",), enabled=True, frame=(40, 30, 10, 10),
                    element=ref),
        AXCandidate(index=2, role="AXButton", title="8", value="", description="",
                    identifier="", actions=("AXPress",), enabled=True, frame=(60, 30, 10, 10),
                    element=ref),
    ], False


def selection_response(status: str, index: int) -> ChatCompletion:
    return ChatCompletion.model_validate({
        "id": "ax", "object": "chat.completion", "created": 1, "model": "test",
        "choices": [{
            "index": 0, "finish_reason": "tool_calls",
            "message": {"role": "assistant", "tool_calls": [
                {"id": "c", "type": "function",
                 "function": {"name": "select",
                              "arguments": json.dumps({"status": status, "index": index})}},
            ]},
        }],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
    })


def fake_llm(response: ChatCompletion) -> MagicMock:
    llm = MagicMock()
    llm.model = "test"
    llm.complete_response = AsyncMock(return_value=response)
    return llm


def make_session(
    desktop, ax_action: str, llm: Any,
) -> tuple[Any, SubAgentContext, list[tuple[str, dict[str, Any]]]]:
    events: list[tuple[str, dict[str, Any]]] = []

    class Observer:
        def on_event(self, kind: str, metadata: dict[str, Any]) -> None:
            events.append((kind, metadata))

    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop"})), SubAgentBudget(limit=100), asyncio.Event(),
        observer=Observer(),
    )
    session = computer_ax.AXSession(
        desktop.manager.tools, {"primary": llm}, context, "ax-test", ax_action)
    return session, context, events


async def call(session, name: str, **kwargs) -> ToolResult:
    result = await LocateTool(session, name).execute(**kwargs)
    assert isinstance(result, ToolResult)
    return result


async def observe_and_locate(session) -> dict[str, Any]:
    shot = await call(session, "screenshot", window_id=7)
    text = next(b.text for b in shot.to_blocks() if isinstance(b, TextBlock))
    frame = json.loads(text[text.index("{"):])["frame_id"]
    located = await call(session, "locate", frame_id=frame,
                          target="the seven button", window_id=7)
    assert not located.error, located.content
    content = located.content
    assert isinstance(content, str)
    return json.loads(content)


# ---------------------------------------------------------------- config


def test_grounding_config_ax_modes() -> None:
    from tank_backend.agents.definition import GroundingConfig

    assert GroundingConfig(mode="ax").ax_action == "quartz"
    assert GroundingConfig(mode="ax", ax_action="ax_press").ax_action == "ax_press"
    with pytest.raises(ValueError, match="ax_action"):
        GroundingConfig(mode="ax", ax_action="bounce")
    with pytest.raises(ValueError, match="mode"):
        GroundingConfig(mode="semantic")


# ------------------------------------------------- listing/payload/parse


def test_candidate_listing_and_payload_exclude_pixels_and_truth() -> None:
    ref = AXElementRef(object(), flip=False, screen_height=80)
    candidates = [
        AXCandidate(index=1, role="AXButton", title="7", value="", description="",
                    identifier="digit-7", actions=("AXPress",), enabled=True,
                    frame=(40, 30, 10, 10), element=ref),
        AXCandidate(index=2, role="AXButton", title="7", value="", description="",
                    identifier="", actions=(), enabled=None, frame=None, element=ref),
    ]
    listing = computer_ax.format_candidates(candidates)
    assert '1. role=AXButton title="7" identifier="digit-7"' in listing
    assert "frame=(40, 30, 10, 10)" in listing
    assert "actions=[AXPress]" in listing
    assert "2. role=AXButton" in listing and "frame=unknown" in listing
    assert not any(word in listing for word in ("truth", "mask", "score"))

    payload = computer_ax.ax_selection_payload(candidates, "seven key", truncated=True)
    assert "truncated" in payload["messages"][1]["content"]
    assert "Target: seven key" in payload["messages"][1]["content"]
    assert "image_url" not in json.dumps(payload["messages"])
    function = payload["tools"][0]["function"]
    assert function["name"] == "select"
    assert function["parameters"]["properties"]["index"]["maximum"] == 2


def test_parse_ax_selection_strictness() -> None:
    good = computer_ax.parse_ax_selection('{"status": "found", "index": 2}', 3)
    assert good.status == "found" and good.index == 2
    assert computer_ax.parse_ax_selection(
        '{"status": "ambiguous", "index": 0}', 3).status == "ambiguous"
    for raw, message in [
        ('{"status": "found", "index": 4}', "range"),
        ('{"status": "found", "index": 0}', "range"),
        ('{"status": "found", "index": "2"}', "integer"),
        ('{"status": "maybe", "index": 1}', "status"),
        ('{"status": "ambiguous", "index": 1}', "Abstention"),
        ('{"status": "found"}', "fields"),
        ('{"status": "found", "index": 1, "x": 5}', "fields"),
        ("not json", "Expecting"),
    ]:
        with pytest.raises(ValueError, match=message):
            computer_ax.parse_ax_selection(raw, 3)


def test_parse_ax_selection_response_rejects_malformed_calls() -> None:
    refusal = ChatCompletion.model_validate({
        "id": "r", "object": "chat.completion", "created": 1, "model": "test",
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant", "refusal": "no"}}],
    })
    with pytest.raises(GroundingResponseError, match="refused"):
        computer_ax.parse_ax_selection_response(refusal, 2)
    wrong_tool = ChatCompletion.model_validate({
        "id": "w", "object": "chat.completion", "created": 1, "model": "test",
        "choices": [{"index": 0, "finish_reason": "tool_calls",
                     "message": {"role": "assistant", "tool_calls": [
                         {"id": "c", "type": "function",
                          "function": {"name": "click",
                                       "arguments": '{"status": "found", "index": 1}'}}]}}],
    })
    with pytest.raises(GroundingResponseError, match="select"):
        computer_ax.parse_ax_selection_response(wrong_tool, 2)


# ------------------------------------------------------- enumeration


def test_ax_window_candidates_enumerates_bound_window(monkeypatch) -> None:
    quartz = MagicMock()
    quartz.CGWindowListCopyWindowInfo.return_value = [WINDOW]
    monkeypatch.setattr(macos, "_load_quartz", lambda: quartz)
    group = _Element({"AXRole": "AXGroup",
                      "AXPosition": _AXValue(x=0, y=0), "AXSize": _AXValue(w=100, h=80)})
    text = _Element({"AXRole": "AXStaticText", "AXTitle": "Display", "AXValue": "0",
                     "AXPosition": _AXValue(x=10, y=5), "AXSize": _AXValue(w=80, h=10)})
    seven = button("7", 40, 30)
    duplicate = button("7", 60, 30)
    window = _Element({"AXRole": "AXWindow",
                       "AXPosition": _AXValue(x=0, y=0), "AXSize": _AXValue(w=100, h=80)},
                      [group, text, seven, duplicate])
    monkeypatch.setattr(computer_ax, "_load_ax", lambda: make_api(_App(42, [window])))
    candidates, truncated = computer_ax.ax_window_candidates(7, (5, 0, 0, 100, 80, 200, 160))
    assert truncated is False
    assert [c.title for c in candidates] == ["Display", "7", "7"]
    assert candidates[0].role == "AXStaticText" and candidates[0].frame == (10, 5, 80, 10)
    assert candidates[1].actions == ("AXPress",)
    assert candidates[1].element.flip is False
    assert all(c.role != "AXGroup" for c in candidates)
    with pytest.raises(ValueError, match="window"):
        computer_ax.ax_window_candidates(999, (5, 0, 0, 100, 80, 200, 160))


def test_ax_window_candidates_calibrates_flipped_orientation(monkeypatch) -> None:
    # Bottom-left style AX coordinates: window top y=20, height 80, screen 80.
    window = _Element({"AXRole": "AXWindow",
                       "AXPosition": _AXValue(x=10, y=-20), "AXSize": _AXValue(w=100, h=80)},
                      [button("7", 50, 40)])
    cg = {"kCGWindowNumber": 7, "kCGWindowOwnerPID": 42, "kCGWindowLayer": 0,
          "kCGWindowBounds": {"X": 10, "Y": 20, "Width": 100, "Height": 80}}
    quartz = MagicMock()
    quartz.CGWindowListCopyWindowInfo.return_value = [cg]
    monkeypatch.setattr(macos, "_load_quartz", lambda: quartz)
    monkeypatch.setattr(computer_ax, "_load_ax", lambda: make_api(_App(42, [window])))
    candidates, _ = computer_ax.ax_window_candidates(7, (5, 0, 0, 100, 80, 200, 160))
    assert candidates[0].frame == (50, 30, 10, 10)
    assert candidates[0].element.flip is True


def test_ax_window_candidates_caps_and_truncates(monkeypatch) -> None:
    quartz = MagicMock()
    quartz.CGWindowListCopyWindowInfo.return_value = [WINDOW]
    monkeypatch.setattr(macos, "_load_quartz", lambda: quartz)
    window = _Element({"AXRole": "AXWindow",
                       "AXPosition": _AXValue(x=0, y=0), "AXSize": _AXValue(w=100, h=80)},
                      [button(str(i), 10 * i, 30) for i in range(4)])
    monkeypatch.setattr(computer_ax, "_load_ax", lambda: make_api(_App(42, [window])))
    monkeypatch.setattr(computer_ax, "MAX_ELEMENTS", 2)
    candidates, truncated = computer_ax.ax_window_candidates(7, (5, 0, 0, 100, 80, 200, 160))
    assert len(candidates) == 2 and truncated is True

    monkeypatch.setattr(computer_ax, "MAX_ELEMENTS", 500)
    monkeypatch.setattr(computer_ax, "MAX_DEPTH", 1)
    deep = _Element({"AXRole": "AXGroup",
                     "AXPosition": _AXValue(x=0, y=0), "AXSize": _AXValue(w=1, h=1)},
                    [button("hidden", 5, 5)])
    window2 = _Element({"AXRole": "AXWindow",
                        "AXPosition": _AXValue(x=0, y=0), "AXSize": _AXValue(w=100, h=80)},
                       [deep])
    monkeypatch.setattr(computer_ax, "_load_ax", lambda: make_api(_App(42, [window2])))
    candidates, truncated = computer_ax.ax_window_candidates(7, (5, 0, 0, 100, 80, 200, 160))
    assert candidates == [] and truncated is False


# ------------------------------------------------------- session flows


async def test_ax_quartz_locates_selects_and_dispatches(desktop, monkeypatch) -> None:
    monkeypatch.setattr(computer_ax, "ax_window_candidates", fake_candidates)
    refreshed = fake_candidates(7, (5, 0, 0, 100, 80, 200, 160))[0][0]
    monkeypatch.setattr(computer_ax, "ax_refresh_candidate", lambda ref: refreshed)
    session, context, events = make_session(desktop, "quartz", fake_llm(
        selection_response("found", 1)))
    result = await observe_and_locate(session)
    assert result["status"] == "found" and result["location_id"]
    click = await call(session, "click", location_id=result["location_id"])
    assert not click.error, click.content
    desktop.click.assert_called_once_with(45, 35, "left", 1)
    outcomes = [e for kind, e in events if kind == "grounding_outcome"]
    assert outcomes[0]["outcome"] == "found" and outcomes[0]["protocol"] == "ax"
    assert outcomes[0]["candidate_count"] == 2 and outcomes[0]["selected_index"] == 1
    usage = [e for kind, e in events if kind == "grounding_usage"]
    assert usage[0]["usage_known"] is True and context.budget.total_tokens == 10


async def test_ax_press_performs_action_without_pointer(desktop, monkeypatch) -> None:
    pressed = []

    def record_press(ref: AXElementRef) -> None:
        pressed.append(ref)

    monkeypatch.setattr(computer_ax, "ax_window_candidates", fake_candidates)
    refreshed = fake_candidates(7, (5, 0, 0, 100, 80, 200, 160))[0][0]
    monkeypatch.setattr(computer_ax, "ax_refresh_candidate", lambda ref: refreshed)
    monkeypatch.setattr(computer_ax, "ax_press", record_press)
    session, _, _ = make_session(desktop, "ax_press", fake_llm(selection_response("found", 2)))
    result = await observe_and_locate(session)
    click = await call(session, "click", location_id=result["location_id"])
    assert not click.error and "AXPress" in str(click.content)
    assert len(pressed) == 1
    desktop.click.assert_not_called()


async def test_ax_press_works_without_advertised_actions(desktop, monkeypatch) -> None:
    # Real macOS 26 Calculator buttons accept AXPress without an AXActions
    # attribute; PerformAction's error code is the authority.
    ref = AXElementRef(object(), flip=False, screen_height=80)
    bare = AXCandidate(index=1, role="AXButton", title="", value="", description="7",
                       identifier="", actions=(), enabled=True, frame=(40, 30, 10, 10),
                       element=ref)
    monkeypatch.setattr(computer_ax, "ax_window_candidates",
                        lambda wid, g: ([bare], False))
    monkeypatch.setattr(computer_ax, "ax_refresh_candidate", lambda r: bare)
    pressed = []
    monkeypatch.setattr(computer_ax, "ax_press", lambda r: pressed.append(r))
    session, _, _ = make_session(desktop, "ax_press", fake_llm(selection_response("found", 1)))
    result = await observe_and_locate(session)
    click = await call(session, "click", location_id=result["location_id"])
    assert not click.error, click.content
    assert len(pressed) == 1


async def test_ax_press_rejects_other_pointer_actions(desktop, monkeypatch) -> None:
    monkeypatch.setattr(computer_ax, "ax_window_candidates", fake_candidates)
    session, _, _ = make_session(desktop, "ax_press", fake_llm(selection_response("found", 1)))
    result = await observe_and_locate(session)
    drag = await call(session, "drag", location_id=result["location_id"],
                      end_location_id=result["location_id"])
    assert drag.error and "click only" in str(drag.content)
    right = await call(session, "click", location_id=result["location_id"],
                        button="right")
    assert right.error and "button/clicks" in str(right.content)
    desktop.click.assert_not_called()


async def test_ax_stale_element_refuses_zero_input(desktop, monkeypatch) -> None:
    monkeypatch.setattr(computer_ax, "ax_window_candidates", fake_candidates)
    monkeypatch.setattr(computer_ax, "ax_refresh_candidate", lambda ref: None)
    session, _, _ = make_session(desktop, "quartz", fake_llm(selection_response("found", 1)))
    result = await observe_and_locate(session)
    click = await call(session, "click", location_id=result["location_id"])
    assert click.error and "Stale AX element" in str(click.content)
    desktop.click.assert_not_called()


async def test_ax_window_move_refuses_zero_input(desktop, monkeypatch) -> None:
    monkeypatch.setattr(computer_ax, "ax_window_candidates", fake_candidates)
    refreshed = fake_candidates(7, (5, 0, 0, 100, 80, 200, 160))[0][0]
    monkeypatch.setattr(computer_ax, "ax_refresh_candidate", lambda ref: refreshed)
    session, _, _ = make_session(desktop, "quartz", fake_llm(selection_response("found", 1)))
    result = await observe_and_locate(session)
    desktop.quartz.CGWindowListCopyWindowInfo.return_value = [{
        **WINDOW, "kCGWindowBounds": {"X": 10, "Y": 10, "Width": 90, "Height": 70}}]
    click = await call(session, "click", location_id=result["location_id"])
    assert click.error and "geometry" in str(click.content).lower()
    desktop.click.assert_not_called()


async def test_ax_ambiguous_and_not_found_keep_zero_input(desktop, monkeypatch) -> None:
    monkeypatch.setattr(computer_ax, "ax_window_candidates", fake_candidates)
    for status in ("ambiguous", "not_found"):
        session, _, _ = make_session(desktop, "quartz", fake_llm(selection_response(status, 0)))
        result = await observe_and_locate(session)
        assert result["status"] == status and "location_id" not in result
        click = await call(session, "click", location_id="missing")
        assert click.error
    desktop.click.assert_not_called()


async def test_ax_requires_window_bound_frame(desktop, monkeypatch) -> None:
    monkeypatch.setattr(computer_ax, "ax_window_candidates", fake_candidates)
    session, _, _ = make_session(desktop, "quartz", fake_llm(selection_response("found", 1)))
    shot = await call(session, "screenshot")
    text = next(b.text for b in shot.to_blocks() if isinstance(b, TextBlock))
    frame = json.loads(text[text.index("{"):])["frame_id"]
    located = await call(session, "locate", frame_id=frame, target="seven")
    assert located.error and "window-bound" in str(located.content)


async def test_ax_unknown_usage_is_not_zero(desktop, monkeypatch) -> None:
    monkeypatch.setattr(computer_ax, "ax_window_candidates", fake_candidates)
    response = selection_response("found", 1)
    object.__setattr__(response, "usage", None)
    session, context, _ = make_session(desktop, "quartz", fake_llm(response))
    context.budget.limit = 0  # Only the shared stop path reacts to unknown usage.
    located = await observe_and_locate(session)
    assert located["status"] == "found"
    assert context.budget.unknown_calls


# ------------------------------------------------------- runner flows


def stream(name: str | None, arguments: dict[str, Any]) -> httpx.Response:
    delta = (
        {"tool_calls": [{"index": 0, "id": "call", "type": "function", "function": {
            "name": name,
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments)}}]}
        if name else {"content": "done"}
    )
    chunk = {"id": "planner", "object": "chat.completion.chunk", "created": 1, "model": "test",
             "choices": [{"index": 0, "delta": delta,
                          "finish_reason": "tool_calls" if name else "stop"}],
             "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}}
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                          content=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n")


@pytest.mark.parametrize("ax_action", ["quartz", "ax_press"])
async def test_runner_ax_grounding_flow(desktop, monkeypatch, ax_action) -> None:
    refreshed = fake_candidates(7, (5, 0, 0, 100, 80, 200, 160))[0][0]
    monkeypatch.setattr(computer_ax, "ax_window_candidates", fake_candidates)
    monkeypatch.setattr(computer_ax, "ax_refresh_candidate", lambda ref: refreshed)
    pressed = []
    monkeypatch.setattr(computer_ax, "ax_press",
                        lambda ref: pressed.append(ref))
    requests: list[dict[str, Any]] = []
    planner_turn = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal planner_turn
        body = json.loads(request.content)
        requests.append(body)
        if not body.get("stream"):
            assert body["tools"][0]["function"]["name"] == "select"
            assert "image_url" not in json.dumps(body["messages"])
            assert 'title="7"' in body["messages"][1]["content"]
            assert "Target: the seven button" in body["messages"][1]["content"]
            return httpx.Response(200, json={
                "id": "selector", "object": "chat.completion", "created": 1, "model": "test",
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                    "role": "assistant", "tool_calls": [
                        {"id": "s", "type": "function", "function": {
                            "name": "select",
                            "arguments": json.dumps({"status": "found", "index": 1})}}]}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}})
        planner_turn += 1
        schemas = {t["function"]["name"]: t["function"]["parameters"] for t in body["tools"]}
        assert "locate" in schemas and "x" not in schemas["click"]["properties"]
        assert "AX semantic addressing" in body["messages"][0]["content"]
        if planner_turn == 1:
            return stream("screenshot", {"window_id": 7})
        if planner_turn == 2:
            text = next(p["text"] for m in body["messages"]
                        if isinstance(m.get("content"), list) for p in m["content"]
                        if p["type"] == "text" and "frame_id" in p["text"])
            frame = json.loads(text[text.index("{"):])["frame_id"]
            return stream("locate", {"frame_id": frame, "target": "the seven button",
                                      "window_id": 7})
        if planner_turn == 3:
            result = json.loads(next(m["content"] for m in body["messages"]
                                     if m.get("name") == "locate"))
            assert result["status"] == "found" and "point" not in result
            return stream("click", {"location_id": result["location_id"]})
        assert "dispatched" in json.dumps(body["messages"])
        return stream(None, {})

    client = AsyncOpenAI(api_key="test", max_retries=0,
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(llm_module, "AsyncOpenAI", lambda **kw: client)
    monkeypatch.setattr(llm_module, "initialize_langfuse", lambda: None)
    llm = llm_module.LLM(api_key="test", model="test", base_url="https://offline.invalid/v1")
    definition = AgentDefinition(
        "ax", "", "Use the GUI.", tool_filter=("screenshot", "click"),
        grounding=GroundingConfig(mode="ax", ax_action=ax_action),
    )
    runner = AgentRunner(llm, desktop.manager, Bus(),
                         ToolApprovalPolicy(computer_mode="allow"), PendingToolCallStore(),
                         {"ax": definition})
    try:
        outputs = [o async for o in runner.run_agent(
            definition,
            [{"role": "user", "content": "private task history: press the seven button"}],
            token_budget=100)]
        assert outputs[-1].type == AgentOutputType.DONE
        if ax_action == "quartz":
            desktop.click.assert_called_once_with(45, 35, "left", 1)
            assert not pressed
        else:
            desktop.click.assert_not_called()
            assert len(pressed) == 1
        assert len(requests) == 5  # 4 planner turns + 1 AX selection
    finally:
        await client.close()


async def test_ax_session_rejects_missing_frame_adapter(desktop) -> None:
    # LocateSession without an adapter stays split-incompatible (fail closed).
    context = SubAgentContext(SubAgentAuthorization(frozenset({"desktop"})),
                              SubAgentBudget(), asyncio.Event())
    session = LocateSession(desktop.manager.tools, {"primary": MagicMock()}, None,
                            context, "no-adapter")
    shot = await call(session, "screenshot", window_id=7)
    text = next(b.text for b in shot.to_blocks() if isinstance(b, TextBlock))
    frame = json.loads(text[text.index("{"):])["frame_id"]
    located = await call(session, "locate", frame_id=frame, target="x", window_id=7)
    assert located.error and "adapter" in str(located.content)


class NSArrayLike:
    """pyobjc returns NSArray subclasses that are not Python list/tuple."""

    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)


def test_ax_window_candidates_walks_nsarray_children_and_actions(monkeypatch) -> None:
    quartz = MagicMock()
    quartz.CGWindowListCopyWindowInfo.return_value = [WINDOW]
    monkeypatch.setattr(macos, "_load_quartz", lambda: quartz)
    seven = button("7", 40, 30)
    seven.attrs["AXActions"] = NSArrayLike(["AXPress"])
    window = _Element({"AXRole": "AXWindow",
                       "AXPosition": _AXValue(x=0, y=0), "AXSize": _AXValue(w=100, h=80)},
                      NSArrayLike([seven]))
    monkeypatch.setattr(computer_ax, "_load_ax", lambda: make_api(_App(42, [window])))
    candidates, truncated = computer_ax.ax_window_candidates(7, (5, 0, 0, 100, 80, 200, 160))
    assert truncated is False
    assert [c.title for c in candidates] == ["7"]
    assert candidates[0].actions == ("AXPress",)
