"""M6 item 1: re-verify the M2 input/display oracle on the real Calculator.

Local only — no model requests, no screenshot upload. Real key presses go
through the production KeyPressTool; the display is read back via AX
(calc_validator) and independently captured through the M2 window frame tool.
"""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
import time
from pathlib import Path

import AppKit
import Quartz

from tank_backend.benchmarks.calc_validator import read_calculator, reset_calculator
from tank_backend.benchmarks.runner import (
    pin_ascii_input_source,
    restore_saved_input_source,
    save_current_input_source,
)
from tank_backend.core.content import ImageBlock
from tank_backend.tools.base import ToolContext
from tank_backend.tools.computer_frame import FrameState, FrameTool
from tank_backend.tools.computer_use_macos import KeyPressTool, ScreenshotTool

OUT = Path(__file__).parent


async def main() -> None:
    result: dict = {"started_at": time.time()}
    save_current_input_source()
    try:
        pin_ascii_input_source()
        result["reset"] = reset_calculator()
        if not result["reset"]:
            raise RuntimeError("Calculator reset failed")
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to tell process "Calculator" '
             "to set position of window 1 to {600, 100}"],
            check=True, capture_output=True, timeout=20,
        )
        presses = []
        for key in ("7", "shift+8", "8", "enter"):
            pressed_at = time.time()
            action = await KeyPressTool().execute(keys=key)
            presses.append({"key": key, "at": pressed_at,
                            "error": bool(action.error),
                            "display": str(action.display)})
            if action.error:
                raise RuntimeError(str(action.content))
        result["key_presses"] = presses
        await asyncio.sleep(0.5)
        result["display"] = read_calculator()
        result["oracle_passed"] = (
            result["display"].get("expression") in ("7×8", "7*8")
            and result["display"].get("result") == "56"
        )
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
        window = next(w for w in windows
                      if w.get("kCGWindowOwnerName") == "Calculator"
                      and w.get("kCGWindowLayer") == 0)
        shot = await FrameTool(ScreenshotTool(), FrameState()).execute(
            coordinate_space="image", window_id=int(window["kCGWindowNumber"]),
            ctx=ToolContext(session_id="m6-oracle"),
        )
        if shot.error:
            raise RuntimeError(str(shot.content))
        image = next(b for b in shot.content if isinstance(b, ImageBlock))
        (OUT / "calculator.png").write_bytes(
            base64.b64decode(image.source.split(",", 1)[1]))
        text = next(b.text for b in shot.content if not isinstance(b, ImageBlock))
        result["frame_observation"] = json.loads(text[text.index("{"):])
    finally:
        restore_saved_input_source()
        subprocess.run(
            ["osascript", "-e", 'tell application "Calculator" to quit'],
            capture_output=True, timeout=20)
        await asyncio.sleep(0.3)
        result["calculator_closed"] = not any(
            a.bundleIdentifier() == "com.apple.calculator"
            for a in AppKit.NSWorkspace.sharedWorkspace().runningApplications())
        result["pressed_mouse_buttons"] = [
            i for i in range(3)
            if Quartz.CGEventSourceButtonState(
                Quartz.kCGEventSourceStateCombinedSessionState, i)]
        result["pressed_keys"] = [
            i for i in range(128)
            if Quartz.CGEventSourceKeyState(
                Quartz.kCGEventSourceStateCombinedSessionState, i)]
        result["finished_at"] = time.time()
        (OUT / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps({k: result.get(k) for k in (
            "reset", "display", "oracle_passed", "calculator_closed",
            "pressed_mouse_buttons", "pressed_keys")}, ensure_ascii=False))
    if (not result.get("oracle_passed") or not result["calculator_closed"]
            or result["pressed_mouse_buttons"] or result["pressed_keys"]):
        raise RuntimeError("Oracle or cleanup failed")


asyncio.run(main())
