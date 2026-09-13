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
import struct
import time
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

# Socket discovery: env override → distro default under XDG_RUNTIME_DIR
# (Ubuntu's systemd ydotoold listens at /run/user/<uid>/.ydotool_socket)
# → legacy /tmp path.
_YDOTOOL_LEGACY_SOCKET = "/tmp/.ydotool_socket"


def _ydotool_socket() -> str | None:
    import os
    from pathlib import Path

    candidates: list[str] = []
    if env_socket := os.environ.get("YDOTOOL_SOCKET"):
        candidates.append(env_socket)
    if xdg := os.environ.get("XDG_RUNTIME_DIR"):
        candidates.append(f"{xdg}/.ydotool_socket")
    candidates.append(_YDOTOOL_LEGACY_SOCKET)
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _ydotool_available() -> bool:
    """Check if a ydotool daemon socket is reachable."""
    return _ydotool_socket() is not None


# ---------------------------------------------------------------------------
# ydotool native input — speak the ydotoold socket protocol directly.
#
# The distro CLI is unusable (verified on the GUI VM 2026-09-13 by
# strace + evtest): Debian ydotool 1.0.4-3 `key` sends nothing at all,
# and `mousemove -a` emits an INT32_MIN delta that libinput drops. The
# daemon protocol is fine, so we send its 24-byte little-endian
# datagrams ourselves: 16 zero bytes, uint32 (type | code << 16),
# int32 value — one EV_SYN after each event (strace ground truth).
# ---------------------------------------------------------------------------

_YD_EV_KEY = 1
_YD_EV_REL = 2

# value is SIGNED int32: relative deltas and wheel values go negative.
_YD_PACKET = struct.Struct("<16xIi")

_PACKET_GAP_S = 0.005
_KEY_HOLD_S = 0.05
_TYPE_HOLD_S = 0.02

# Canonical key names / characters → Linux evdev keycodes (US layout).
_LINUX_KEYCODES: dict[str, int] = {
    "escape": 1, "esc": 1,
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9,
    "9": 10, "0": 11, "-": 12, "=": 13,
    "backspace": 14, "tab": 15,
    "q": 16, "w": 17, "e": 18, "r": 19, "t": 20, "y": 21, "u": 22,
    "i": 23, "o": 24, "p": 25, "[": 26, "]": 27,
    "enter": 28, "ctrl": 29,
    "a": 30, "s": 31, "d": 32, "f": 33, "g": 34, "h": 35, "j": 36,
    "k": 37, "l": 38, ";": 39, "'": 40, "`": 41, "shift": 42, "\\": 43,
    "z": 44, "x": 45, "c": 46, "v": 47, "b": 48, "n": 49, "m": 50,
    ",": 51, ".": 52, "/": 53,
    "space": 57, " ": 57,
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
    "alt": 56,
    "home": 102, "up": 103, "pageup": 104, "left": 105, "right": 106,
    "end": 107, "down": 108, "pagedown": 109, "insert": 110, "delete": 111,
    "meta": 125,
}

# Characters typed as shift + another key (US layout).
_LINUX_SHIFT_CHARS: dict[str, str] = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]",
    ":": ";", '"': "'", "~": "`", "|": "\\", "<": ",", ">": ".", "?": "/",
}

_YD_BTN = {"left": 272, "right": 273, "middle": 274}  # BTN_LEFT/RIGHT/MIDDLE
_YD_REL_X, _YD_REL_Y, _YD_REL_WHEEL = 0, 1, 8

_YD_MODIFIERS = ("ctrl", "alt", "shift", "meta")


def _ydotool_client():
    """Connected DGRAM socket to the ydotoold daemon."""
    import socket as socket_mod

    path = _ydotool_socket()
    if path is None:
        raise RuntimeError("ydotoold is not running (no socket found)")
    sock = socket_mod.socket(socket_mod.AF_UNIX, socket_mod.SOCK_DGRAM)
    sock.connect(path)
    return sock


def _ydotool_emit(sock, ev_type: int, code: int, value: int) -> None:
    """Send one event + SYN to the daemon."""
    sock.send(_YD_PACKET.pack(ev_type | (code << 16), value))
    sock.send(_YD_PACKET.pack(0, 0))
    time.sleep(_PACKET_GAP_S)


