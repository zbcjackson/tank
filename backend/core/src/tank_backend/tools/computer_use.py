"""Computer-use tools — screenshot capture and host UI automation.

Provides six tools that let the main ChatAgent control the host desktop:
  - screenshot: capture screen + interpret via vision LLM
  - click: mouse click at (x, y)
  - type_text: type a string at the cursor
  - key_press: press key combinations
  - scroll: scroll wheel at position
  - mouse_move: move cursor without clicking

The screenshot tool calls a dedicated vision LLM (configured via the
``computer_use`` LLM profile) to interpret what's on screen. Action
tools are thin wrappers around pyautogui.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import TYPE_CHECKING, Any

from ..core.content import ImageBlock, TextBlock
from .base import BaseTool, ToolInfo, ToolMetadata, ToolParameter, ToolResult

if TYPE_CHECKING:
    from ..llm.profile import LLMProfile

logger = logging.getLogger(__name__)

_VISION_SYSTEM_PROMPT = """\
You are a GUI grounding agent. You see a screenshot of a computer screen.

Your job:
1. Describe what you see relevant to the user's task.
2. When asked to locate a UI element, output its pixel coordinates as (x, y).
3. Be precise with coordinates — they will be used for mouse clicks.
4. If you cannot find what's requested, say so clearly.

