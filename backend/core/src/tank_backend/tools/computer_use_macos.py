"""Computer-use tools — screenshot capture and host UI automation (macOS).

Provides six tools that let the main ChatAgent control the host desktop:
  - screenshot: capture screen (returned directly for the agent to analyze)
  - click: mouse click at (x, y)
  - type_text: type a string at the cursor
  - key_press: press key combinations
  - scroll: scroll wheel at position
  - mouse_move: move cursor without clicking

macOS implementation uses:
  - Screenshot: screencapture CLI (requires Screen Recording permission)
  - Input: CGEvent via pyobjc-framework-Quartz (one-time Accessibility permission)
  - App control: AppleScript for activate/launch (built-in osascript)

Requires: pip install pyobjc-framework-Quartz
One-time setup: Grant Screen Recording and Accessibility to the host app
(e.g. Paseo or Terminal) in System Settings → Privacy & Security.
"""

from __future__ import annotations

import base64
import importlib
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ..core.content import ImageBlock, TextBlock
from .base import BaseTool, ToolInfo, ToolMetadata, ToolParameter, ToolResult
from .computer_native import run_native
from .computer_use_common import (
    COORDINATE_NOTE,
    COORDINATE_X_DESCRIPTION,
    COORDINATE_Y_DESCRIPTION,
    REGION_DESCRIPTION,
    click_schema,
    crop_and_upscale,
    normalize_keys,
    normalize_point,
    parse_region,
    region_note,
)

logger = logging.getLogger(__name__)


def _load_quartz() -> Any:
    """PyObjC exports CoreGraphics symbols dynamically, without static stubs."""
    return importlib.import_module("Quartz")


# ---------------------------------------------------------------------------
# Display topology (multi-monitor)
# ---------------------------------------------------------------------------

# Cap for CGGetActiveDisplayList; real desktops stay far below this.
_MAX_DISPLAYS = 16


def _active_displays() -> tuple[tuple[int, ...], ...]:
    """Active displays as ``(id, ox, oy, w_pts, h_pts, pw_px, ph_px)`` tuples.

    Global CGEvent coordinates are display-local points plus the display
    origin ``(ox, oy)``. The main display always sits at the origin — that
    invariant identifies it without a second Quartz round-trip. Entries are
    sorted by id because CGGetActiveDisplayList order is unspecified.
    Raises when the topology is not usable (missing main, shifted main,
    non-positive geometry).
    """
    Quartz = _load_quartz()

    err, ids, count = Quartz.CGGetActiveDisplayList(_MAX_DISPLAYS, None, None)
    if err or not count:
        raise RuntimeError(f"CGGetActiveDisplayList failed: err={err} count={count}")
    entries: list[tuple[int, ...]] = []
    for display in tuple(ids)[:int(count)]:
        bounds = Quartz.CGDisplayBounds(display)
        mode = Quartz.CGDisplayCopyDisplayMode(display)
        entry = (
            int(display),
            int(bounds[0][0]), int(bounds[0][1]),
            int(bounds[1][0]), int(bounds[1][1]),
            int(Quartz.CGDisplayModeGetPixelWidth(mode)),
            int(Quartz.CGDisplayModeGetPixelHeight(mode)),
        )
        ox, oy, w, h, pw, ph = entry[1:]
        if w <= 0 or h <= 0 or pw <= 0 or ph <= 0:
            raise ValueError(f"Display {entry[0]} has invalid geometry {entry[1:]}")
        entries.append(entry)
    if not any((e[1], e[2]) == (0, 0) for e in entries):
        raise ValueError("No display at origin (0,0); main display missing")
    return tuple(sorted(entries))


def _display_geometry(
    display: int, displays: tuple[tuple[int, ...], ...] | None = None,
) -> tuple[int, ...]:
    """One display's geometry tuple; raises listing active displays if unknown."""
    if displays is None:
        displays = _active_displays()
    for entry in displays:
        if entry[0] == display:
            return entry
    listing = ", ".join(str(e[0]) for e in displays) or "none"
    raise ValueError(f"Unknown display {display}; active displays: {listing}")


def _main_geometry(displays: tuple[tuple[int, ...], ...]) -> tuple[int, ...]:
    """The origin-anchored (main) display entry of a validated topology."""
    return next(e for e in displays if (e[1], e[2]) == (0, 0))


def _displays_note(
    displays: tuple[tuple[int, ...], ...], captured_id: int | None,
) -> str:
    """Multi-display guidance appended to screenshot text; empty when single."""
    if len(displays) <= 1:
        return ""
    listing = "; ".join(
        f"id={e[0]}{' (main)' if (e[1], e[2]) == (0, 0) else ''} "
        f"{e[3]}x{e[4]} at ({e[1]},{e[2]})"
        for e in displays
    )
    shown = captured_id if captured_id is not None else "main"
    return (
        f" DISPLAYS: {listing}. This image shows display {shown}. Coordinate "
        "tools (click, scroll, mouse_move, drag) accept display=<id>; the "
        "default is the display of the most recent screenshot."
    )