def _key_ydotool(keys: list[str]) -> None:
    """Press a combo as a real chord: modifiers down, main key tap,
    modifiers up (the dead CLI pressed keys sequentially instead)."""
    mods = [k for k in keys if k in _YD_MODIFIERS]
    main = [k for k in keys if k not in _YD_MODIFIERS]
    sock = _ydotool_client()
    try:
        for mod in mods:
            _ydotool_emit(sock, _YD_EV_KEY, _LINUX_KEYCODES[mod], 1)
        for key in main:
            code = _LINUX_KEYCODES[key]
            _ydotool_emit(sock, _YD_EV_KEY, code, 1)
            time.sleep(_KEY_HOLD_S)
            _ydotool_emit(sock, _YD_EV_KEY, code, 0)
        for mod in reversed(mods):
            _ydotool_emit(sock, _YD_EV_KEY, _LINUX_KEYCODES[mod], 0)
    finally:
        sock.close()


def _type_ydotool(text: str) -> None:
    """Type ASCII text as per-character key events (US layout)."""
    sock = _ydotool_client()
    try:
        for ch in text:
            base = _LINUX_SHIFT_CHARS.get(ch)
            if base is None and ch.lower() in _LINUX_KEYCODES:
                base = ch.lower()
                shifted = ch.isupper()
            elif base is not None:
                shifted = True
            else:
                raise ValueError(f"untypable character: {ch!r}")
            code = _LINUX_KEYCODES[base]
            if shifted:
                shift_code = _LINUX_KEYCODES["shift"]
                _ydotool_emit(sock, _YD_EV_KEY, shift_code, 1)
                _ydotool_emit(sock, _YD_EV_KEY, code, 1)
                time.sleep(_TYPE_HOLD_S)
                _ydotool_emit(sock, _YD_EV_KEY, code, 0)
                _ydotool_emit(sock, _YD_EV_KEY, shift_code, 0)
            else:
                _ydotool_emit(sock, _YD_EV_KEY, code, 1)
                time.sleep(_TYPE_HOLD_S)
                _ydotool_emit(sock, _YD_EV_KEY, code, 0)
    finally:
        sock.close()


def _click_ydotool(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    """Click at pixel coordinates (move first, then BTN down/up)."""
    _move_ydotool(x, y)
    btn = _YD_BTN.get(button, _YD_BTN["left"])
    sock = _ydotool_client()
    try:
        for i in range(clicks):
            _ydotool_emit(sock, _YD_EV_KEY, btn, 1)
            time.sleep(_KEY_HOLD_S)
            _ydotool_emit(sock, _YD_EV_KEY, btn, 0)
            if i < clicks - 1:
                time.sleep(0.05)
    finally:
        sock.close()


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
    # wl-copy/xclip fork into the background to serve the selection and
    # the child inherits our pipes — capture_output would block on EOF
    # until timeout. DEVNULL lets the daemonizing child inherit harmless fds.
    proc = sp.run(
        copy_cmd, input=text.encode(),
        stdout=sp.DEVNULL, stderr=sp.DEVNULL, timeout=5,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"clipboard copy failed (exit {proc.returncode})")
    import time

    time.sleep(0.1)  # let the selection register
    if _ydotool_available():
        _key_ydotool(["ctrl", "v"])
    else:
        _run_pyautogui("hotkey", "ctrl", "v")


def _scroll_ydotool(amount: int, x: int | None = None, y: int | None = None) -> None:
    """Scroll the wheel (positive = up, negative = down)."""
    if x is not None and y is not None:
        _move_ydotool(x, y)
    sock = _ydotool_client()
    try:
        _ydotool_emit(sock, _YD_EV_REL, _YD_REL_WHEEL, amount)
    finally:
        sock.close()


def _move_ydotool(x: int, y: int) -> None:
    """Move to pixel coordinates: reset to top-left with chunked small
    deltas (a single huge delta gets dropped by libinput), then one
    relative move of (x, y)."""
    sock = _ydotool_client()
    try:
        # 10 × (-400,-400) covers any display up to 4K from any position.
        for _ in range(10):
            _ydotool_emit(sock, _YD_EV_REL, _YD_REL_X, -400)
            _ydotool_emit(sock, _YD_EV_REL, _YD_REL_Y, -400)
        _ydotool_emit(sock, _YD_EV_REL, _YD_REL_X, x)
        _ydotool_emit(sock, _YD_EV_REL, _YD_REL_Y, y)
    finally:
        sock.close()


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
