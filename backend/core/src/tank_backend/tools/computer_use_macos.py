"""Computer-use tools — screenshot capture and host UI automation (macOS).

Provides six tools that let the main ChatAgent control the host desktop:
  - screenshot: capture screen + interpret via vision LLM
  - click: mouse click at (x, y)
  - type_text: type a string at the cursor
  - key_press: press key combinations
  - scroll: scroll wheel at position
  - mouse_move: move cursor without clicking

macOS implementation uses:
  - Screenshot: screencapture CLI (built-in, no extra permissions)
  - Input: CGEvent via pyobjc-framework-Quartz (one-time Accessibility permission)
  - App control: AppleScript for activate/launch (built-in osascript)

Requires: pip install pyobjc-framework-Quartz
One-time setup: Grant Accessibility permission to Terminal/iTerm2 in
  System Settings → Privacy & Security → Accessibility
"""

from __future__ import annotations

import asyncio
import base64
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.content import ImageBlock, TextBlock
from .base import BaseTool, ToolInfo, ToolMetadata, ToolParameter, ToolResult

if TYPE_CHECKING:
    from ..llm.profile import LLMProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Screenshot capture (macOS)
# ---------------------------------------------------------------------------

def _get_display_scale_factor() -> int:
    """Get the Retina scale factor (1 for non-Retina, 2 for Retina).

    Compares the backing store pixel width (what screencapture produces)
    to the point width (what CGEvent uses for coordinates).
    """
    import Quartz

    main_display = Quartz.CGMainDisplayID()
    mode = Quartz.CGDisplayCopyDisplayMode(main_display)
    backing_width = Quartz.CGDisplayModeGetPixelWidth(mode)
    point_width = Quartz.CGDisplayModeGetWidth(mode)
    if point_width and backing_width > point_width:
        return backing_width // point_width
    return 1


