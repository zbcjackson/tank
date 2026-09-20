"""Opt-in real macOS calibration; only click targets in our own test window.

Run: uv run python scripts/calibrate_macos_coordinates.py --output /tmp/tank-calibration
No screenshots are sent to a model. Requires Screen Recording and Accessibility.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import importlib
import io
import json
import threading
import time
from pathlib import Path

from PIL import Image

from tank_backend.core.content import ImageBlock, TextBlock
from tank_backend.tools.base import ToolContext
from tank_backend.tools.computer_frame import FrameState, FrameTool
from tank_backend.tools.computer_use_macos import ClickTool, ScreenshotTool


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--coordinate-space", choices=("legacy", "image"), default="legacy")
    parser.add_argument("--window", action="store_true", help="Bind image mode to the test window")
    args = parser.parse_args()
    if args.window and args.coordinate_space != "image":
        parser.error("--window requires --coordinate-space image")
    args.output.mkdir(parents=True)
    quartz = importlib.import_module("Quartz")
    appkit = importlib.import_module("AppKit")
    objc = importlib.import_module("objc")
    from PyObjCTools import AppHelper

    display = quartz.CGMainDisplayID()
    bounds = quartz.CGDisplayBounds(display)
    mode = quartz.CGDisplayCopyDisplayMode(display)
    geometry = {
        "display_id": display,
        "logical_size": [bounds.size.width, bounds.size.height],
        "backing_size": [quartz.CGDisplayModeGetPixelWidth(mode),
                         quartz.CGDisplayModeGetPixelHeight(mode)],
        "screen_recording": bool(quartz.CGPreflightScreenCaptureAccess()),
        "input_control": bool(quartz.CGPreflightPostEventAccess()),
    }
    (args.output / "geometry.json").write_text(json.dumps(geometry, indent=2))
    if not geometry["screen_recording"] or not geometry["input_control"]:
        raise SystemExit("Calibration blocked: grant Screen Recording and Accessibility first")

    targets = [(x, y) for y in (70, 250, 430) for x in (80, 400, 720)]
    events: list[dict] = []
    delivered: list[dict] = []

    class CalibrationView(appkit.NSView):
        def isFlipped(self):
            return True

        def acceptsFirstResponder(self):
            return True

        def drawRect_(self, rect):
            appkit.NSColor.whiteColor().setFill()
            appkit.NSRectFill(self.bounds())
            for index, (x, y) in enumerate(targets):
                appkit.NSColor.redColor().setFill()
                appkit.NSBezierPath.bezierPathWithOvalInRect_(
                    appkit.NSMakeRect(x - 12, y - 12, 24, 24),
                ).fill()
                label = appkit.NSString.stringWithString_(f"Target {index + 1}")
                label.drawAtPoint_withAttributes_((x - 28, y + 18), {
                    appkit.NSFontAttributeName: appkit.NSFont.systemFontOfSize_(14),
                    appkit.NSForegroundColorAttributeName: appkit.NSColor.blackColor(),
                })

        def mouseDown_(self, event):
            point = self.convertPoint_fromView_(event.locationInWindow(), None)
            screen = quartz.CGEventGetLocation(event.CGEvent())
            events.append({
                "view_point": [point.x, point.y], "event_point": [screen.x, screen.y],
                "hit": next((i for i, (x, y) in enumerate(targets)
                             if (x - point.x) ** 2 + (y - point.y) ** 2 <= 12 ** 2), None),
            })

    app = appkit.NSApplication.sharedApplication()
    original_front = appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
    app.setActivationPolicy_(appkit.NSApplicationActivationPolicyRegular)
    window = appkit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        appkit.NSMakeRect(100, 150, 800, 500),
        appkit.NSWindowStyleMaskTitled | appkit.NSWindowStyleMaskClosable,
        appkit.NSBackingStoreBuffered, False,
    )
    window.setTitle_("Tank coordinate calibration — nine test targets")
    view = CalibrationView.alloc().initWithFrame_(appkit.NSMakeRect(0, 0, 800, 500))
    window.setContentView_(view)
    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)

    def observe(event):
        point = event.locationInWindow()
        delivered.append({"type": int(event.type()), "window": event.windowNumber(),
                          "point": [point.x, point.y], "timestamp": time.time()})
        return event

    monitor = appkit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
        appkit.NSEventMaskLeftMouseDown | appkit.NSEventMaskLeftMouseUp, observe,
    )
    screen_targets = []
    for point in targets:
        base = view.convertPoint_toView_(point, None)
        global_point = window.convertPointToScreen_(base)
        screen_targets.append((global_point.x, bounds.size.height - global_point.y))
    initial_mouse = quartz.CGEventGetLocation(quartz.CGEventCreate(None))

    frame_state = FrameState()
    frame_context = ToolContext(session_id="local-calibration")
    frame_shot = FrameTool(ScreenshotTool(), frame_state)
    frame_click = FrameTool(ClickTool(), frame_state)

    async def calibrate() -> None:
        await asyncio.sleep(1)
        rows = []
        for index, ((x, y), local) in enumerate(zip(screen_targets, targets, strict=True)):
            if not window.isKeyWindow():
                raise RuntimeError("Calibration window lost focus; stopped before next click")
            metadata = None
            if args.coordinate_space == "image":
                shot = await frame_shot.execute(
                    coordinate_space="image", ctx=frame_context,
                    **({"window_id": window.windowNumber()} if args.window else {}),
                )
            else:
                shot = await ScreenshotTool().execute()
            if isinstance(shot, str):
                raise RuntimeError(shot)
            if shot.error or not isinstance(shot.content, list):
                raise RuntimeError(f"Screenshot failed: {shot.display}")
            block = next(b for b in shot.content if isinstance(b, ImageBlock))
            png = base64.b64decode(block.source.split(",", 1)[1])
            point_x, point_y = x, y
            if args.coordinate_space == "image":
                text = next(b.text for b in shot.content if isinstance(b, TextBlock))
                metadata = json.loads(text[text.index("{"):])
                left, top, right, bottom = metadata["crop"]
                image_w, image_h = metadata["image_size"]
                point_x = (x - left) * image_w / (right - left)
                point_y = (y - top) * image_h / (bottom - top)
            with Image.open(io.BytesIO(png)) as image:
                size = image.size
                color = image.convert("RGB").getpixel((round(point_x), round(point_y)))
                assert isinstance(color, tuple) and len(color) == 3
            # Independently verify the visible target before issuing any input.
            if not (color[0] > 200 and color[1] < 80 and color[2] < 80):
                raise RuntimeError(f"Target {index} not visible at expected screenshot location")
            if index == 0:
                (args.output / "screen.png").write_bytes(png)
            normalized = (round(x / size[0] * 1000), round(y / size[1] * 1000))
            before = len(events)
            before_delivered = len(delivered)
            if metadata is not None:
                result = await frame_click.execute(
                    coordinate_space="image", frame_id=metadata["frame_id"], ctx=frame_context,
                    x=point_x, y=point_y,
                )
            else:
                result = await ClickTool().execute(x=normalized[0], y=normalized[1])
            if isinstance(result, str):
                raise RuntimeError(result)
            if result.error:
                raise RuntimeError(str(result.content))
            for _ in range(20):
                if len(events) > before and any(
                    event["type"] == appkit.NSEventTypeLeftMouseUp
                    for event in delivered[before_delivered:]
                ):
                    break
                await asyncio.sleep(0.05)
            actual = quartz.CGEventGetLocation(quartz.CGEventCreate(None))
            received = events[before:]
            row = {"target": index, "expected_screen": [x, y], "expected_view": local,
                   "normalized": normalized, "screenshot_size": size,
                   "observation": metadata, "timestamp": time.time(),
                   "actual_mouse": [actual.x, actual.y], "received": received,
                   "delivered_events": delivered[before_delivered:],
                   "error_points": [actual.x - x, actual.y - y],
                   "hit": len(received) == 1 and received[0]["hit"] == index,
                   "released": any(event["type"] == appkit.NSEventTypeLeftMouseUp
                                   for event in delivered[before_delivered:])}
            rows.append(row)
            (args.output / "results.json").write_text(json.dumps(rows, indent=2))
            print(json.dumps(row), flush=True)
            if (not row["hit"] or not row["released"]
                    or (metadata is not None and max(abs(v) for v in row["error_points"]) > 1)):
                raise RuntimeError("Target did not receive the expected click; stopping")
            await asyncio.sleep(0.1)

    def finish() -> None:
        window.close()
        if original_front is not None:
            original_front.activateWithOptions_(appkit.NSApplicationActivateIgnoringOtherApps)
        app.stop_(None)
        # Wake NSApplication's pending nextEvent call so run() can return.
        wake = appkit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            appkit.NSEventTypeApplicationDefined, (0, 0), 0, 0, 0, None, 0, 0, 0,
        )
        app.postEvent_atStart_(wake, True)

    def worker() -> None:
        with objc.autorelease_pool():
            try:
                asyncio.run(calibrate())
            except Exception as exc:
                (args.output / "error.txt").write_text(str(exc))
                print(f"Calibration failed: {exc}", flush=True)
            finally:
                quartz.CGWarpMouseCursorPosition(initial_mouse)
                AppHelper.callAfter(finish)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    app.run()
    appkit.NSEvent.removeMonitor_(monitor)
    thread.join(timeout=3)
    restored_mouse = quartz.CGEventGetLocation(quartz.CGEventCreate(None))
    cleanup = {"window_closed": not window.isVisible(),
               "cursor_restored": abs(restored_mouse.x - initial_mouse.x) <= 1
               and abs(restored_mouse.y - initial_mouse.y) <= 1}
    (args.output / "cleanup.json").write_text(json.dumps(cleanup, indent=2))
    if not all(cleanup.values()):
        raise SystemExit("Calibration cleanup unconfirmed")
    if (args.output / "error.txt").exists():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
