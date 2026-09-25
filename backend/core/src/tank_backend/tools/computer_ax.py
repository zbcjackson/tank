"""M7 AX semantic addressing: numbered candidates from the live AX tree.

The AX branch is an independent experiment arm beside pure vision. locate()
enumerates accessibility candidates of the window bound to the current
observation — nothing is hardcoded per application and no scoring truth is
included — and a selector model picks one candidate by number through a text
request (no pixels are uploaded for locating). Dispatch either synthesizes a
Quartz pointer event at the element frame through the M2 validated path
(quartz mode) or performs the element's AXPress action directly (ax_press
mode). The AX C API is loaded lazily through pyobjc so non-macOS hosts and
tests can substitute the boundary.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from openai.types.chat import ChatCompletion

from ..agents.subagent import SubAgentContext
from ..llm.llm import LLM
from . import computer_use_macos as macos
from .base import ToolContext, ToolResult
from .computer_grounding import GroundingResponseError, _unique_object, grounding_call_id
from .computer_locate import LocateSession
from .computer_native import run_native
from .computer_observation import Observation

AX_PROMPT = """Desktop planning uses AX semantic addressing.
For this run, this tool contract replaces earlier coordinate and tool-call-format
instructions. All other task-specific instructions remain applicable.
Observe with screenshot (the host binds the target window automatically), then call
locate(frame_id, target). Describe the unique target in words; the host enumerates
numbered accessibility candidates of the bound window and selects one.
Never calculate or supply coordinates. Use only returned location_id references
for click, mouse_move, scroll or drag (drag also requires end_location_id).
Missing/ambiguous/error means no action; clarify the target, observe again, or
stop. Elements without an accessibility representation cannot be addressed this
way; report that instead of guessing positions. At most two re-locations per
action step; at most one switch to the configured fallback per step. Re-observation
does not reset these limits. A dispatched action is not proof of success. Inspect
the returned screenshot and verify the expected effect. Report execution failure
separately from no visible effect. Never blindly replay a failed batch. Use
computer_batch only for short predictable sequences; each located target is
revalidated before input. Keyboard shortcuts and type_text remain available when
advertised.
"""

MAX_ELEMENTS = 500
MAX_DEPTH = 12
MAX_CHILDREN = 64

_ADDRESSABLE_ROLES = frozenset({
    "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXMenuButton",
    "AXSlider", "AXTextField", "AXSecureTextField", "AXTextArea", "AXSearchField",
    "AXTab", "AXLink", "AXMenuItem", "AXValueIndicator", "AXColorWell",
    "AXIncrementor", "AXStaticText", "AXImage", "AXHeading",
})

_AX_FUNCTIONS: dict[str, Any] = {}


@dataclass(frozen=True)
class AXElementRef:
    """Native element handle plus the orientation decided at enumeration."""

    native: Any
    flip: bool
    screen_height: int


@dataclass(frozen=True)
class AXCandidate:
    index: int
    role: str
    title: str
    value: str
    description: str
    identifier: str
    actions: tuple[str, ...]
    enabled: bool | None
    frame: tuple[int, int, int, int] | None
    element: AXElementRef


@dataclass(frozen=True)
class AXSelection:
    status: Literal["found", "not_found", "ambiguous"]
    index: int | None = None


@dataclass(frozen=True)
class AXLocatedTarget:
    observation: Observation
    candidate: AXCandidate


def _load_ax() -> dict[str, Any]:
    if _AX_FUNCTIONS:
        return _AX_FUNCTIONS
    # pyobjc exports HIServices symbols dynamically, without static stubs.
    foundation: Any = importlib.import_module("Foundation")
    objc: Any = importlib.import_module("objc")
    bundle = foundation.NSBundle.bundleWithPath_(
        "/System/Library/Frameworks/ApplicationServices.framework"
        "/Frameworks/HIServices.framework"
    )
    if bundle is None:
        raise RuntimeError("HIServices framework unavailable")
    functions: dict[str, Any] = {}
    objc.loadBundleFunctions(bundle, functions, [
        ("AXUIElementCreateApplication", b"@i"),
        ("AXUIElementCopyAttributeValue", b"i@@o^@"),
        ("AXUIElementPerformAction", b"i@@"),
        # CGPoint and CGSize share the two-CGDouble layout, so one struct
        # signature decodes both attribute kinds (type passed per call).
        ("AXValueGetValue", b"B@io^{CGPoint=dd}"),
    ])
    missing = {"AXUIElementCreateApplication", "AXUIElementCopyAttributeValue",
               "AXUIElementPerformAction", "AXValueGetValue"} - functions.keys()
    if missing:
        raise RuntimeError(f"AX functions unavailable: {sorted(missing)}")
    _AX_FUNCTIONS.update(functions)
    return _AX_FUNCTIONS


def _attr(api: dict[str, Any], element: Any, name: str) -> Any:
    err, value = api["AXUIElementCopyAttributeValue"](element, name, None)
    if err != 0:
        return None
    return value


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _clean(value: object, limit: int = 80) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _strings(value: object) -> tuple[str, ...]:
    # pyobjc NSArrays are iterable but not list/tuple subclasses; the
    # structural Iterable check accepts both them and plain Python lists.
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _flag(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _cg_point(value: object) -> tuple[float, float] | None:
    if value is None:
        return None
    decoder = _load_ax().get("AXValueGetValue")
    if decoder is not None:
        point = None
        try:
            ok, point = decoder(value, 1, None)  # kAXValueCGPointType
        except Exception:  # untyped AX value; fall through to other decodings
            ok = False
        if ok and point is not None:
            return (float(point.x), float(point.y))
    converted: Any = None
    for method in ("CGPointValue", "pointValue"):
        function = getattr(value, method, None)
        if callable(function):
            converted = function()
            break
    if converted is not None:
        return (float(converted.x), float(converted.y))
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            return (float(value[0]), float(value[1]))
        except (TypeError, ValueError):
            return None
    return None


def _cg_size(value: object) -> tuple[float, float] | None:
    if value is None:
        return None
    decoder = _load_ax().get("AXValueGetValue")
    if decoder is not None:
        size = None
        try:
            ok, size = decoder(value, 2, None)  # kAXValueCGSizeType
        except Exception:  # untyped AX value; fall through to other decodings
            ok = False
        if ok and size is not None:
            return (float(size.x), float(size.y))
    converted: Any = None
    for method in ("CGSizeValue", "sizeValue"):
        function = getattr(value, method, None)
        if callable(function):
            converted = function()
            break
    if converted is not None:
        return (float(converted.width), float(converted.height))
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            return (float(value[0]), float(value[1]))
        except (TypeError, ValueError):
            return None
    return None


def _position_size(
    api: dict[str, Any], element: Any,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    point = _cg_point(_attr(api, element, "AXPosition"))
    size = _cg_size(_attr(api, element, "AXSize"))
    if point is None or size is None:
        return None
    return point, size


def _top_left_frame(
    api: dict[str, Any], element: Any, screen_height: int,
) -> tuple[int, int, int, int] | None:
    measured = _position_size(api, element)
    if measured is None:
        return None
    (x, y), (w, h) = measured
    return (round(x), round(y), round(w), round(h))


def _flipped_frame(
    api: dict[str, Any], element: Any, screen_height: int,
) -> tuple[int, int, int, int] | None:
    measured = _position_size(api, element)
    if measured is None:
        return None
    (x, y), (w, h) = measured
    return (round(x), round(screen_height - y - h), round(w), round(h))


def _frames_close(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return all(abs(x - y) <= 2 for x, y in zip(a, b, strict=True))


def ax_window_candidates(
    window_id: int, display_geometry: tuple[int, ...],
) -> tuple[list[AXCandidate], bool]:
    """Enumerate the bound window's live AX tree; returns (candidates, truncated).

    The window element is matched to the Quartz window by frame; the coordinate
    orientation (top-left vs bottom-left origin) is calibrated from that match
    instead of assumed. Candidates carry only observed AX attributes.
    """
    if type(window_id) is not int or window_id <= 0:
        raise ValueError("Invalid window_id")
    quartz = macos._load_quartz()
    pid: int | None = None
    bounds: tuple[int, int, int, int] | None = None
    for window in quartz.CGWindowListCopyWindowInfo(
        quartz.kCGWindowListOptionOnScreenOnly, 0
    ) or []:
        if window.get("kCGWindowNumber") == window_id:
            rect = window["kCGWindowBounds"]
            pid = int(window["kCGWindowOwnerPID"])
            bounds = (int(rect["X"]), int(rect["Y"]),
                      int(rect["Width"]), int(rect["Height"]))
            break
    if pid is None or bounds is None:
        raise ValueError("AX enumeration requires an on-screen Quartz window")
    api = _load_ax()
    app = api["AXUIElementCreateApplication"](pid)
    screen_height = int(display_geometry[4])
    err, ax_windows = api["AXUIElementCopyAttributeValue"](app, "AXWindows", None)
    if err != 0 or ax_windows is None:
        raise RuntimeError(f"AX: cannot list windows (error {err})")
    window_element = None
    flip = False
    for candidate_window in ax_windows:
        direct = _top_left_frame(api, candidate_window, screen_height)
        if direct is not None and _frames_close(direct, bounds):
            window_element, flip = candidate_window, False
            break
        flipped = _flipped_frame(api, candidate_window, screen_height)
        if flipped is not None and _frames_close(flipped, bounds):
            window_element, flip = candidate_window, True
            break
    if window_element is None:
        raise RuntimeError("AX: bound window not found in the accessibility tree")
    convert = _flipped_frame if flip else _top_left_frame
    candidates: list[AXCandidate] = []
    truncated = False
    queue: list[tuple[Any, int]] = [(window_element, 0)]
    while queue:
        if len(candidates) >= MAX_ELEMENTS:
            truncated = True
            break
        element, depth = queue.pop(0)
        role = _string(_attr(api, element, "AXRole"))
        actions = _strings(_attr(api, element, "AXActions"))
        if role and (role in _ADDRESSABLE_ROLES or "AXPress" in actions):
            candidates.append(AXCandidate(
                index=len(candidates) + 1, role=role,
                title=_clean(_attr(api, element, "AXTitle")),
                value=_clean(_attr(api, element, "AXValue")),
                description=_clean(_attr(api, element, "AXDescription")),
                identifier=_clean(_attr(api, element, "AXIdentifier")),
                actions=actions,
                enabled=_flag(_attr(api, element, "AXEnabled")),
                frame=convert(api, element, screen_height),
                element=AXElementRef(element, flip=flip, screen_height=screen_height),
            ))
        if depth < MAX_DEPTH:
            children = _attr(api, element, "AXChildren")
            if children is not None:
                try:
                    child_list = list(children)[:MAX_CHILDREN]
                except TypeError:
                    child_list = []
                queue.extend((child, depth + 1) for child in child_list)
    return candidates, truncated


def ax_refresh_candidate(ref: AXElementRef) -> AXCandidate | None:
    """Re-read a located element; None means stale (destroyed or inaccessible)."""
    api = _load_ax()
    role = _string(_attr(api, ref.native, "AXRole"))
    if not role:
        return None
    convert = _flipped_frame if ref.flip else _top_left_frame
    return AXCandidate(
        index=0, role=role,
        title=_clean(_attr(api, ref.native, "AXTitle")),
        value=_clean(_attr(api, ref.native, "AXValue")),
        description=_clean(_attr(api, ref.native, "AXDescription")),
        identifier=_clean(_attr(api, ref.native, "AXIdentifier")),
        actions=_strings(_attr(api, ref.native, "AXActions")),
        enabled=_flag(_attr(api, ref.native, "AXEnabled")),
        frame=convert(api, ref.native, ref.screen_height),
        element=ref,
    )


def ax_press(ref: AXElementRef) -> None:
    """Perform AXPress on the element; raises on any AX error."""
    err = _load_ax()["AXUIElementPerformAction"](ref.native, "AXPress")
    if err != 0:
        raise RuntimeError(f"AXPress failed with error {err}")


def format_candidates(candidates: list[AXCandidate]) -> str:
    lines = []
    for candidate in candidates:
        parts = [f"{candidate.index}.", f"role={candidate.role}"]
        for key, value in (("title", candidate.title), ("value", candidate.value),
                           ("identifier", candidate.identifier),
                           ("description", candidate.description)):
            if value:
                parts.append(f'{key}="{value}"')
        parts.append("frame=unknown" if candidate.frame is None
                     else f"frame={candidate.frame}")
        if candidate.actions:
            parts.append("actions=[" + ",".join(candidate.actions) + "]")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def ax_selection_payload(
    candidates: list[AXCandidate], target: str, *, truncated: bool = False,
) -> dict[str, Any]:
    """Text-only selection request; no image is uploaded for AX locating."""
    header = ("Candidates (list truncated; some elements are not shown):"
              if truncated else "Candidates:")
    question = (
        f"{header}\n{format_candidates(candidates)}\n\nTarget: {target}\n"
        "Call select once with the 1-based index of the single candidate that "
        "matches the target. status=found for exactly one unambiguous match, "
        "status=not_found when no candidate matches, or status=ambiguous when "
        "several candidates match equally or the choice is uncertain. "
        "Use index=0 when the status is not found."
    )
    function = {
        "name": "select",
        "description": "Report one numbered candidate; no action is executed.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["found", "not_found", "ambiguous"]},
                "index": {"type": "integer", "minimum": 0,
                          "maximum": max(1, len(candidates))},
            },
            "required": ["status", "index"],
            "additionalProperties": False,
        },
    }
    return {
        "messages": [
            {"role": "system",
             "content": "Select the accessibility candidate matching the target."},
            {"role": "user", "content": question},
        ],
        "tools": [{"type": "function", "function": function}],
    }


def parse_ax_selection(raw: str, count: int) -> AXSelection:
    obj = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(obj, dict) or set(obj) != {"status", "index"}:
        raise ValueError("Unexpected selection fields")
    status = obj["status"]
    if status not in ("found", "not_found", "ambiguous"):
        raise ValueError("Invalid selection status")
    index = obj["index"]
    if type(index) is not int:
        raise ValueError("index must be an integer")
    if status != "found":
        if index != 0:
            raise ValueError("Abstention must use index=0")
        return AXSelection(status)
    if not 1 <= index <= count:
        raise ValueError("Selection outside candidate range")
    return AXSelection("found", index)


def parse_ax_selection_response(response: ChatCompletion, count: int) -> AXSelection:
    if len(response.choices) != 1:
        raise GroundingResponseError("invalid_response", "Expected one selection response")
    choice = response.choices[0]
    if choice.finish_reason not in {"tool_calls", "stop"}:
        raise GroundingResponseError(
            "incomplete_response", f"Incomplete selection response: {choice.finish_reason}")
    if choice.message.refusal:
        raise GroundingResponseError("refused_response", "Selection response was refused")
    calls = choice.message.tool_calls or []
    if len(calls) != 1 or calls[0].type != "function" or calls[0].function.name != "select":
        raise GroundingResponseError(
            "invalid_tool_call", "Expected exactly one select function call")
    try:
        return parse_ax_selection(calls[0].function.arguments, count)
    except ValueError as exc:
        raise GroundingResponseError("invalid_selection", str(exc)) from exc


def resolve_frontmost_window() -> int | None:
    """Host-side binding: the frontmost regular app's main on-screen window.

    Models cannot discover CGWindowNumbers from pixels, so AX mode binds the
    observation window here instead of asking the planner for an id.
    """
    appkit: Any = importlib.import_module("AppKit")

    quartz = macos._load_quartz()
    front = appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
    if front is None or front.processIdentifier() == os.getpid():
        return None
    for window in quartz.CGWindowListCopyWindowInfo(
        quartz.kCGWindowListOptionOnScreenOnly, 0
    ) or []:
        if (window.get("kCGWindowLayer") == 0
                and int(window.get("kCGWindowOwnerPID", -1)) == front.processIdentifier()):
            size = window["kCGWindowBounds"]
            if int(size["Width"]) > 50 and int(size["Height"]) > 50:
                return int(window["kCGWindowNumber"])
    return None


def _screen_to_image(observation: Observation, x: float, y: float) -> tuple[float, float]:
    left, top, right, bottom = observation.crop
    width, height = observation.image_size
    return ((x - left) * width / (right - left), (y - top) * height / (bottom - top))


class AXSession(LocateSession):
    """Split-mode session whose locator addresses numbered AX candidates."""

    def __init__(
        self,
        tools: dict[str, Any],
        llms: dict[str, LLM],
        context: SubAgentContext,
        session_id: str,
        ax_action: str,
    ) -> None:
        if ax_action not in ("quartz", "ax_press"):
            raise ValueError("Unknown AX dispatch action")
        super().__init__(tools, llms, None, context, session_id)
        self.ax_action = ax_action
        self.ax_locations: dict[str, AXLocatedTarget] = {}

    def _protocol_name(self) -> str:
        return "ax"

    def _clear_locations(self) -> None:
        super()._clear_locations()
        self.ax_locations.clear()

    def _host_arguments(self, name: str) -> set[str]:
        return {"window_id"} if name == "screenshot" else set()

    async def execute(
        self, name: str, arguments: dict[str, Any], *, feedback: bool = True,
    ) -> ToolResult | str:
        if name == "screenshot" and "window_id" not in arguments:
            window_id = await asyncio.to_thread(resolve_frontmost_window)
            if window_id is not None:
                arguments = {**arguments, "window_id": window_id}
        return await super().execute(name, arguments, feedback=feedback)

    async def _locate(
        self, frame_id: str, target: str, window_id: int | None, backend: str,
        evidence: dict[str, Any],
    ) -> ToolResult:
        self.context.check()
        self._prepare_locate(target, backend)
        evidence["stage"] = "observation_before"
        observation = await self.screenshot.validate(self.session_id, frame_id, window_id)
        if observation.window_id is None:
            raise ValueError("AX locating requires a window-bound frame; re-observe with window_id")
        evidence["stage"] = "enumerate"
        candidates, truncated = await asyncio.to_thread(
            ax_window_candidates, observation.window_id, observation.display_geometry)
        if not candidates:
            raise ValueError("No accessibility candidates in the bound window; stop or re-observe")
        evidence.update(candidate_count=len(candidates), truncated=truncated,
                        window_id=observation.window_id)
        self.context.check()
        evidence.update(stage="request", model=self.llms[backend].model)
        call_id = evidence["call_id"]
        token = grounding_call_id.set(call_id)
        try:
            response = await self.llms[backend].complete_response(
                **ax_selection_payload(candidates, target, truncated=truncated), retry=False)
        except BaseException:
            self._clear_locations()
            self.context.budget.record_unknown(call_id)
            raise
        finally:
            grounding_call_id.reset(token)
        evidence.update(stage="accounting", usage_known=response.usage is not None,
                        response_model=response.model, response_id=response.id,
                        finish_reason=response.choices[0].finish_reason
                        if len(response.choices) == 1 else None)
        if response.usage is None:
            self.context.budget.record_unknown(call_id)
        else:
            self.context.budget.record(
                call_id, response.usage.prompt_tokens, response.usage.completion_tokens
            )
        self.context.observe(
            "grounding_usage",
            call_id=call_id,
            frame_id=frame_id,
            backend=backend,
            model=response.model,
            total_tokens=self.context.budget.total_tokens,
            usage_known=response.usage is not None,
        )
        self.context.check()
        evidence["stage"] = "parse"
        selection = parse_ax_selection_response(response, len(candidates))
        evidence.update(stage="observation_after", reported_status=selection.status,
                        selected_index=selection.index)
        await self.screenshot.validate(self.session_id, frame_id, window_id)
        evidence["stage"] = "postcheck"
        self.context.check()
        result: dict[str, Any] = {"status": selection.status, "frame_id": frame_id}
        if selection.status == "found" and selection.index is not None:
            location_id = uuid.uuid4().hex
            self.ax_locations[location_id] = AXLocatedTarget(
                observation, candidates[selection.index - 1])
            result["location_id"] = location_id
        else:
            self._clear_locations()
        evidence["stage"] = "resolved"
        return ToolResult(content=json.dumps(result))

    def ax_target(self, location_id: object) -> AXLocatedTarget:
        if not isinstance(location_id, str):
            raise ValueError("location_id is required")
        target = self.ax_locations.get(location_id)
        if target is None or target.observation is not self.state.observation:
            raise ValueError("Missing or stale location; observe and locate again")
        return target

    async def _refreshed(self, target: AXLocatedTarget) -> AXCandidate:
        candidate = await asyncio.to_thread(
            ax_refresh_candidate, target.candidate.element)
        if candidate is None:
            raise ValueError("Stale AX element; observe and locate again")
        return candidate

    def _check_pressable(self, candidate: AXCandidate, observation: Observation) -> None:
        # Real controls may accept AXPress without advertising an AXActions
        # attribute (macOS 26 Calculator buttons); PerformAction's error code
        # is the authority, so only geometry is pre-checked here.
        if candidate.frame is None:
            raise ValueError("Element frame unknown; observe again")
        x, y, w, h = candidate.frame
        wx, wy, ww, wh = observation.window_bounds or (0, 0, *observation.screen_size)
        if not (wx <= x and wy <= y and x + w <= wx + ww and y + h <= wy + wh):
            raise ValueError("Element frame is outside the bound window; observe again")

    async def _dispatch_pointer(
        self, name: str, tool: Any, arguments: dict[str, Any], ctx: ToolContext,
    ) -> ToolResult:
        if self.ax_action == "ax_press":
            if name != "click":
                raise ValueError(
                    "ax_press dispatch supports click only; use keyboard tools instead")
            if arguments.get("button", "left") != "left" or arguments.get("clicks", 1) != 1:
                raise ValueError("ax_press click cannot honor button/clicks options")
            target = self.ax_target(arguments.pop("location_id"))
            observation = await self.screenshot.validate(
                self.session_id, target.observation.frame_id, target.observation.window_id)
            candidate = await self._refreshed(target)
            self._check_pressable(candidate, observation)
            try:
                await run_native(ax_press, target.candidate.element)
            except (RuntimeError, OSError) as exc:
                raise ValueError(f"AXPress failed: {exc}") from exc
            label = candidate.role + (f' "{candidate.title}"' if candidate.title else "")
            return ToolResult(content=f"click: AXPress on {label}", display="AXPress dispatched")
        target = self.ax_target(arguments.pop("location_id"))
        observation = await self.screenshot.validate(
            self.session_id, target.observation.frame_id, target.observation.window_id)
        start = await self._refreshed(target)
        end: AXCandidate | None = None
        if name == "drag":
            end = await self._refreshed(
                self.ax_target(arguments.pop("end_location_id")))
        if start.frame is None:
            raise ValueError("Element frame unknown; observe again")
        sx, sy = start.frame[0] + start.frame[2] / 2, start.frame[1] + start.frame[3] / 2
        if name == "drag":
            if end is None or end.frame is None:
                raise ValueError("Element frame unknown; observe again")
            ex, ey = end.frame[0] + end.frame[2] / 2, end.frame[1] + end.frame[3] / 2
            x1, y1 = _screen_to_image(observation, sx, sy)
            x2, y2 = _screen_to_image(observation, ex, ey)
            coordinates: dict[str, float] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        else:
            x, y = _screen_to_image(observation, sx, sy)
            coordinates = {"x": x, "y": y}
        arguments.update(
            coordinate_space="image",
            frame_id=observation.frame_id,
            window_id=observation.window_id,
            **coordinates,
        )
        return await tool.execute(ctx=ctx, **arguments)

__all__ = [
    "AXCandidate", "AXElementRef", "AXLocatedTarget", "AX_PROMPT", "AXSession",
    "AXSelection", "ax_press", "ax_refresh_candidate", "ax_selection_payload",
    "ax_window_candidates", "format_candidates", "parse_ax_selection",
    "parse_ax_selection_response",
]