Always respond concisely. Focus on actionable information."""


def _capture_screenshot(monitor_index: int = 0) -> bytes:
    """Capture the screen and return PNG bytes.

    Tries multiple backends in order:
    1. XDG Desktop Portal (works on GNOME Wayland)
    2. mss (works on X11 and some Wayland compositors)

    Includes retry logic for the portal path since
    xdg-desktop-portal-gnome can crash and restart between calls.
    """
    for _attempt in range(3):
        png = _capture_via_portal()
        if png is not None:
            return png
        # Portal may be restarting after a crash — brief pause before retry
        import time
        time.sleep(1)

    # Fallback to mss (X11)
    import mss
    import mss.tools

    with mss.MSS() as sct:
        monitors = sct.monitors
        mon = monitors[min(monitor_index + 1, len(monitors) - 1)]
        img = sct.grab(mon)
        png_bytes: bytes = mss.tools.to_png(img.rgb, img.size)  # type: ignore[assignment]
    return png_bytes


def _capture_via_portal() -> bytes | None:
    """Capture screenshot via XDG Desktop Portal (GNOME Wayland).

    Returns PNG bytes on success, None if the portal is unavailable.
    """
    import json
    import re
    import subprocess
    import time
    from pathlib import Path
    from urllib.parse import unquote, urlparse

    try:
        monitor = subprocess.Popen(
            ["busctl", "--user", "--json=short", "monitor",
             "org.freedesktop.portal.Desktop"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
    except FileNotFoundError:
        return None

    time.sleep(0.3)

    try:
        result = subprocess.run(
            ["busctl", "--user", "call", "org.freedesktop.portal.Desktop",
             "/org/freedesktop/portal/desktop",
             "org.freedesktop.portal.Screenshot", "Screenshot",
             "sa{sv}", "", "2",
             "handle_token", "s", "tank_screenshot",
             "interactive", "b", "false"],
            capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        monitor.terminate()
        return None

    if result.returncode != 0:
        monitor.terminate()
        return None

    time.sleep(3)
    monitor.terminate()
    out = monitor.stdout.read() if monitor.stdout else ""

    uri = None
    for line in out.split("\n"):
        if "uri" not in line or "file://" not in line:
            continue
        try:
            data = json.loads(line)
            payload = data.get("payload", {}).get("data", [])
            if len(payload) >= 2 and isinstance(payload[1], dict):
                uri_entry = payload[1].get("uri", {})
                if isinstance(uri_entry, dict):
                    uri = uri_entry.get("data")
        except (json.JSONDecodeError, IndexError, TypeError):
            match = re.search(r'file://[^\s"]+', line)
            if match:
                uri = match.group(0)
        break

    if not uri:
        return None

    parsed = urlparse(uri)
    file_path = Path(unquote(parsed.path))
    if not file_path.exists():
        return None

    png_bytes = file_path.read_bytes()
    file_path.unlink(missing_ok=True)
    return png_bytes


def _run_pyautogui(func_name: str, *args: Any, **kwargs: Any) -> None:
    """Call a pyautogui function by name."""
    import pyautogui

    pyautogui.FAILSAFE = False
    fn = getattr(pyautogui, func_name)
    fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# ydotool-based input (works on Wayland via /dev/uinput)
# ---------------------------------------------------------------------------

_YDOTOOL_BIN = "/tmp/ydotool-extract/usr/bin/ydotool"
_YDOTOOL_SOCKET = "/tmp/.ydotool_socket"


def _ydotool_available() -> bool:
    """Check if ydotool daemon is running."""
    from pathlib import Path
    return Path(_YDOTOOL_SOCKET).exists()


def _run_ydotool(subcmd: str, *args: str) -> None:
    """Run a ydotool subcommand."""
    import os
    import subprocess

    env = os.environ.copy()
    env["YDOTOOL_SOCKET"] = _YDOTOOL_SOCKET
    result = subprocess.run(
        [_YDOTOOL_BIN, subcmd, *args],
        capture_output=True, text=True, timeout=5, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ydotool {subcmd} failed: {result.stderr.strip()}")


def _click_ydotool(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    """Click using ydotool (Wayland-compatible).

    Uses reset-to-origin + relative move for pixel-accurate positioning,
    since ydotool absolute mode doesn't work reliably on GNOME Wayland.
    """
    _move_ydotool(x, y)
    # ydotool click codes: 0xC0=left, 0xC1=right, 0xC2=middle (down+up combined)
    btn_map = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
    btn_code = btn_map.get(button, "0xC0")
    for _ in range(clicks):
        _run_ydotool("click", "-D", "50", btn_code)


def _type_ydotool(text: str) -> None:
    """Type text using ydotool."""
    _run_ydotool("type", "--", text)


def _key_ydotool(keys: list[str]) -> None:
    """Press key combination using ydotool.

    ydotool uses key names like 'enter', 'ctrl', 'alt', 'shift', 'space', etc.
    For combos: "ctrl+c" → separate key press/release events.
    """
    # ydotool key command takes keycodes or key names joined with '+'
    combo = "+".join(keys)
    _run_ydotool("key", combo)


def _scroll_ydotool(amount: int, x: int | None = None, y: int | None = None) -> None:
    """Scroll using ydotool."""
    if x is not None and y is not None:
        _move_ydotool(x, y)
    # ydotool wheel: -w flag with -x (horizontal) -y (vertical)
    # positive y = scroll up, negative y = scroll down
    _run_ydotool("mousemove", "-w", "-x", "0", "-y", str(amount))


def _move_ydotool(x: int, y: int) -> None:
    """Move mouse to pixel coordinates using ydotool.

    Uses reset-to-origin + relative move for pixel-accurate positioning,
    since ydotool --absolute doesn't work on GNOME Wayland.
    """
    _run_ydotool("mousemove", "-x", "-20000", "-y", "-20000")
    _run_ydotool("mousemove", "-x", str(x), "-y", str(y))


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
                "you want to know about the screen (e.g. 'Find the Firefox "
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
            png_bytes = await asyncio.to_thread(_capture_screenshot)
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
            if _ydotool_available():
                await asyncio.to_thread(_click_ydotool, x, y, button, clicks)
            else:
                await asyncio.to_thread(_run_pyautogui, "click", x, y, button=button, clicks=clicks)
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
                ToolParameter(
                    name="interval",
                    type="number",
                    description="Seconds between each keystroke (0 for instant)",
                    required=False,
                    default=0,
                ),
            ],
        )

    async def execute(self, text: str, interval: float = 0) -> ToolResult:
        if not text:
            return ToolResult(content="type_text: 'text' is required", error=True)
        try:
            if _ydotool_available():
                await asyncio.to_thread(_type_ydotool, text)
            else:
                await asyncio.to_thread(_run_pyautogui, "write", text, interval=interval)
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
                "separate keys with '+' (e.g. 'ctrl+c', 'cmd+space', "
                "'alt+tab'). Single keys: 'enter', 'tab', 'escape', "
                "'backspace', 'delete', 'up', 'down', 'left', 'right', "
                "'f1'-'f12', 'space', etc."
            ),
            parameters=[
                ToolParameter(
                    name="keys",
                    type="string",
                    description="Key(s) to press, e.g. 'enter', 'ctrl+c', 'cmd+space'",
                ),
            ],
        )

    async def execute(self, keys: str) -> ToolResult:
        if not keys:
            return ToolResult(content="key_press: 'keys' is required", error=True)

        key_list = [k.strip() for k in keys.split("+")]
        # Map common aliases
        alias_map = {"ctrl": "ctrl", "cmd": "command", "win": "win", "alt": "alt"}
        mapped = [alias_map.get(k.lower(), k.lower()) for k in key_list]

        try:
            if _ydotool_available():
                await asyncio.to_thread(_key_ydotool, mapped)
            else:
                await asyncio.to_thread(_run_pyautogui, "hotkey", *mapped)
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
            if _ydotool_available():
                await asyncio.to_thread(_scroll_ydotool, amount, x, y)
            else:
                kwargs: dict[str, Any] = {}
                if x is not None:
                    kwargs["x"] = x
                if y is not None:
                    kwargs["y"] = y
                await asyncio.to_thread(_run_pyautogui, "scroll", amount, **kwargs)
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
            if _ydotool_available():
                await asyncio.to_thread(_move_ydotool, x, y)
            else:
                await asyncio.to_thread(_run_pyautogui, "moveTo", x, y)
        except Exception as e:
            return ToolResult(content=f"mouse_move: failed: {e}", error=True)
        return ToolResult(
            content=f"Moved cursor to ({x}, {y})",
            display=f"Cursor → ({x}, {y})",
        )