def _capture_screenshot_macos() -> bytes:
    """Capture the screen and return PNG bytes scaled to point-resolution.

    macOS screencapture produces Retina (2x) images, but CGEvent uses
    point coordinates. We resize the screenshot to match point-space
    so the vision model returns coordinates that map directly to CGEvent.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["screencapture", "-x", "-C", tmp_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"screencapture failed: {result.stderr}")

        scale = _get_display_scale_factor()
        if scale > 1:
            # Downscale to point-resolution so vision model coordinates
            # map directly to CGEvent points
            result2 = subprocess.run(
                ["sips", "--resampleWidth",
                 str(_get_point_width()),
                 tmp_path],
                capture_output=True, text=True, timeout=10,
            )
            if result2.returncode != 0:
                # sips failed, try reading raw and let vision model deal with it
                logger.warning("sips resize failed, using raw Retina screenshot")

        png_bytes = Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return png_bytes


def _get_point_width() -> int:
    """Get the main display width in points."""
    import Quartz

    main_display = Quartz.CGMainDisplayID()
    mode = Quartz.CGDisplayCopyDisplayMode(main_display)
    return Quartz.CGDisplayModeGetWidth(mode)


# ---------------------------------------------------------------------------
# Input injection via CGEvent (pyobjc-framework-Quartz)
# ---------------------------------------------------------------------------

def _click_macos(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    """Click at coordinates using CGEvent."""
    import Quartz

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


def _type_macos(text: str) -> None:
    """Type text on macOS.

    For ASCII-only text, uses AppleScript keystroke (fast, reliable).
    For text containing non-ASCII (Chinese, emoji, etc.), uses clipboard
    paste (pbcopy + cmd+v) to bypass IME interference.
    """
    if all(ord(c) < 128 for c in text):
        # Pure ASCII — use keystroke directly
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"keystroke failed: {result.stderr.strip()}")
    else:
        # Non-ASCII — paste via clipboard to bypass IME
        proc = subprocess.run(
            ["pbcopy"],
            input=text, capture_output=True, text=True, timeout=5,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"pbcopy failed: {proc.stderr.strip()}")
        # Cmd+V to paste
        import Quartz
        src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        down = Quartz.CGEventCreateKeyboardEvent(src, 9, True)  # 9 = 'v'
        up = Quartz.CGEventCreateKeyboardEvent(src, 9, False)
        Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        time.sleep(0.1)


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
    if main_key in _KEYCODE_MAP and len(main_key) > 1:
        # Named key — use key code
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
    import Quartz

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
    import Quartz

    point = Quartz.CGPointMake(x, y)
    event = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft,
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


# ---------------------------------------------------------------------------
# Coordinate conversion: normalized (0-1000) → pixel
# ---------------------------------------------------------------------------

# Last known screen point dimensions for normalized→pixel conversion.
# Updated each time a screenshot is captured.
_screen_point_size: tuple[int, int] = (1920, 1080)


def _normalized_to_pixel(x: int, y: int) -> tuple[int, int]:
    """Convert normalized 0-1000 coordinates to pixel coordinates."""
    screen_w, screen_h = _screen_point_size
    px = int(x * screen_w / 1000)
    py = int(y * screen_h / 1000)
    return px, py


# ---------------------------------------------------------------------------
# Tool classes
# ---------------------------------------------------------------------------

class ScreenshotTool(BaseTool):
    """Capture a screenshot and return it as an image block."""

    def __init__(self, profile: LLMProfile) -> None:
        self._profile = profile

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="general", idempotent=True)

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
            ],
        )

    async def execute(self, task: str = "") -> ToolResult:
        global _screen_point_size

        try:
            png_bytes = await asyncio.to_thread(_capture_screenshot_macos)
        except Exception as e:
            return ToolResult(
                content=f"screenshot: failed to capture screen: {e}",
                display="Screenshot capture failed",
                error=True,
            )

        # Get the actual image dimensions and update the module-level cache
        import io

        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes))
        width, height = img.width, img.height
        _screen_point_size = (width, height)

        b64 = base64.b64encode(png_bytes).decode()
        data_url = f"data:image/png;base64,{b64}"

        dimension_note = (
            "Screenshot captured. "
            "When reporting element positions, use NORMALIZED coordinates "
            "on a 0-1000 scale where (0, 0) is the top-left corner and "
            "(1000, 1000) is the bottom-right corner. "
            "For example, the center of the screen is (500, 500). "
            "All coordinate tools (click, scroll, mouse_move) expect this "
            "0-1000 normalized format."
        )
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
        return ToolMetadata(category="general")

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
                    description="X coordinate (0-1000, 0=left, 1000=right)",
                ),
                ToolParameter(
                    name="y", type="integer",
                    description="Y coordinate (0-1000, 0=top, 1000=bottom)",
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
            ],
        )

    async def execute(
        self, x: int, y: int, button: str = "left", clicks: int = 1,
    ) -> ToolResult:
        # Handle models that pass coordinates as a list: {'x': [180, 168]}
        if isinstance(x, list):
            if len(x) >= 2:
                x, y = int(x[0]), int(x[1])
            else:
                return ToolResult(content="click: need both x and y coordinates", error=True)

        # Handle models that pass coordinates as strings: {'x': '380', 'y': '310'}
        try:
            x, y = int(x), int(y)
        except (ValueError, TypeError):
            return ToolResult(
                content=f"click: x and y must be integers, got x={x!r}, y={y!r}",
                error=True,
            )

        # Convert normalized 0-1000 coordinates to pixel coordinates
        px, py = _normalized_to_pixel(x, y)

        try:
            await asyncio.to_thread(_click_macos, px, py, button, clicks)
        except Exception as e:
            return ToolResult(content=f"click: failed: {e}", error=True)
        return ToolResult(
            content=(
                f"Clicked {button} button at normalized ({x}, {y}) "
                f"→ pixel ({px}, {py}), clicks={clicks}"
            ),
            display=f"Clicked ({x}, {y})",
        )


class TypeTextTool(BaseTool):
    """Type text at the current cursor position."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="general")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="type_text",
            description=(
                "Type text at the current cursor/focus position. "
                "Click on an input field first using the 'click' tool, "
                "then use this to enter text."
            ),
            parameters=[
                ToolParameter(
                    name="text",
                    type="string",
                    description="The text to type",
                ),
            ],
        )

    async def execute(self, text: str) -> ToolResult:
        if not text:
            return ToolResult(content="type_text: 'text' is required", error=True)
        try:
            await asyncio.to_thread(_type_macos, text)
        except Exception as e:
            return ToolResult(content=f"type_text: failed: {e}", error=True)
        display_text = text if len(text) <= 30 else text[:27] + "..."
        return ToolResult(
            content=f"Typed: {text!r}",
            display=f"Typed: {display_text!r}",
        )


