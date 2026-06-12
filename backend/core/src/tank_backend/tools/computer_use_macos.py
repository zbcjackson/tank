"""Computer-use tools — screenshot capture and host UI automation (macOS).

Provides six tools that let the main ChatAgent control the host desktop:
  - screenshot: capture screen + interpret via vision LLM
  - click: mouse click at (x, y)
  - type_text: type a string at the cursor
  - key_press: press key combinations
  - scroll: scroll wheel at position
  - mouse_move: move cursor without clicking

macOS implementation uses:
  - Screenshot: screencapture CLI (built-in, works without permissions on own screen)
  - Input: cliclick (lightweight, no accessibility permission needed for basic clicks)
    OR AppleScript/CGEvent via pyobjc (needs Accessibility permission)

The screenshot tool calls a dedicated vision LLM (configured via the
``computer_use`` LLM profile) to interpret what's on screen. Action
tools use platform-native APIs.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.content import ImageBlock, TextBlock
from .base import BaseTool, ToolInfo, ToolMetadata, ToolParameter, ToolResult

if TYPE_CHECKING:
    from ..llm.profile import LLMProfile

logger = logging.getLogger(__name__)

_VISION_SYSTEM_PROMPT = """\
You are a GUI grounding agent. You see a screenshot of a macOS computer screen.

Your job:
1. Describe what you see relevant to the user's task.
2. When asked to locate a UI element, output its pixel coordinates as (x, y).
3. Be precise with coordinates — they will be used for mouse clicks.
4. If you cannot find what's requested, say so clearly.

Always respond concisely. Focus on actionable information."""


# ---------------------------------------------------------------------------
# Screenshot capture (macOS)
# ---------------------------------------------------------------------------

def _capture_screenshot_macos() -> bytes:
    """Capture the screen using macOS screencapture CLI and return PNG bytes."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["screencapture", "-x", "-C", tmp_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"screencapture failed: {result.stderr}")
        png_bytes = Path(tmp_path).read_bytes()
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return png_bytes


# ---------------------------------------------------------------------------
# Input injection (macOS) — multiple backends
# ---------------------------------------------------------------------------

def _cliclick_available() -> bool:
    """Check if cliclick is installed (brew install cliclick)."""
    try:
        r = subprocess.run(["cliclick", "-V"], capture_output=True, timeout=3)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _run_cliclick(*args: str) -> None:
    """Run a cliclick command."""
    result = subprocess.run(
        ["cliclick", *args],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"cliclick failed: {result.stderr.strip()}")


