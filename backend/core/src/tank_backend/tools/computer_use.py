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
from .computer_use_common import (
    COORDINATE_NOTE,
    COORDINATE_X_DESCRIPTION,
    COORDINATE_Y_DESCRIPTION,
    PYAUTOGUI_KEY_ALIASES,
    YDOTOOL_KEY_ALIASES,
    normalize_keys,
    normalize_point,
    normalized_to_pixel,
)

if TYPE_CHECKING:
    from ..llm.profile import LLMProfile

logger = logging.getLogger(__name__)

# Screen size in pixels, refreshed from every screenshot (PNG IHDR).
# Coordinate tools convert 0-1000 normalized input to pixels with it.
_screen_size: tuple[int, int] | None = None
_DEFAULT_SCREEN_SIZE = (1920, 1080)


def _png_size(png: bytes) -> tuple[int, int]:
    """Read width/height from the PNG IHDR chunk."""
    import struct

    width, height = struct.unpack(">II", png[16:24])
    return width, height


def _to_pixel(nx: int, ny: int) -> tuple[int, int]:
    size = _screen_size or _DEFAULT_SCREEN_SIZE
    if _screen_size is None:
        logger.warning(
            "screen size unknown; assuming %s until next screenshot", size
        )
    return normalized_to_pixel(nx, ny, size)


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

# The historical extract path survives neither reboot nor repo setup —
# prefer a ydotool on PATH (apt install ydotool), fall back to it.
_YDOTOOL_FALLBACK_BIN = "/tmp/ydotool-extract/usr/bin/ydotool"
_YDOTOOL_SOCKET = "/tmp/.ydotool_socket"


def _ydotool_binary() -> str:
    import shutil

    return shutil.which("ydotool") or _YDOTOOL_FALLBACK_BIN


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
        [_ydotool_binary(), subcmd, *args],
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