# ---------------------------------------------------------------------------
# Screenshot capture (macOS)
# ---------------------------------------------------------------------------

def _capture_screenshot_macos(
    *, include_cursor: bool = True, display: int | None = None,
) -> bytes:
    """Capture one display and return PNG bytes scaled to point-resolution.

    ``display=None`` captures the main display with ``-m`` (the calibrated
    legacy path). An explicit CGDirectDisplayID captures exactly that display
    via a global-coordinate ``-R`` rect — ``screencapture -D`` takes a
    1-based index whose ordering is undocumented, so it is not usable for
    identity-based selection.

    macOS screencapture produces backing-resolution images (2x on Retina),
    but CGEvent uses point coordinates. We resize the screenshot to match
    point-space so the vision model returns coordinates that map directly
    to CGEvent.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    try:
        displays = _active_displays()
        geometry = (
            _display_geometry(display, displays) if display is not None
            else _main_geometry(displays)
        )
        rect = ["-m"] if display is None else [
            f"-R{geometry[1]},{geometry[2]},{geometry[3]},{geometry[4]}"
        ]
        result = subprocess.run(
            ["screencapture", "-x", *(["-C"] if include_cursor else []), *rect, tmp_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"screencapture failed: {result.stderr}")

        if geometry[5] > geometry[3]:
            # Downscale to point-resolution so vision model coordinates
            # map directly to CGEvent points
            result2 = subprocess.run(
                ["sips", "--resampleWidth", str(geometry[3]), tmp_path],
                capture_output=True, text=True, timeout=10,
            )
            if result2.returncode != 0:
                raise RuntimeError(f"sips resize failed: {result2.stderr}")

        png_bytes = Path(tmp_path).read_bytes()
        # A successful command is not enough: the image must really match
        # the display's logical coordinate space (including its height).
        import io

        from PIL import Image

        expected = (geometry[3], geometry[4])
        with Image.open(io.BytesIO(png_bytes)) as image:
            if image.size != expected:
                raise RuntimeError(
                    f"screenshot dimensions {image.size} do not match logical "
                    f"display {geometry[0]} size {expected}"
                )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return png_bytes


# ---------------------------------------------------------------------------
# Input injection via CGEvent (pyobjc-framework-Quartz)
# ---------------------------------------------------------------------------

def _click_macos(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    """Click at coordinates using CGEvent."""
    Quartz = _load_quartz()

    point = Quartz.CGPointMake(x, y)

    if button == "right":
        down_type = Quartz.kCGEventRightMouseDown
        up_type = Quartz.kCGEventRightMouseUp
        btn = Quartz.kCGMouseButtonRight
    elif button == "middle":
        down_type = Quartz.kCGEventOtherMouseDown
        up_type = Quartz.kCGEventOtherMouseUp
        btn = Quartz.kCGMouseButtonCenter
    else:
        down_type = Quartz.kCGEventLeftMouseDown
        up_type = Quartz.kCGEventLeftMouseUp
        btn = Quartz.kCGMouseButtonLeft

    for i in range(clicks):
        down = Quartz.CGEventCreateMouseEvent(None, down_type, point, btn)
        up = Quartz.CGEventCreateMouseEvent(None, up_type, point, btn)
        # Set click count for double/triple click recognition
        Quartz.CGEventSetIntegerValueField(
            down, Quartz.kCGMouseEventClickState, i + 1,
        )
        Quartz.CGEventSetIntegerValueField(
            up, Quartz.kCGMouseEventClickState, i + 1,
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        time.sleep(0.02)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        if i < clicks - 1:
            time.sleep(0.05)


_KEYSTROKE_SAFE = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "
)


def _ascii_input_source() -> bool:
    """Read the active input source without changing the user's input method.

    The Carbon TIS query runs in a short-lived helper process: calling it
    in-process off the main thread trips a dispatch queue assertion
    (SIGTRAP, observed live during the M6 terminal-write batch). Any helper
    failure is conservative: report non-ASCII so typing takes the paste path.
    """
    import json as _json
    import sys as _sys

    helper = Path(__file__).resolve().parents[1] / "benchmarks" / "_ime_native.py"
    try:
        result = subprocess.run(
            [_sys.executable, str(helper)],
            input=_json.dumps({"operation": "ascii"}),
            capture_output=True, text=True, timeout=5,
        )
        payload = _json.loads(result.stdout)
        return bool(payload.get("ok") and payload.get("ascii"))
    except (OSError, ValueError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        return False


def _type_macos(text: str, mode: str = "auto") -> str:
    """Type text on macOS.

    Plain alphanumeric text with an ASCII-capable input source uses
    AppleScript keystroke (fast). An IME can rewrite even ASCII letters. Anything
    else — non-ASCII (Chinese, emoji) or ASCII punctuation like ``-``
    and ``.`` — is pasted via clipboard (pbcopy + cmd+v): per-app IME
    stickiness silently eats synthetic keystrokes of bare punctuation
    in some apps (observed: Terminal.app eats ``-``/``.`` while
    TextEdit types them fine), while the paste path is immune.
    """
    if mode == "auto" and all(c in _KEYSTROKE_SAFE for c in text) and _ascii_input_source():
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"keystroke failed: {result.stderr.strip()}")
        return "keystroke"
    else:
        # Non-ASCII — paste via clipboard to bypass IME
        proc = subprocess.run(
            ["pbcopy"],
            input=text, capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"pbcopy failed: {proc.stderr.strip()}")
        # Cmd+V to paste
        Quartz = _load_quartz()
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        command_down = Quartz.CGEventCreateKeyboardEvent(src, 55, True)
        command_up = Quartz.CGEventCreateKeyboardEvent(src, 55, False)
        down = Quartz.CGEventCreateKeyboardEvent(src, 9, True)  # 9 = 'v'
        up = Quartz.CGEventCreateKeyboardEvent(src, 9, False)
        Quartz.CGEventSetFlags(command_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(command_up, 0)
        Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
        try:
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, command_down)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        finally:
            # A V-up carrying Command still leaves the session modifier down.
            # Release both keys even if dispatch raises after partial delivery.
            try:
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            finally:
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, command_up)
        time.sleep(0.1)
        return "clipboard_paste"


# Key name → macOS virtual keycode mapping
_KEYCODE_MAP: dict[str, int] = {
    "return": 36, "enter": 36, "tab": 48, "space": 49,
    "escape": 53, "esc": 53, "backspace": 51, "delete": 117,
    "up": 126, "down": 125, "left": 123, "right": 124,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118,
    "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3,
    "g": 5, "h": 4, "i": 34, "j": 38, "k": 40, "l": 37,
    "m": 46, "n": 45, "o": 31, "p": 35, "q": 12, "r": 15,
    "s": 1, "t": 17, "u": 32, "v": 9, "w": 13, "x": 7,
    "y": 16, "z": 6,
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21,
    "5": 23, "6": 22, "7": 26, "8": 28, "9": 25,
    "-": 27, "=": 24, "[": 33, "]": 30, "\\": 42,
    ";": 41, "'": 39, ",": 43, ".": 47, "/": 44, "`": 50,
}

# Modifier key → CGEvent flag mapping
_MODIFIER_FLAGS: dict[str, int] = {
    "cmd": 0x100000,      # kCGEventFlagMaskCommand
    "command": 0x100000,
    "ctrl": 0x40000,      # kCGEventFlagMaskControl
    "control": 0x40000,
    "alt": 0x80000,       # kCGEventFlagMaskAlternate
    "option": 0x80000,
    "shift": 0x20000,     # kCGEventFlagMaskShift
}


def _key_macos(keys: list[str]) -> None:
    """Press key combination via AppleScript System Events.

    AppleScript 'key code' goes through the full Cocoa event chain
    (performKeyEquivalent → keyDown → insertText), which is how real
    keyboard presses are handled. CGEvent injection bypasses parts of
    this chain, causing some apps (WeChat, etc.) to misinterpret keys.
    """
    _key_applescript(keys)


def _key_applescript(keys: list[str]) -> None:
    """Fallback: press key combo using AppleScript for unmapped keys."""
    modifier_map = {
        "cmd": "command down", "command": "command down",
        "ctrl": "control down", "control": "control down",
        "alt": "option down", "option": "option down",
        "shift": "shift down",
    }

    modifiers = []
    main_key = None
    for k in keys:
        if k.lower() in modifier_map:
            modifiers.append(modifier_map[k.lower()])
        else:
            main_key = k.lower()

    if main_key is None:
        return

    modifier_str = ", ".join(modifiers)
    if main_key in _KEYCODE_MAP and (
        len(main_key) > 1 or not main_key.isalnum() or "shift down" in modifiers
    ):
        # Shift modifies a physical key; keystroke "8" can still insert "8".
        keycode = _KEYCODE_MAP[main_key]
        if modifier_str:
            script = (
                f'tell application "System Events" to key code'
                f' {keycode} using {{{modifier_str}}}'
            )
        else:
            script = (
                f'tell application "System Events" to key code {keycode}'
            )
    else:
        # Character key
        if modifier_str:
            script = (
                f'tell application "System Events" to keystroke'
                f' "{main_key}" using {{{modifier_str}}}'
            )
        else:
            script = (
                f'tell application "System Events" to keystroke "{main_key}"'
            )

    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript key press failed: {result.stderr.strip()}")


def _scroll_macos(amount: int, x: int | None = None, y: int | None = None) -> None:
    """Scroll using CGEvent."""
    Quartz = _load_quartz()

    if x is not None and y is not None:
        _move_macos(x, y)
        time.sleep(0.05)

    # kCGScrollEventUnitLine: positive = up, negative = down
    event = Quartz.CGEventCreateScrollWheelEvent(
        None, Quartz.kCGScrollEventUnitLine, 1, amount,
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _move_macos(x: int, y: int) -> None:
    """Move mouse cursor using CGEvent."""
    Quartz = _load_quartz()

    point = Quartz.CGPointMake(x, y)
    event = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft,
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _mouse_button_macos(button: str = "left", down: bool = True) -> None:
    """Press/release a mouse button at the CURRENT cursor position."""
    Quartz = _load_quartz()

    loc = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
    if button == "right":
        etype = Quartz.kCGEventRightMouseDown if down else Quartz.kCGEventRightMouseUp
        btn = Quartz.kCGMouseButtonRight
    elif button == "middle":
        etype = Quartz.kCGEventOtherMouseDown if down else Quartz.kCGEventOtherMouseUp
        btn = Quartz.kCGMouseButtonCenter
    else:
        etype = Quartz.kCGEventLeftMouseDown if down else Quartz.kCGEventLeftMouseUp
        btn = Quartz.kCGMouseButtonLeft
    event = Quartz.CGEventCreateMouseEvent(None, etype, loc, btn)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _hold_key_macos(keys: list[str], duration_s: float) -> None:
    """Hold a key (with modifiers) via CGEvent keyDown/keyUp pairs.

    The usual key path is AppleScript (app-compat reasons), but it can
    only tap — holding requires raw CGEvent keyboard events.
    """
    Quartz = _load_quartz()

    mods = [k for k in keys if k in _MODIFIER_FLAGS]
    main = [k for k in keys if k not in _MODIFIER_FLAGS]
    if not main:
        main = mods[:1]
        mods = mods[1:]
    keycode = _KEYCODE_MAP.get(main[0], 0)

    flags = 0
    for mod in mods:
        flags |= _MODIFIER_FLAGS.get(mod, 0)

    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    if flags:
        Quartz.CGEventSetFlags(down, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(duration_s)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    if flags:
        Quartz.CGEventSetFlags(up, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def _drag_macos(x1: int, y1: int, x2: int, y2: int, button: str = "left") -> None:
    """Drag: move to start, button down, stepped drag events, button up."""
    Quartz = _load_quartz()

    btn = Quartz.kCGMouseButtonLeft
    if button == "right":
        down_type, up_type = Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp
        btn = Quartz.kCGMouseButtonRight
    else:
        down_type, up_type = Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp

    def post(etype: int, x: int, y: int) -> None:
        event = Quartz.CGEventCreateMouseEvent(
            None, etype, Quartz.CGPointMake(x, y), btn
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    post(Quartz.kCGEventMouseMoved, x1, y1)
    post(down_type, x1, y1)
    try:
        dx, dy = x2 - x1, y2 - y1
        steps = max(1, max(abs(dx), abs(dy)) // 30)
        for i in range(1, steps + 1):
            post(
                Quartz.kCGEventLeftMouseDragged,
                x1 + dx * i // steps, y1 + dy * i // steps,
            )
            time.sleep(0.02)
    finally:
        post(up_type, x2, y2)


# ---------------------------------------------------------------------------
# Coordinate conversion: normalized (0-1000) → global Quartz points
# ---------------------------------------------------------------------------

# Last known point size + global origin per display id, updated each time a
# display is captured. Key None is the un-observed main-display default.
_screen_caches: dict[int | None, tuple[int, int, int, int]] = {}
# Display of the most recent screenshot; None → main default. Coordinate
# tools without an explicit display target this one.
_active_display: int | None = None
_DEFAULT_POINT_SIZE = (1920, 1080)


def _normalized_to_pixel(
    x: int, y: int, display: int | None = None,
) -> tuple[int, int]:
    """Convert normalized 0-1000 coordinates to GLOBAL CGEvent points.

    Coordinates are relative to the screenshot the model saw, i.e. the
    display's local point space; the cached display origin is added so the
    result lands on that display in the global Quartz coordinate space.
    """
    w, h, ox, oy = _screen_caches.get(display) or (*_DEFAULT_POINT_SIZE, 0, 0)
    px = min(w - 1, int(x * w / 1000)) + ox
    py = min(h - 1, int(y * h / 1000)) + oy
    return px, py


def _display_arg(display: Any) -> int | None:
    """Coerce a model-supplied display argument to a CGDirectDisplayID.

    Models emit numeric strings for coordinates (observed in the baseline
    traces); the same tolerance applies to display ids. Bools and
    non-numeric values raise ValueError.
    """
    if display is None:
        return None
    if isinstance(display, bool):
        raise ValueError("'display' must be a CGDirectDisplayID integer")
    if isinstance(display, int):
        return display
    if isinstance(display, str):
        try:
            return int(display.strip())
        except ValueError:
            raise ValueError("'display' must be a CGDirectDisplayID integer") from None
    raise ValueError("'display' must be a CGDirectDisplayID integer")


async def _resolve_target_display(display: Any) -> int | None:
    """Resolve the display a coordinate action targets.

    None → the most recent screenshot's display (or the main default when
    nothing was captured yet — no Quartz read, matching legacy behavior).
    An explicit id must be known: either captured before (cache) or still
    active (live geometry read); unknown ids raise ValueError. Numeric
    strings are accepted like every other model coordinate argument.
    """
    display = _display_arg(display)
    if display is None:
        return _active_display
    if display not in _screen_caches:
        entry = await run_native(_display_geometry, display)
        _screen_caches[display] = (entry[3], entry[4], entry[1], entry[2])
    return display


# ---------------------------------------------------------------------------
# Tool classes
# ---------------------------------------------------------------------------

class ScreenshotTool(BaseTool):
    """Capture a screenshot and return it as an image block."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer", idempotent=True)

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="screenshot",
            description=(
                "Capture a screenshot of the current screen. Returns the image "
                "directly. The calling agent (if vision-capable) can analyze "
                "it to identify UI elements and their coordinates."
            ),
            parameters=[
                ToolParameter(
                    name="task",
                    type="string",
                    description=(
                        "Optional context about what you're looking for on screen. "
                        "Helps you focus your analysis of the returned image."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="region",
                    type="array",
                    description=REGION_DESCRIPTION,
                    required=False,
                ),
                ToolParameter(
                    name="display",
                    type="integer",
                    description=(
                        "Optional CGDirectDisplayID to capture (IDs are listed "
                        "in multi-display screenshot results). Default: the "
                        "main display."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(
        self, task: str = "", region: Any = None, display: Any = None,
    ) -> ToolResult:
        global _active_display

        try:
            display = _display_arg(display)
        except ValueError as e:
            return ToolResult(content=f"screenshot: {e}", error=True)
        try:
            displays = await run_native(_active_displays)
        except Exception:  # noqa: BLE001 — note only; capture reports its own errors
            displays = ()
        if display is not None and not any(e[0] == display for e in displays):
            listing = ", ".join(str(e[0]) for e in displays) or "none"
            return ToolResult(
                content=(
                    f"screenshot: unknown display {display} "
                    f"(active displays: {listing})"
                ),
                error=True,
            )

        try:
            png_bytes = await run_native(_capture_screenshot_macos, display=display)
        except Exception as e:
            return ToolResult(
                content=f"screenshot: failed to capture screen: {e}",
                display="Screenshot capture failed",
                error=True,
            )

        # Get the actual image dimensions and update the display cache.
        # The cache must stay FULL-display even for zoomed captures — click
        # coordinates are always full-display normalized.
        import io

        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes))
        width, height = img.width, img.height
        entry = (
            _display_geometry(display, displays) if display is not None and displays
            else (_main_geometry(displays) if displays else None)
        )
        cache_id = entry[0] if entry else None
        origin = (entry[1], entry[2]) if entry else (0, 0)
        _screen_caches[cache_id] = (width, height, origin[0], origin[1])
        _active_display = cache_id

        dimension_note = f"Screenshot captured. {COORDINATE_NOTE}"
        dimension_note += _displays_note(displays, cache_id)
        if region is not None:
            parsed = parse_region(region)
            if parsed is None:
                return ToolResult(
                    content=(
                        "screenshot: 'region' must be [x1, y1, x2, y2] in "
                        "0-1000 normalized coordinates with x2 > x1, y2 > y1"
                    ),
                    error=True,
                )
            png_bytes = await run_native(
                crop_and_upscale, png_bytes, parsed, (width, height),
            )
            dimension_note = (
                f"Screenshot captured. {region_note(parsed)} {COORDINATE_NOTE}"
            )

        b64 = base64.b64encode(png_bytes).decode()
        data_url = f"data:image/png;base64,{b64}"

        text = f"{dimension_note} {task}" if task else dimension_note

        content = [
            TextBlock(text=text),
            ImageBlock(source=data_url, mime_type="image/png", detail="auto"),
        ]

        return ToolResult(
            content=content,
            display="Screenshot captured",
        )


class ClickTool(BaseTool):
    """Click at screen coordinates."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="click",
            description=(
                "Click the mouse at the specified coordinates (normalized 0-1000 scale). "
                "Use 'screenshot' first to find the coordinates of the "
                "element you want to click."
            ),
            parameters=[
                ToolParameter(
                    name="x", type="integer",
                    description=COORDINATE_X_DESCRIPTION,
                    required=False,
                ),
                ToolParameter(
                    name="y", type="integer",
                    description=COORDINATE_Y_DESCRIPTION,
                    required=False,
                ),
                ToolParameter(
                    name="bbox", type="array", required=False,
                    description="Bounding box [x1,y1,x2,y2] (0-1000); use instead of x/y",
                ),
                ToolParameter(
                    name="button",
                    type="string",
                    description="Mouse button: 'left', 'right', or 'middle'",
                    required=False,
                    default="left",
                ),
                ToolParameter(
                    name="clicks",
                    type="integer",
                    description="Number of clicks (1 for single, 2 for double)",
                    required=False,
                    default=1,
                ),
                ToolParameter(
                    name="display",
                    type="integer",
                    description=(
                        "Optional CGDirectDisplayID these coordinates refer to "
                        "(default: the display of the last screenshot)"
                    ),
                    required=False,
                ),
            ],
        )

    def get_raw_schema(self) -> dict[str, Any]:
        return click_schema(self.get_info())

    async def execute(
        self, x: Any = None, y: Any = None, button: str = "left", clicks: int = 1,
        bbox: Any = None, display: Any = None,
    ) -> ToolResult:
        # 0-1000 normalized input, or a bbox array (Qwen-VL native form).
        if bbox is not None:
            if x is not None or y is not None or not isinstance(bbox, list) or len(bbox) != 4:
                return ToolResult(
                    content="click: pass either x/y or bbox=[x1,y1,x2,y2]", error=True,
                )
            x = bbox
        point = normalize_point(x, y, strict=True)
        if point is None:
            return ToolResult(
                content=(
                    "click: pass x/y as integers (0-1000 normalized) or a "
                    "bbox [x1,y1,x2,y2] in x"
                ),
                error=True,
            )
        x, y = point
        try:
            target = await _resolve_target_display(display)
        except (ValueError, RuntimeError, OSError) as e:
            return ToolResult(content=f"click: {e}", error=True)

        # Convert normalized 0-1000 coordinates to global pixel coordinates
        px, py = _normalized_to_pixel(x, y, target)

        try:
            await run_native(_click_macos, px, py, button, clicks)
        except Exception as e:
            return ToolResult(content=f"click: failed: {e}", error=True)
        where = f", display {target}" if target is not None else ""
        return ToolResult(
            content=(
                f"Clicked {button} button at normalized ({x}, {y}) "
                f"→ pixel ({px}, {py}){where}, clicks={clicks}"
            ),
            display=f"Clicked ({x}, {y})",
        )


class TypeTextTool(BaseTool):
    """Type text at the current cursor position."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="type_text",
            description=(
                "Insert text into the focused field on macOS. Click the field first. "
                "Default auto mode uses keystrokes for ASCII letters, digits and spaces "
                "only with an ASCII-capable input source; otherwise it pastes to bypass IME. "
                "Punctuation, newlines and non-ASCII text also use clipboard paste. "
                "Paste replaces the clipboard and may be interpreted by the app (Calculator "
                "can evaluate a pasted expression without displaying that expression). "
                "This is not a sequence of key presses. Use key_press for Enter/shortcuts "
                "or click individual calculator buttons, and observe the result."
            ),
            parameters=[
                ToolParameter(
                    name="text",
                    type="string",
                    description="The text to type",
                ),
                ToolParameter(
                    name="mode", type="string", required=False, default="auto",
                    description="auto: compatible insertion; paste: always use clipboard paste",
                ),
            ],
        )

    def get_raw_schema(self) -> dict[str, Any]:
        return {
            "type": "object", "required": ["text"],
            "properties": {
                "text": {"type": "string", "description": "Text to insert"},
                "mode": {"type": "string", "enum": ["auto", "paste"], "default": "auto"},
            },
            "additionalProperties": False,
        }

    async def execute(self, text: str, mode: str = "auto") -> ToolResult:
        if not text:
            return ToolResult(content="type_text: 'text' is required", error=True)
        if mode not in ("auto", "paste"):
            return ToolResult(content="type_text: mode must be auto or paste", error=True)
        try:
            method = await run_native(_type_macos, text, mode)
        except Exception as e:
            return ToolResult(content=f"type_text: failed: {e}", error=True)
        display_text = text if len(text) <= 30 else text[:27] + "..."
        return ToolResult(
            content=(f"Typed: {text!r}\nInput method: "
                     + method
                     + ". Input dispatched; application effect not verified."),
            display=f"Typed: {display_text!r}",
        )


class KeyPressTool(BaseTool):
    """Press a key or key combination."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="key_press",
            description=(
                "Press a key or key combination. For combinations, "
                "separate keys with '+' (e.g. 'cmd+c', 'cmd+space', "
                "'ctrl+alt+delete'). Single keys: 'enter', 'tab', 'escape', "
                "'backspace', 'delete', 'up', 'down', 'left', 'right', "
                "'f1'-'f12', 'space'; modifiers cmd, ctrl, alt, shift."
            ),
            parameters=[
                ToolParameter(
                    name="keys",
                    type="string",
                    description="Key(s) to press, e.g. 'enter', 'cmd+c', 'cmd+space'",
                ),
                ToolParameter(
                    name="repeat",
                    type="integer",
                    description="Times to press the combination (1-20)",
                    required=False,
                    default=1,
                ),
            ],
        )

    async def execute(self, keys: str, repeat: int = 1) -> ToolResult:
        # Models sometimes double-encode the argument ('["return"]' or an
        # actual list) — normalize at the entry, both platforms alike.
        key_list = normalize_keys(keys)
        if not key_list:
            return ToolResult(
                content=(
                    f"key_press: invalid 'keys' {keys!r} — valid keys: "
                    "enter, tab, escape, backspace, delete, space, up, down, "
                    "left, right, home, end, pageup, pagedown, f1-f12, "
                    "letters, digits; modifiers cmd, ctrl, alt, shift "
                    "(combine with '+')"
                ),
                error=True,
            )
        try:
            times = max(1, min(20, int(repeat)))
        except (TypeError, ValueError):
            times = 1

        try:
            for _ in range(times):
                await run_native(_key_macos, key_list)
        except Exception as e:
            return ToolResult(content=f"key_press: failed: {e}", error=True)
        suffix = f" ×{times}" if times > 1 else ""
        return ToolResult(
            content=f"Pressed: {'+'.join(key_list)}{suffix}",
            display=f"Key: {'+'.join(key_list)}{suffix}",
        )


class ScrollTool(BaseTool):
    """Scroll at a screen position."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="scroll",
            description=(
                "Scroll the mouse wheel. Positive amount scrolls up, "
                "negative scrolls down. Optionally specify (x, y) in "
                "normalized 0-1000 coordinates to move the cursor there first."
            ),
            parameters=[
                ToolParameter(
                    name="amount",
                    type="integer",
                    description="Scroll amount (positive=up, negative=down)",
                ),
                ToolParameter(
                    name="x",
                    type="integer",
                    description=COORDINATE_X_DESCRIPTION,
                    required=False,
                ),
                ToolParameter(
                    name="y",
                    type="integer",
                    description=COORDINATE_Y_DESCRIPTION,
                    required=False,
                ),
                ToolParameter(
                    name="display",
                    type="integer",
                    description=(
                        "Optional CGDirectDisplayID these coordinates refer to "
                        "(default: the display of the last screenshot)"
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(
        self, amount: Any = None, x: Any = None, y: Any = None,
        display: Any = None,
    ) -> ToolResult:
        try:
            amount = int(amount)  # type: ignore[assignment]
        except (TypeError, ValueError):
            return ToolResult(content="scroll: 'amount' is required", error=True)
        if abs(amount) > 50:
            return ToolResult(
                content=(
                    f"scroll: amount {amount} out of range — use between "
                    "-50 and 50 per call (scroll multiple times for more)"
                ),
                error=True,
            )
        px, py = None, None
        pos = ""
        if x is not None or y is not None:
            point = normalize_point(x, y, strict=True)
            if point is None:
                return ToolResult(
                    content=(
                        "scroll: pass x/y as integers (0-1000 normalized) or "
                        "a bbox [x1,y1,x2,y2] in x"
                    ),
                    error=True,
                )
            x, y = point
            try:
                target = await _resolve_target_display(display)
            except (ValueError, RuntimeError, OSError) as e:
                return ToolResult(content=f"scroll: {e}", error=True)
            px, py = _normalized_to_pixel(x, y, target)
            pos = f" at ({x}, {y})"

        try:
            await run_native(_scroll_macos, amount, px, py)
        except Exception as e:
            return ToolResult(content=f"scroll: failed: {e}", error=True)
        direction = "up" if amount > 0 else "down"
        return ToolResult(
            content=f"Scrolled {direction} by {abs(amount)}{pos}",
            display=f"Scroll {direction} {abs(amount)}",
        )


class MouseMoveTool(BaseTool):
    """Move the mouse cursor without clicking."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer", idempotent=True)

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="mouse_move",
            description=(
                "Move the mouse cursor to the specified coordinates "
                "(normalized 0-1000 scale) without clicking."
            ),
            parameters=[
                ToolParameter(
                    name="x", type="integer",
                    description=COORDINATE_X_DESCRIPTION,
                ),
                ToolParameter(
                    name="y", type="integer",
                    description=COORDINATE_Y_DESCRIPTION,
                ),
                ToolParameter(
                    name="display",
                    type="integer",
                    description=(
                        "Optional CGDirectDisplayID these coordinates refer to "
                        "(default: the display of the last screenshot)"
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(
        self, x: Any, y: Any = None, display: Any = None,
    ) -> ToolResult:
        point = normalize_point(x, y, strict=True)
        if point is None:
            return ToolResult(
                content=(
                    "mouse_move: pass x/y as integers (0-1000 normalized) or "
                    "a bbox [x1,y1,x2,y2] in x"
                ),
                error=True,
            )
        x, y = point

        try:
            target = await _resolve_target_display(display)
        except (ValueError, RuntimeError, OSError) as e:
            return ToolResult(content=f"mouse_move: {e}", error=True)
        px, py = _normalized_to_pixel(x, y, target)
        try:
            await run_native(_move_macos, px, py)
        except Exception as e:
            return ToolResult(content=f"mouse_move: failed: {e}", error=True)
        return ToolResult(
            content=f"Moved cursor to normalized ({x}, {y}) → pixel ({px}, {py})",
            display=f"Cursor → ({x}, {y})",
        )


class LaunchAppTool(BaseTool):
    """Launch a macOS application by name."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="launch_app",
            description=(
                "Launch a macOS application by name and bring it to the foreground. "
                "Use this before taking screenshots to interact with an app."
            ),
            parameters=[
                ToolParameter(
                    name="app_name",
                    type="string",
                    description='Application name (e.g. "Safari", "Spark Desktop", "Arc")',
                    required=True,
                ),
            ],
        )

    async def execute(self, app_name: str) -> ToolResult:
        if not app_name:
            return ToolResult(content="launch_app: 'app_name' is required", error=True)

        try:
            result = await run_native(
                subprocess.run,
                ["open", "-a", app_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return ToolResult(
                    content=f"launch_app: failed to open '{app_name}': {result.stderr.strip()}",
                    error=True,
                )
        except Exception as e:
            return ToolResult(content=f"launch_app: failed: {e}", error=True)

        return ToolResult(
            content=f"Launched '{app_name}' and brought it to the foreground.",
            display=f"Launched {app_name}",
        )


class MouseDownTool(BaseTool):
    """Press and hold a mouse button (drag building block)."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="mouse_down",
            description="Press and hold a mouse button at the current position.",
            parameters=[
                ToolParameter(
                    name="button",
                    type="string",
                    description="Mouse button: 'left', 'right', or 'middle'",
                    required=False,
                    default="left",
                ),
            ],
        )

    async def execute(self, button: str = "left") -> ToolResult:
        try:
            await run_native(_mouse_button_macos, button, True)
        except Exception as e:
            return ToolResult(content=f"mouse_down: failed: {e}", error=True)
        return ToolResult(content=f"Mouse {button} button down", display="Mouse down")


class MouseUpTool(BaseTool):
    """Release a mouse button previously pressed with mouse_down."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="mouse_up",
            description="Release a mouse button held by mouse_down.",
            parameters=[
                ToolParameter(
                    name="button",
                    type="string",
                    description="Mouse button: 'left', 'right', or 'middle'",
                    required=False,
                    default="left",
                ),
            ],
        )

    async def execute(self, button: str = "left") -> ToolResult:
        try:
            await run_native(_mouse_button_macos, button, False)
        except Exception as e:
            return ToolResult(content=f"mouse_up: failed: {e}", error=True)
        return ToolResult(content=f"Mouse {button} button up", display="Mouse up")


class HoldKeyTool(BaseTool):
    """Hold a key combination pressed for a duration."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="hold_key",
            description=(
                "Press and hold a key combination for a duration, then "
                "release (e.g. hold shift for 1 second). Same key format "
                "as key_press."
            ),
            parameters=[
                ToolParameter(
                    name="keys",
                    type="string",
                    description="Key(s) to hold, e.g. 'shift', 'cmd+c'",
                ),
                ToolParameter(
                    name="duration_s",
                    type="number",
                    description="Seconds to hold (0.1-10)",
                    required=False,
                    default=1.0,
                ),
            ],
        )

    async def execute(self, keys: str, duration_s: float = 1.0) -> ToolResult:
        key_list = normalize_keys(keys)
        if not key_list:
            return ToolResult(content=f"hold_key: invalid 'keys' {keys!r}", error=True)
        try:
            duration = max(0.1, min(10.0, float(duration_s)))
        except (TypeError, ValueError):
            duration = 1.0
        try:
            await run_native(_hold_key_macos, key_list, duration)
        except Exception as e:
            return ToolResult(content=f"hold_key: failed: {e}", error=True)
        return ToolResult(
            content=f"Held {'+'.join(key_list)} for {duration}s",
            display=f"Hold {'+'.join(key_list)}",
        )


class DragTool(BaseTool):
    """Drag from one point to another with the button held."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="computer")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="drag",
            description=(
                "Press at (x1,y1), drag to (x2,y2), release. Coordinates "
                "are 0-1000 normalized like click."
            ),
            parameters=[
                ToolParameter(
                    name="x1", type="integer", description="Start X (0-1000 normalized)"
                ),
                ToolParameter(
                    name="y1", type="integer", description="Start Y (0-1000 normalized)"
                ),
                ToolParameter(
                    name="x2", type="integer", description="End X (0-1000 normalized)"
                ),
                ToolParameter(
                    name="y2", type="integer", description="End Y (0-1000 normalized)"
                ),
                ToolParameter(
                    name="display",
                    type="integer",
                    description=(
                        "Optional CGDirectDisplayID the START coordinates refer to "
                        "(default: the display of the last screenshot)"
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="display2",
                    type="integer",
                    description=(
                        "Optional CGDirectDisplayID the END coordinates refer to "
                        "(e.g. dragging a window to another display). "
                        "Default: same as the start display."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(
        self, x1: Any, y1: Any = None, x2: Any = None, y2: Any = None,
        display: Any = None, display2: Any = None,
    ) -> ToolResult:
        start = normalize_point(x1, y1, strict=True)
        end = normalize_point(x2, y2, strict=True)
        if start is None or end is None:
            return ToolResult(
                content="drag: pass x1/y1/x2/y2 as integers (0-1000 normalized)",
                error=True,
            )
        try:
            target = await _resolve_target_display(display)
            end_target = target if display2 is None else await _resolve_target_display(display2)
        except (ValueError, RuntimeError, OSError) as e:
            return ToolResult(content=f"drag: {e}", error=True)
        sx, sy = _normalized_to_pixel(*start, target)
        ex, ey = _normalized_to_pixel(*end, end_target)
        try:
            await run_native(_drag_macos, sx, sy, ex, ey)
        except Exception as e:
            return ToolResult(content=f"drag: failed: {e}", error=True)
        return ToolResult(
            content=(
                f"Dragged normalized {start} → {end} "
                f"(pixel ({sx},{sy}) → ({ex},{ey}))"
            ),
            display=f"Drag {start} → {end}",
        )