class KeyPressTool(BaseTool):
    """Press a key or key combination."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="general")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="key_press",
            description=(
                "Press a key or key combination. For combinations, "
                "separate keys with '+' (e.g. 'cmd+c', 'cmd+space', "
                "'ctrl+alt+delete'). Single keys: 'enter', 'tab', 'escape', "
                "'backspace', 'delete', 'up', 'down', 'left', 'right', "
                "'f1'-'f12', 'space', etc."
            ),
            parameters=[
                ToolParameter(
                    name="keys",
                    type="string",
                    description="Key(s) to press, e.g. 'enter', 'cmd+c', 'cmd+space'",
                ),
            ],
        )

    async def execute(self, keys: str) -> ToolResult:
        if not keys:
            return ToolResult(content="key_press: 'keys' is required", error=True)

        key_list = [k.strip() for k in keys.split("+")]

        try:
            await asyncio.to_thread(_key_macos, key_list)
        except Exception as e:
            return ToolResult(content=f"key_press: failed: {e}", error=True)
        return ToolResult(
            content=f"Pressed: {keys}",
            display=f"Key: {keys}",
        )


class ScrollTool(BaseTool):
    """Scroll at a screen position."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="general")

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
                    description="X coordinate (0-1000) to scroll at",
                    required=False,
                ),
                ToolParameter(
                    name="y",
                    type="integer",
                    description="Y coordinate (0-1000) to scroll at",
                    required=False,
                ),
            ],
        )

    async def execute(
        self, amount: int, x: int | None = None, y: int | None = None,
    ) -> ToolResult:
        # Convert normalized coordinates to pixel if provided
        px, py = None, None
        if x is not None and y is not None:
            px, py = _normalized_to_pixel(int(x), int(y))

        try:
            await asyncio.to_thread(_scroll_macos, amount, px, py)
        except Exception as e:
            return ToolResult(content=f"scroll: failed: {e}", error=True)
        direction = "up" if amount > 0 else "down"
        pos = f" at ({x}, {y})" if x is not None else ""
        return ToolResult(
            content=f"Scrolled {direction} by {abs(amount)}{pos}",
            display=f"Scroll {direction} {abs(amount)}",
        )


class MouseMoveTool(BaseTool):
    """Move the mouse cursor without clicking."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="general", idempotent=True)

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
                    description="X coordinate (0-1000, 0=left, 1000=right)",
                ),
                ToolParameter(
                    name="y", type="integer",
                    description="Y coordinate (0-1000, 0=top, 1000=bottom)",
                ),
            ],
        )

    async def execute(self, x: int, y: int) -> ToolResult:
        try:
            x, y = int(x), int(y)
        except (ValueError, TypeError):
            return ToolResult(
                content=f"mouse_move: invalid coordinates x={x!r}, y={y!r}",
                error=True,
            )

        px, py = _normalized_to_pixel(x, y)
        try:
            await asyncio.to_thread(_move_macos, px, py)
        except Exception as e:
            return ToolResult(content=f"mouse_move: failed: {e}", error=True)
        return ToolResult(
            content=f"Moved cursor to normalized ({x}, {y}) → pixel ({px}, {py})",
            display=f"Cursor → ({x}, {y})",
        )


class LaunchAppTool(BaseTool):
    """Launch a macOS application by name."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="general")

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
            result = await asyncio.to_thread(
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