def _paste_linux(text: str) -> None:
    """Paste non-ASCII text via clipboard + ctrl+v.

    Synthetic typing of non-ASCII goes through the desktop IME layer and
    gets mangled; the clipboard path bypasses it (mirrors the macOS
    pbcopy+cmd+v behavior). The user's clipboard is overwritten by
    design — same tradeoff as on macOS.
    """
    import os
    import shutil
    import subprocess as sp

    wl_copy = shutil.which("wl-copy")
    xclip = shutil.which("xclip")
    wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"
    if wl_copy:
        copy_cmd = [wl_copy]
    elif wayland:
        # xclip under Wayland goes through XWayland without a clipboard
        # bridge and can hang — fail fast with the right fix instead.
        raise RuntimeError(
            "wl-copy not found — on Wayland install wl-clipboard "
            "(sudo apt install wl-clipboard)"
        )
    elif xclip:
        copy_cmd = [xclip, "-selection", "clipboard"]
    else:
        raise RuntimeError(
            "no clipboard tool found — install wl-clipboard (Wayland) or xclip"
        )
    proc = sp.run(copy_cmd, input=text.encode(), capture_output=True, timeout=5)
    if proc.returncode != 0:
        raise RuntimeError(f"clipboard copy failed: {proc.stderr.decode()[:200]}")
    import time

    time.sleep(0.1)  # let the selection register
    if _ydotool_available():
        _key_ydotool(["ctrl", "v"])
    else:
        _run_pyautogui("hotkey", "ctrl", "v")


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
        global _screen_size
        try:
            png_bytes = await asyncio.to_thread(_capture_screenshot)
        except Exception as e:
            return ToolResult(
                content=f"screenshot: failed to capture screen: {e}",
                display="Screenshot capture failed",
                error=True,
            )

        # Refresh the size cache coordinate tools convert against.
        size = _png_size(png_bytes)
        if size[0] and size[1]:
            _screen_size = size

        b64 = base64.b64encode(png_bytes).decode()
        data_url = f"data:image/png;base64,{b64}"

        note = f"Screenshot captured. {COORDINATE_NOTE}"
        text = f"{note} {task}" if task else note
        content = [
            TextBlock(text=text),
            ImageBlock(source=data_url, mime_type="image/png", detail="high"),
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
                "Click the mouse at the specified screen coordinates. "
                "Use 'screenshot' first to find the coordinates of the "
                "element you want to click."
            ),
            parameters=[
                ToolParameter(name="x", type="integer", description=COORDINATE_X_DESCRIPTION),
                ToolParameter(name="y", type="integer", description=COORDINATE_Y_DESCRIPTION),
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
        self, x: Any, y: Any = None, button: str = "left", clicks: int = 1,
    ) -> ToolResult:
        # 0-1000 normalized input (or a bbox array — Qwen-VL form).
        point = normalize_point(x, y)
        if point is None:
            return ToolResult(
                content=(
                    "click: pass x/y as integers (0-1000 normalized) or a "
                    "bbox [x1,y1,x2,y2] in x"
                ),
                error=True,
            )
        nx, ny = point
        px, py = _to_pixel(nx, ny)
        try:
            if _ydotool_available():
                await asyncio.to_thread(_click_ydotool, px, py, button, clicks)
            else:
                await asyncio.to_thread(
                    _run_pyautogui, "click", px, py, button=button, clicks=clicks
                )
        except Exception as e:
            return ToolResult(content=f"click: failed: {e}", error=True)
        return ToolResult(
            content=(
                f"Clicked {button} button at normalized ({nx}, {ny}) "
                f"→ pixel ({px}, {py}), clicks={clicks}"
            ),
            display=f"Clicked ({nx}, {ny})",
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
            if any(ord(c) >= 128 for c in text):
                # Non-ASCII: paste via clipboard to bypass IME mangling.
                await asyncio.to_thread(_paste_linux, text)
            elif _ydotool_available():
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
                "'alt+tab'). Valid keys: enter, tab, escape, backspace, "
                "delete, space, up, down, left, right, home, end, pageup, "
                "pagedown, f1-f12, letters, digits; modifiers cmd, ctrl, "
                "alt, shift."
            ),
            parameters=[
                ToolParameter(
                    name="keys",
                    type="string",
                    description="Key(s) to press, e.g. 'enter', 'ctrl+c', 'cmd+space'",
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

        # Backend-specific modifier names: ydotool speaks libevdev,
        # pyautogui (X11 fallback) its own key list.
        ydotool = _ydotool_available()
        aliases = YDOTOOL_KEY_ALIASES if ydotool else PYAUTOGUI_KEY_ALIASES
        mapped = [aliases.get(k, k) for k in key_list]

        try:
            for _ in range(times):
                if ydotool:
                    await asyncio.to_thread(_key_ydotool, mapped)
                else:
                    await asyncio.to_thread(_run_pyautogui, "hotkey", *mapped)
        except Exception as e:
            return ToolResult(content=f"key_press: failed: {e}", error=True)
        suffix = f" ×{times}" if times > 1 else ""
        return ToolResult(
            content=f"Pressed: {'+'.join(mapped)}{suffix}",
            display=f"Key: {'+'.join(mapped)}{suffix}",
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
                    description=COORDINATE_X_DESCRIPTION,
                    required=False,
                ),
                ToolParameter(
                    name="y",
                    type="integer",
                    description=COORDINATE_Y_DESCRIPTION,
                    required=False,
                ),
            ],
        )

    async def execute(
        self, amount: int, x: Any = None, y: Any = None,
    ) -> ToolResult:
        px: int | None = None
        py: int | None = None
        pos = ""
        if x is not None or y is not None:
            point = normalize_point(x, y)
            if point is None:
                return ToolResult(
                    content=(
                        "scroll: pass x/y as integers (0-1000 normalized) or "
                        "a bbox [x1,y1,x2,y2] in x"
                    ),
                    error=True,
                )
            nx, ny = point
            px, py = _to_pixel(nx, ny)
            pos = f" at ({nx}, {ny})"
        try:
            if _ydotool_available():
                await asyncio.to_thread(_scroll_ydotool, amount, px, py)
            else:
                kwargs: dict[str, Any] = {}
                if px is not None:
                    kwargs["x"] = px
                if py is not None:
                    kwargs["y"] = py
                await asyncio.to_thread(_run_pyautogui, "scroll", amount, **kwargs)
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
        return ToolMetadata(category="general", idempotent=True)

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="mouse_move",
            description="Move the mouse cursor to the specified coordinates without clicking.",
            parameters=[
                ToolParameter(name="x", type="integer", description=COORDINATE_X_DESCRIPTION),
                ToolParameter(name="y", type="integer", description=COORDINATE_Y_DESCRIPTION),
            ],
        )

    async def execute(self, x: Any, y: Any = None) -> ToolResult:
        point = normalize_point(x, y)
        if point is None:
            return ToolResult(
                content=(
                    "mouse_move: pass x/y as integers (0-1000 normalized) or "
                    "a bbox [x1,y1,x2,y2] in x"
                ),
                error=True,
            )
        nx, ny = point
        px, py = _to_pixel(nx, ny)
        try:
            if _ydotool_available():
                await asyncio.to_thread(_move_ydotool, px, py)
            else:
                await asyncio.to_thread(_run_pyautogui, "moveTo", px, py)
        except Exception as e:
            return ToolResult(content=f"mouse_move: failed: {e}", error=True)
        return ToolResult(
            content=f"Moved cursor to normalized ({nx}, {ny}) → pixel ({px}, {py})",
            display=f"Cursor → ({nx}, {ny})",
        )
