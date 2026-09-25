"""M7 batch 2: real-machine AX branch boundary verification on Calculator.

Verifies on the real desktop, without any model request or screenshot upload:
- quartz dispatch: AX frame center through the production AXSession/M2 path,
  with the dispatched Quartz point and the independent AX display read-back;
- ax_press dispatch: AXUIElementPerformAction through the production session;
- stale reference: element destroyed after locate -> refused, zero input;
- window mismatch: window moved after binding -> refused, zero input;
- input cleanliness after the run (no pressed keys/buttons).

Controlled actions are limited to a Calculator window positioned by this
script; the previous frontmost app is restored at the end.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import AppKit

from tank_backend.agents.subagent import SubAgentAuthorization, SubAgentBudget, SubAgentContext
from tank_backend.benchmarks.calc_validator import read_calculator
from tank_backend.tools import computer_ax
from tank_backend.tools import computer_use_macos as macos
from tank_backend.tools.computer_ax import AXLocatedTarget
from tank_backend.tools.computer_locate import LocateSession, LocateTool
from tank_backend.tools.groups import ComputerUseToolGroup
from tank_backend.tools.manager import ToolManager

OUT = Path(__file__).parent


class Observer:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def on_event(self, kind: str, metadata: dict[str, Any]) -> None:
        self.events.append((kind, metadata))


def calculator_window() -> dict[str, Any] | None:
    quartz = macos._load_quartz()
    for window in quartz.CGWindowListCopyWindowInfo(
        quartz.kCGWindowListOptionOnScreenOnly, 0
    ) or []:
        if (window.get("kCGWindowOwnerName") == "Calculator"
                and window.get("kCGWindowLayer") == 0):
            return dict(window)
    return None


def wait_calculator(timeout: float = 12.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        window = calculator_window()
        if window is not None:
            return window
        time.sleep(0.3)
    raise RuntimeError("Calculator window did not appear")


def position(x: int, y: int) -> None:
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to tell process "Calculator" '
         f"to set position of window 1 to {{{x}, {y}}}"],
        check=True, capture_output=True, timeout=20)


def reset_display() -> None:
    subprocess.run(
        ["osascript", "-e", 'tell application "Calculator" to activate', "-e",
         "delay 0.4", "-e",
         'tell application "System Events" to key code 53', "-e",
         'tell application "System Events" to key code 53'],
        check=True, capture_output=True, timeout=20)
    time.sleep(0.3)
    if read_calculator().get("result") != "0":
        raise RuntimeError("Calculator did not reset to 0")


def make_session() -> tuple[LocateSession, Observer]:
    manager = ToolManager.__new__(ToolManager)
    manager.tools = {t.get_info().name: t for t in ComputerUseToolGroup()._create_macos_tools()}
    manager.tool_metadata = {n: t.get_metadata() for n, t in manager.tools.items()}
    manager._media_store = manager._bus = None
    manager.set_session_id("m7-boundaries")
    observer = Observer()
    context = SubAgentContext(
        SubAgentAuthorization(frozenset({"desktop"})), SubAgentBudget(limit=100000),
        asyncio.Event(), observer=observer)
    session = computer_ax.AXSession(
        manager.tools, {"primary": None}, context, "m7-boundaries", "quartz")
    return session, observer


def find_candidate(session: LocateSession, description: str):
    from tank_backend.tools.computer_frame import _geometry

    observation = session.state.observation
    assert observation is not None and observation.window_id is not None
    candidates, truncated = computer_ax.ax_window_candidates(
        observation.window_id, observation.display_geometry or _geometry())
    for candidate in candidates:
        if (candidate.description == description or candidate.title == description
                or candidate.identifier == description):
            return candidate, truncated, len(candidates)
    raise RuntimeError(f"no candidate labeled {description!r}")


async def main() -> None:
    result: dict[str, Any] = {"started_at": time.time()}
    original = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    launched = calculator_window() is None
    if launched:
        subprocess.run(["open", "-a", "Calculator"], check=True, capture_output=True, timeout=30)
    try:
        window = wait_calculator()
        result["window_id"] = int(window["kCGWindowNumber"])
        position(600, 100)
        reset_display()
        session, observer = make_session()

        # --- quartz dispatch on the "7" button -----------------------------
        shot = await LocateTool(session, "screenshot").execute(window_id=result["window_id"])
        assert isinstance(shot, object) and not getattr(shot, "error", True), shot
        seven, truncated, total = find_candidate(session, "7")
        result["candidates_total"] = total
        result["truncated"] = truncated
        result["seven_frame"] = seven.frame
        location_id = "m7-quartz-7"
        session.ax_locations[location_id] = AXLocatedTarget(session.state.observation, seven)
        click = await LocateTool(session, "click").execute(location_id=location_id)
        content = str(getattr(click, "content", click))
        match = re.search(r"Quartz \((\d+), (\d+)\)", content)
        result["quartz_click_error"] = bool(getattr(click, "error", True))
        result["quartz_dispatched_point"] = (
            [int(match.group(1)), int(match.group(2))] if match else None)
        time.sleep(0.5)
        result["display_after_quartz"] = read_calculator()

        # --- ax_press dispatch on the "8" button ---------------------------
        shot2 = await LocateTool(session, "screenshot").execute(window_id=result["window_id"])
        assert isinstance(shot2, object) and not getattr(shot2, "error", True), shot2
        eight, _, _ = find_candidate(session, "8")
        result["eight_frame"] = eight.frame
        location_id = "m7-press-8"
        session.ax_locations[location_id] = AXLocatedTarget(session.state.observation, eight)
        click2 = await LocateTool(session, "click").execute(location_id=location_id)
        result["ax_press_error"] = bool(getattr(click2, "error", True))
        result["ax_press_content"] = str(getattr(click2, "content", click2))
        time.sleep(0.5)
        result["display_after_press"] = read_calculator()

        # --- stale reference: destroy the element, then dispatch -----------
        shot3 = await LocateTool(session, "screenshot").execute(window_id=result["window_id"])
        assert isinstance(shot3, object) and not getattr(shot3, "error", True), shot3
        five, _, _ = find_candidate(session, "5")
        location_id = "m7-stale-5"
        session.ax_locations[location_id] = AXLocatedTarget(session.state.observation, five)
        subprocess.run(["osascript", "-e", 'tell application "Calculator" to quit'],
                       capture_output=True, timeout=8)
        subprocess.run(["killall", "Calculator"], capture_output=True, timeout=10)
        time.sleep(0.8)
        result["stale_refresh_returns_none"] = (
            computer_ax.ax_refresh_candidate(five.element) is None)
        stale = await LocateTool(session, "click").execute(location_id=location_id)
        result["stale_refusal"] = str(getattr(stale, "content", stale))
        result["stale_refused"] = bool(getattr(stale, "error", False))

        # --- window mismatch: move the window after binding ---------------
        subprocess.run(["open", "-a", "Calculator"], capture_output=True, timeout=30)
        window = wait_calculator()
        result["window_id_after_relaunch"] = int(window["kCGWindowNumber"])
        position(600, 100)
        reset_display()
        session2, _ = make_session()
        shot4 = await LocateTool(session2, "screenshot").execute(
            window_id=result["window_id_after_relaunch"])
        assert isinstance(shot4, object) and not getattr(shot4, "error", True), shot4
        digit, _, _ = find_candidate(session2, "9")
        location_id = "m7-moved-9"
        session2.ax_locations[location_id] = AXLocatedTarget(session2.state.observation, digit)
        position(650, 120)
        moved = await LocateTool(session2, "click").execute(location_id=location_id)
        result["moved_refusal"] = str(getattr(moved, "content", moved))
        result["moved_refused"] = bool(getattr(moved, "error", False))
        time.sleep(0.3)
        result["display_after_moved_refusal"] = read_calculator()
        result["dispatch_events"] = [
            {"kind": kind, "name": meta.get("name"), "succeeded": meta.get("succeeded")}
            for kind, meta in observer.events if kind == "desktop_dispatch"]
    finally:
        subprocess.run(["osascript", "-e", 'tell application "Calculator" to quit'],
                       capture_output=True, timeout=8)
        subprocess.run(["killall", "Calculator"], capture_output=True, timeout=10)
        time.sleep(0.5)
        quartz = macos._load_quartz()
        result["pressed_keys"] = [
            i for i in range(128)
            if quartz.CGEventSourceKeyState(
                quartz.kCGEventSourceStateCombinedSessionState, i)]
        result["pressed_mouse_buttons"] = [
            i for i in range(3)
            if quartz.CGEventSourceButtonState(
                quartz.kCGEventSourceStateCombinedSessionState, i)]
        result["calculator_closed"] = calculator_window() is None
        original.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.3)
        result["finished_at"] = time.time()
        (OUT / "boundaries.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps({k: result.get(k) for k in (
            "candidates_total", "seven_frame", "quartz_dispatched_point",
            "display_after_quartz", "display_after_press", "ax_press_error",
            "stale_refresh_returns_none", "stale_refusal", "moved_refusal",
            "display_after_moved_refusal", "pressed_keys", "pressed_mouse_buttons",
            "calculator_closed")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