def _click_macos(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    """Click at coordinates on macOS."""
    if _cliclick_available():
        # cliclick commands: c: = click, rc: = right-click, dc: = double-click
        if clicks == 2:
            cmd = f"dc:{x},{y}"
        elif button == "right":
            cmd = f"rc:{x},{y}"
        else:
            cmd = f"c:{x},{y}"
        _run_cliclick(cmd)
        # Additional clicks beyond 2
        for _ in range(max(0, clicks - 2)):
            _run_cliclick(f"c:{x},{y}")
    else:
        _click_applescript(x, y, button, clicks)


def _click_applescript(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    """Click using CGEvent via subprocess python call (needs Accessibility permission)."""
    script = f"""
import Quartz
import time

point = Quartz.CGPointMake({x}, {y})
"""
    if button == "right":
        script += f"""
for _ in range({clicks}):
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventRightMouseDown, point, Quartz.kCGMouseButtonRight)
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventRightMouseUp, point, Quartz.kCGMouseButtonRight)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    time.sleep(0.05)
"""
    elif clicks == 2:
        script += """
down = Quartz.CGEventCreateMouseEvent(
    None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
up = Quartz.CGEventCreateMouseEvent(
    None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
time.sleep(0.02)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
time.sleep(0.05)
down2 = Quartz.CGEventCreateMouseEvent(
    None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
Quartz.CGEventSetIntegerValueField(down2, Quartz.kCGMouseEventClickState, 2)
up2 = Quartz.CGEventCreateMouseEvent(
    None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
Quartz.CGEventSetIntegerValueField(up2, Quartz.kCGMouseEventClickState, 2)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, down2)
time.sleep(0.02)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, up2)
"""
    else:
        script += f"""
for _ in range({clicks}):
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.02)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    time.sleep(0.05)
"""
    result = subprocess.run(
        ["python3", "-c", script],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"CGEvent click failed: {result.stderr.strip()}")


def _type_macos(text: str) -> None:
    """Type text on macOS."""
    if _cliclick_available():
        # cliclick t: types text
        _run_cliclick(f"t:{text}")
    else:
        _type_applescript(text)


def _type_applescript(text: str) -> None:
    """Type text using AppleScript System Events."""
    # Escape for AppleScript
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "System Events" to keystroke "{escaped}"'
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript keystroke failed: {result.stderr.strip()}")


def _key_macos(keys: list[str]) -> None:
    """Press key combination on macOS using cliclick or AppleScript."""
    if _cliclick_available():
        # cliclick kp: presses a key, kd:/ku: for modifiers
        # Map key names to cliclick key names
        cliclick_map = {
            "enter": "return", "return": "return",
            "tab": "tab", "escape": "escape", "esc": "escape",
            "space": "space", "backspace": "delete", "delete": "fwd-delete",
            "up": "arrow-up", "down": "arrow-down",
            "left": "arrow-left", "right": "arrow-right",
            "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
            "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
            "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
        }
        modifier_map = {
            "cmd": "command", "command": "command",
            "ctrl": "control", "control": "control",
            "alt": "option", "option": "option",
            "shift": "shift",
        }

        if len(keys) == 1:
            key = cliclick_map.get(keys[0].lower(), keys[0].lower())
            _run_cliclick(f"kp:{key}")
        else:
            # Modifiers + key combination
            modifiers = []
            main_key = None
            for k in keys:
                if k.lower() in modifier_map:
                    modifiers.append(modifier_map[k.lower()])
                else:
                    main_key = cliclick_map.get(k.lower(), k.lower())

            if main_key is None:
                main_key = modifiers.pop() if modifiers else "return"

            # cliclick: kd:modifier kp:key ku:modifier
            cmds = (
                [f"kd:{m}" for m in modifiers]
                + [f"kp:{main_key}"]
                + [f"ku:{m}" for m in modifiers]
            )
            _run_cliclick(*cmds)
    else:
        _key_applescript(keys)


def _key_applescript(keys: list[str]) -> None:
    """Press key combo using AppleScript."""
    # Map to AppleScript key codes
    applescript_keycodes = {
        "return": 36, "enter": 36, "tab": 48, "space": 49,
        "escape": 53, "esc": 53, "backspace": 51, "delete": 117,
        "up": 126, "down": 125, "left": 123, "right": 124,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118,
        "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    }
    modifier_applescript = {
        "cmd": "command down", "command": "command down",
        "ctrl": "control down", "control": "control down",
        "alt": "option down", "option": "option down",
        "shift": "shift down",
    }

    modifiers = []
    main_key = None
    for k in keys:
        if k.lower() in modifier_applescript:
            modifiers.append(modifier_applescript[k.lower()])
        else:
            main_key = k.lower()

    if main_key is None:
        return

    modifier_str = ", ".join(modifiers) if modifiers else ""

    if main_key in applescript_keycodes:
        keycode = applescript_keycodes[main_key]
        if modifier_str:
            script = (
                f'tell application "System Events" to key code'
                f' {keycode} using {{{modifier_str}}}'
            )
        else:
            script = f'tell application "System Events" to key code {keycode}'
    else:
        # Single character
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
    """Scroll on macOS."""
    if x is not None and y is not None:
        _move_macos(x, y)

    if _cliclick_available():
        # cliclick doesn't have scroll. Use CGEvent approach.
        pass

    # Use CGEvent for scroll (works without cliclick)
    script = f"""
import Quartz
evt = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, {amount})
Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
"""
    result = subprocess.run(
        ["python3", "-c", script],
        capture_output=True, text=True, timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"CGEvent scroll failed: {result.stderr.strip()}")


def _move_macos(x: int, y: int) -> None:
    """Move mouse cursor on macOS."""
    if _cliclick_available():
        _run_cliclick(f"m:{x},{y}")
    else:
        script = f"""
import Quartz
point = Quartz.CGPointMake({x}, {y})
evt = Quartz.CGEventCreateMouseEvent(
    None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
"""
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            raise RuntimeError(f"CGEvent move failed: {result.stderr.strip()}")


# ---------------------------------------------------------------------------
# Tool classes
# ---------------------------------------------------------------------------

class ScreenshotTool(BaseTool):
    """Capture a screenshot and analyze it with the vision LLM."""

    def __init__(self, profile: LLMProfile) -> None:
        self._profile = profile

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="general", idempotent=True)

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="screenshot",
            description=(
                "Capture a screenshot of the computer screen and analyze it "
                "using a vision model. Pass a task/question describing what "
                "you want to know about the screen (e.g. 'Find the Spark app "
                "icon and give me its coordinates', 'What app is currently "
                "in the foreground?'). Returns the vision model's analysis "
                "including coordinates of UI elements when requested."
            ),
            parameters=[
                ToolParameter(
                    name="task",
                    type="string",
                    description=(
                        "What to look for or analyze on the screen. Be specific "
                        "about what element you need coordinates for."
                    ),
                    required=True,
                ),
            ],
        )

    async def execute(self, task: str) -> ToolResult:
        if not task:
            return ToolResult(content="screenshot: 'task' is required", error=True)

        try:
            png_bytes = await asyncio.to_thread(_capture_screenshot_macos)
        except Exception as e:
            return ToolResult(
                content=f"screenshot: failed to capture screen: {e}",
                display="Screenshot capture failed",
                error=True,
            )

        b64 = base64.b64encode(png_bytes).decode()
        data_url = f"data:image/png;base64,{b64}"

        from openai.types.chat import ChatCompletionMessageParam

        from ..llm.profile import create_llm_from_profile

        llm = create_llm_from_profile(self._profile)

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": _VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    {"type": "text", "text": task},
                ],
            },
        ]

        try:
            response = await llm.complete(messages)
        except Exception as e:
            return ToolResult(
                content=f"screenshot: vision LLM call failed: {e}",
                display="Vision analysis failed",
                error=True,
            )

        content = [
            TextBlock(text=response),
            ImageBlock(source=data_url, mime_type="image/png", detail="low"),
        ]

        return ToolResult(
            content=content,
            display=f"Screenshot analyzed: {response[:100]}",
        )


