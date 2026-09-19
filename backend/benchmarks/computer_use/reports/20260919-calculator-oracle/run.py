"""Local-only Calculator oracle: AX positions -> production screenshot/click -> AX result."""
import asyncio
import base64
import io
import json
import subprocess
from pathlib import Path

import Quartz
from PIL import Image

from tank_backend.benchmarks.calc_validator import read_calculator, reset_calculator
from tank_backend.core.content import ImageBlock
from tank_backend.tools.computer_use_macos import ClickTool, ScreenshotTool

BUTTONS = '''on scanNode(e, depth)
 tell application "System Events"
  set txt to ""
  try
   set ident to value of attribute "AXIdentifier" of e
   if ident is in {"Seven", "Multiply", "Eight", "Equals"} then
    set p to position of e
    set z to size of e
    set txt to ident & "|" & (item 1 of p) & "|" & (item 2 of p) & "|" & (item 1 of z) & "|" & (item 2 of z) & linefeed
   end if
  end try
  if depth < 10 then
   try
    repeat with child in UI elements of e
     set txt to txt & my scanNode(child, depth + 1)
    end repeat
   end try
  end if
  return txt
 end tell
end scanNode
tell application "System Events" to tell process "Calculator"
 if not frontmost then error "Calculator lost focus"
 set win to window 1
end tell
return scanNode(win, 0)
'''


async def main():
    report = {"screen_recording": bool(Quartz.CGPreflightScreenCaptureAccess()),
              "input_control": bool(Quartz.CGPreflightPostEventAccess()), "trials": []}
    assert report["screen_recording"] and report["input_control"]
    assert await asyncio.to_thread(reset_calculator)
    result = await asyncio.to_thread(subprocess.run, ["osascript", "-e", BUTTONS],
                                     capture_output=True, text=True, timeout=40, check=True)
    buttons = {}
    for line in result.stdout.strip().splitlines():
        label, *coords = line.split("|")
        assert label not in buttons and len(coords) == 4
        buttons[label] = list(map(int, coords))
    assert set(buttons) == {"Seven", "Multiply", "Eight", "Equals"}
    report["buttons"] = buttons
    initial_mouse = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    try:
        for trial in range(3):
            assert await asyncio.to_thread(reset_calculator)
            shot = await ScreenshotTool().execute()
            assert not shot.error and isinstance(shot.content, list)
            block = next(p for p in shot.content if isinstance(p, ImageBlock))
            img = Image.open(io.BytesIO(base64.b64decode(block.source.split(",", 1)[1])))
            # Actual desktop pixels stay in memory, never archived or sent over HTTP.
            row = {"trial": trial, "size": img.size, "clicks": []}
            report["trials"].append(row)
            for name in ("Seven", "Multiply", "Eight", "Equals"):
                # A read also verifies Calculator is visible and frontmost.
                assert await asyncio.to_thread(read_calculator)
                x, y, w, h = buttons[name]
                center = (x+w/2, y+h/2)
                norm = [round(center[0]*1000/img.width), round(center[1]*1000/img.height)]
                click = await ClickTool().execute(x=norm[0], y=norm[1])
                assert not click.error
                await asyncio.sleep(.15)
                cursor = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
                row["clicks"].append({"button": name, "center": center, "normalized": norm,
                    "cursor": [cursor.x, cursor.y], "tool_result": click.content})
                Path(__file__).with_name("results.json").write_text(json.dumps(report, indent=2))
                print(json.dumps(row["clicks"][-1]), flush=True)
                assert x <= cursor.x <= x+w and y <= cursor.y <= y+h
            row["display"] = await asyncio.to_thread(read_calculator)
            row["passed"] = row["display"].get("expression") in {"7×8", "7*8"} and row["display"].get("result") == "56"
            Path(__file__).with_name("results.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(row), flush=True)
            assert row["passed"]
    finally:
        Quartz.CGWarpMouseCursorPosition(initial_mouse)


asyncio.run(main())