class ClickTool(BaseTool):
    """Click at screen coordinates."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(category="general")

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="click",
            description=(
                "Click the mouse at the specified screen coordinates. "
                "Use 'screenshot' first to find the coordinates of the "
                "element you want to click."
            ),
            parameters=[
                ToolParameter(name="x", type="integer", description="X coordinate (pixels)"),
                ToolParameter(name="y", type="integer", description="Y coordinate (pixels)"),
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
        try:
            await asyncio.to_thread(_click_macos, x, y, button, clicks)
        except Exception as e:
            return ToolResult(content=f"click: failed: {e}", error=True)
        return ToolResult(
            content=f"Clicked {button} button at ({x}, {y}), clicks={clicks}",
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
                "negative scrolls down. Optionally specify (x, y) to "
                "move the cursor there first."
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
                    description="X coordinate to scroll at",
                    required=False,
                ),
                ToolParameter(
                    name="y",
                    type="integer",
                    description="Y coordinate to scroll at",
                    required=False,
                ),
            ],
        )

    async def execute(
        self, amount: int, x: int | None = None, y: int | None = None,
    ) -> ToolResult:
        try:
            await asyncio.to_thread(_scroll_macos, amount, x, y)
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
            description="Move the mouse cursor to the specified coordinates without clicking.",
            parameters=[
                ToolParameter(name="x", type="integer", description="X coordinate (pixels)"),
                ToolParameter(name="y", type="integer", description="Y coordinate (pixels)"),
            ],
        )

    async def execute(self, x: int, y: int) -> ToolResult:
        try:
            await asyncio.to_thread(_move_macos, x, y)
        except Exception as e:
            return ToolResult(content=f"mouse_move: failed: {e}", error=True)
        return ToolResult(
            content=f"Moved cursor to ({x}, {y})",
            display=f"Cursor → ({x}, {y})",
        )
