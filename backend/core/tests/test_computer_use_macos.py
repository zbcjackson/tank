"""Tests for macOS computer-use tools (screencapture + CGEvent + AppleScript).

Runs on any platform: Quartz is imported lazily inside functions, so these
tests mock ``subprocess.run`` (screencapture/sips/osascript/pbcopy) and the
Quartz-backed helpers directly. A fake ``Quartz`` module is injected into
``sys.modules`` for the clipboard-paste path.
"""

from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

MODULE = "tank_backend.tools.computer_use_macos"

from tank_backend.core.content import ImageBlock, TextBlock  # noqa: E402
from tank_backend.tools import computer_use_macos as cu_macos  # noqa: E402
from tank_backend.tools.computer_use_macos import (  # noqa: E402
    ClickTool,
    KeyPressTool,
    LaunchAppTool,
    MouseMoveTool,
    ScreenshotTool,
    ScrollTool,
    TypeTextTool,
    _normalized_to_pixel,
)
from tank_backend.tools.computer_use_macos import (  # noqa: E402
    _ascii_input_source as _native_ascii_input_source,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def ascii_input_source():
    """Keep native input-source state out of cross-platform unit tests."""
    with patch(f"{MODULE}._ascii_input_source", return_value=True):
        yield


@pytest.fixture(autouse=True)
def reset_screen_size():
    """Reset the module-level screen-size cache between tests."""
    cu_macos._screen_point_size = (1920, 1080)
    yield
    cu_macos._screen_point_size = (1920, 1080)


class _FakeQuartz:
    """Stand-in for the Quartz module for the clipboard-paste path.

    ``import Quartz`` inside production code resolves to whatever object
    sits in ``sys.modules`` — a plain instance works as well as a module.
    """

    CGEventSourceCreate = MagicMock(return_value=object())
    kCGEventSourceStateHIDSystemState = 1
    CGEventCreateKeyboardEvent = MagicMock(side_effect=lambda s, k, d: (k, d))
    CGEventSetFlags = MagicMock()
    kCGEventFlagMaskCommand = 0x100000
    CGEventPost = MagicMock()
    kCGHIDEventTap = 0
    CGEventCreate = MagicMock()
    CGEventGetLocation = MagicMock()
    CGEventCreateMouseEvent = MagicMock()
    CGPointMake = MagicMock()
    kCGEventLeftMouseDown = 1
    kCGEventLeftMouseUp = 2
    kCGMouseButtonLeft = 0
    kCGEventLeftMouseDragged = 3
    kCGEventMouseMoved = 5
    kCGEventFlagMaskShift = 0x20000


@pytest.fixture
def fake_quartz(monkeypatch: pytest.MonkeyPatch) -> _FakeQuartz:
    """Inject a fake Quartz module for functions that ``import Quartz``."""
    quartz = _FakeQuartz()
    # Class-level MagicMock attrs are shared across tests — rebind fresh
    # instances so call counts stay per-test.
    quartz.CGEventCreateKeyboardEvent = MagicMock(
        side_effect=lambda s, k, d: (k, d)
    )
    quartz.CGEventSetFlags = MagicMock()
    quartz.CGEventPost = MagicMock()
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    return quartz


def make_png(width: int = 640, height: int = 480) -> bytes:
    """Generate a real PNG (the tool parses dimensions with PIL)."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="red").save(buf, format="PNG")
    return buf.getvalue()


def make_run_ok(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


@pytest.mark.parametrize("button", ["left", "right", "middle"])
@pytest.mark.parametrize("down", [True, False])
def test_mouse_button_uses_quartz_location_api(button, down):
    quartz = MagicMock()
    current_event = object()  # CGEventRef has no getLocation method.
    quartz.CGEventCreate.return_value = current_event
    quartz.CGEventGetLocation.return_value = (123, 456)
    with patch(f"{MODULE}._load_quartz", return_value=quartz):
        cu_macos._mouse_button_macos(button, down)
    quartz.CGEventGetLocation.assert_called_once_with(current_event)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (123, 456)
    quartz.CGEventPost.assert_called_once()


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


class TestNormalizedToPixel:
    def test_identity_at_origin(self):
        assert _normalized_to_pixel(0, 0) == (0, 0)

    def test_max_maps_inside_screen(self):
        cu_macos._screen_point_size = (2560, 1600)
        assert _normalized_to_pixel(1000, 1000) == (2559, 1599)

    def test_center(self):
        cu_macos._screen_point_size = (2000, 1000)
        assert _normalized_to_pixel(500, 500) == (1000, 500)

    def test_respects_aspect_ratio(self):
        # Non-square screen: x and y scale independently
        cu_macos._screen_point_size = (3840, 1200)
        px, py = _normalized_to_pixel(250, 750)
        assert px == 960  # 250/1000 * 3840
        assert py == 900  # 750/1000 * 1200

    def test_default_cache(self):
        # Default cache is 1920x1080
        assert _normalized_to_pixel(1000, 1000) == (1919, 1079)


# ---------------------------------------------------------------------------
# ScreenshotTool
# ---------------------------------------------------------------------------


class TestScreenshotTool:
    @pytest.mark.asyncio
    async def test_returns_image_and_updates_cache(self):
        tool = ScreenshotTool()
        with patch(f"{MODULE}._capture_screenshot_macos", return_value=make_png(800, 600)):
            result = await tool.execute(task="find the button")

        assert result.error is False
        blocks = result.content
        assert isinstance(blocks, list)
        assert isinstance(blocks[0], TextBlock)
        assert "0-1000" in blocks[0].text
        assert isinstance(blocks[1], ImageBlock)
        assert blocks[1].source.startswith("data:image/png;base64,")
        assert cu_macos._screen_point_size == (800, 600)

    @pytest.mark.asyncio
    async def test_capture_failure(self):
        tool = ScreenshotTool()
        with patch(
            f"{MODULE}._capture_screenshot_macos",
            side_effect=RuntimeError("screencapture failed: no permission"),
        ):
            result = await tool.execute(task="")
        assert result.error is True
        assert "failed to capture" in result.content

    def test_get_info(self):
        info = ScreenshotTool().get_info()
        assert info.name == "screenshot"


# ---------------------------------------------------------------------------
# ClickTool
# ---------------------------------------------------------------------------


class TestClickTool:
    @pytest.mark.asyncio
    async def test_normalized_coords_converted(self):
        tool = ClickTool()
        with patch(f"{MODULE}._click_macos") as mock_click:
            result = await tool.execute(x=500, y=250)
        mock_click.assert_called_once_with(960, 270, "left", 1)
        assert result.error is False
        assert "(500, 250)" in result.content

    @pytest.mark.asyncio
    async def test_list_coordinates_handled(self):
        tool = ClickTool()
        with patch(f"{MODULE}._click_macos") as mock_click:
            result = await tool.execute(x=cast(int, [180, 168]), y=0)
        mock_click.assert_called_once_with(345, 181, "left", 1)
        assert result.error is False

    @pytest.mark.asyncio
    async def test_string_coordinates_handled(self):
        tool = ClickTool()
        with patch(f"{MODULE}._click_macos") as mock_click:
            result = await tool.execute(x=cast(int, "380"), y=cast(int, "310"))
        mock_click.assert_called_once_with(729, 334, "left", 1)
        assert result.error is False

    @pytest.mark.asyncio
    async def test_invalid_coordinates_error(self):
        tool = ClickTool()
        with patch(f"{MODULE}._click_macos") as mock_click:
            result = await tool.execute(x=cast(int, "abc"), y=cast(int, "def"))
        mock_click.assert_not_called()
        assert result.error is True

    @pytest.mark.asyncio
    async def test_click_failure_reported(self):
        tool = ClickTool()
        with patch(f"{MODULE}._click_macos", side_effect=RuntimeError("not authorized")):
            result = await tool.execute(x=100, y=100)
        assert result.error is True
        assert "click: failed" in result.content


# ---------------------------------------------------------------------------
# TypeTextTool
# ---------------------------------------------------------------------------


class TestTypeTextTool:
    @pytest.mark.parametrize("source,value,capable", [
        (1, 2, True), (1, 2, False), (1, None, False), (None, None, False),
    ])
    def test_native_input_source_releases_owned_reference(self, source, value, capable):
        carbon, core = MagicMock(), MagicMock()
        carbon.TISCopyCurrentKeyboardInputSource.return_value = source
        carbon.TISGetInputSourceProperty.return_value = value
        core.CFBooleanGetValue.return_value = capable
        with (
            patch(f"{MODULE}.ctypes.CDLL", side_effect=[carbon, core]),
            patch(f"{MODULE}.ctypes.c_void_p.in_dll", return_value=123),
        ):
            assert _native_ascii_input_source() is capable
        if source:
            core.CFRelease.assert_called_once_with(source)
        else:
            core.CFRelease.assert_not_called()

    async def test_ascii_text_bypasses_non_ascii_input_source(self, fake_quartz):
        with (
            patch(f"{MODULE}._ascii_input_source", return_value=False),
            patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as command,
        ):
            result = await TypeTextTool().execute(text="Abc123")
        assert not result.error
        assert command.call_args.args[0] == ["pbcopy"]
        assert command.call_args.kwargs["input"] == "Abc123"
        assert "clipboard_paste" in result.content

    async def test_shift_digit_dispatches_physical_key_with_modifier(self):
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as command:
            result = await KeyPressTool().execute(keys="shift+8")
        assert not result.error
        script = command.call_args.args[0][2]
        assert "key code 28 using {shift down}" in script

    async def test_batch_paste_then_enter_uses_distinct_input_paths(
        self, fake_quartz: _FakeQuartz,
    ) -> None:
        from tank_backend.tools.computer_use_common import ComputerBatchTool
        from tank_backend.tools.manager import ToolManager

        tool = TypeTextTool()
        manager = ToolManager.__new__(ToolManager)
        manager.tools = {"type_text": tool}
        schema = manager.get_openai_tools()[0]["function"]["parameters"]
        assert schema["properties"]["mode"]["enum"] == ["auto", "paste"]
        assert "mode" not in schema["required"]
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as command:
            batch = ComputerBatchTool({"type_text": tool, "key_press": KeyPressTool()})
            result = await batch.execute(
                actions=[{"action": "type_text", "text": "7*8", "mode": "paste"},
                         {"action": "key_press", "keys": "enter"}], screenshot=False,
            )
        assert not result.error
        assert command.call_args_list[0].args[0] == ["pbcopy"]
        assert "key code 36" in command.call_args_list[1].args[0][2]
        assert fake_quartz.CGEventCreateKeyboardEvent.call_count == 4  # balanced cmd+v

    @pytest.mark.parametrize("mode", ["keys", "", None, []])
    async def test_invalid_mode_dispatches_no_input(
        self, mode: str, fake_quartz: _FakeQuartz,
    ) -> None:
        with patch(f"{MODULE}.subprocess.run") as command:
            result = await TypeTextTool().execute(text="56", mode=mode)
        assert result.error
        command.assert_not_called()
        fake_quartz.CGEventPost.assert_not_called()

    async def test_explicit_paste_uses_clipboard_for_alphanumeric(
        self, fake_quartz: _FakeQuartz,
    ) -> None:
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as command:
            result = await TypeTextTool().execute(text="56", mode="paste")
        assert not result.error
        assert command.call_args.args[0] == ["pbcopy"]
        assert command.call_args.kwargs["input"] == "56"
        assert fake_quartz.CGEventCreateKeyboardEvent.call_count == 4
        assert "clipboard_paste" in result.content

    @pytest.mark.asyncio
    async def test_ascii_uses_applescript_keystroke(self):
        tool = TypeTextTool()
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as mock_run:
            result = await tool.execute(text="hello world")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript"
        assert "keystroke" in args[2]
        assert "hello world" in args[2]
        assert result.error is False

    @pytest.mark.asyncio
    async def test_quoted_text_routes_to_paste(self, fake_quartz):
        """Quotes are punctuation — per-app IME eats bare punctuation
        keystrokes, so quoted text takes the clipboard path now."""
        tool = TypeTextTool()
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as mock_run:
            await tool.execute(text='say "hi"')
        first_cmd = mock_run.call_args_list[0][0][0]
        assert first_cmd[0] == "pbcopy"

    @pytest.mark.asyncio
    async def test_non_ascii_uses_clipboard_paste(self, fake_quartz):
        tool = TypeTextTool()
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as mock_run:
            result = await tool.execute(text="你好，世界")
        # pbcopy was called with the text
        pbcopy_call = mock_run.call_args_list[0]
        assert pbcopy_call[0][0][0] == "pbcopy"
        assert pbcopy_call[1]["input"] == "你好，世界"
        # cmd+v keyboard events posted via Quartz
        assert fake_quartz.CGEventCreateKeyboardEvent.call_count == 4
        assert fake_quartz.CGEventSetFlags.call_count == 4
        assert result.error is False

    @pytest.mark.parametrize("fail_key", [None, 9, 55])
    async def test_paste_releases_keys_even_when_posting_fails(self, fake_quartz, fail_key):
        pressed = set()
        flags = {}

        def set_flags(event, value):
            flags[event] = value

        def post(_tap, event):
            key, down = event
            if down:
                pressed.add(key)
            else:
                pressed.discard(key)
            # Quartz modifier flags also affect the session's modifier state.
            if flags[event] & fake_quartz.kCGEventFlagMaskCommand:
                pressed.add(55)
            else:
                pressed.discard(55)
            if down and key == fail_key:
                raise RuntimeError("Post failed after delivery")

        fake_quartz.CGEventSetFlags.side_effect = set_flags
        fake_quartz.CGEventPost.side_effect = post
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()):
            result = await TypeTextTool().execute(text="56", mode="paste")
        assert result.error is (fail_key is not None)
        assert pressed == set()

    @pytest.mark.asyncio
    async def test_keystroke_failure_raises(self):
        tool = TypeTextTool()
        failed = make_run_ok(returncode=1, stderr="osascript: execution failed")
        with patch(f"{MODULE}.subprocess.run", return_value=failed):
            result = await tool.execute(text="hello")
        assert result.error is True

    @pytest.mark.asyncio
    async def test_empty_text_error(self):
        result = await TypeTextTool().execute(text="")
        assert result.error is True


# ---------------------------------------------------------------------------
# KeyPressTool
# ---------------------------------------------------------------------------


class TestKeyPressTool:
    @pytest.mark.asyncio
    async def test_named_key_uses_keycode(self):
        tool = KeyPressTool()
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as mock_run:
            result = await tool.execute(keys="return")
        script = mock_run.call_args[0][0][2]
        assert "key code 36" in script  # return = 36
        assert result.error is False

    @pytest.mark.asyncio
    async def test_modifier_chord(self):
        tool = KeyPressTool()
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as mock_run:
            await tool.execute(keys="cmd+c")
        script = mock_run.call_args[0][0][2]
        assert "command down" in script
        assert 'keystroke "c"' in script

    @pytest.mark.asyncio
    async def test_multiple_modifiers(self):
        tool = KeyPressTool()
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as mock_run:
            await tool.execute(keys="cmd+shift+a")
        script = mock_run.call_args[0][0][2]
        assert "command down" in script
        assert "shift down" in script

    @pytest.mark.asyncio
    async def test_osascript_failure_raises(self):
        tool = KeyPressTool()
        failed = make_run_ok(returncode=1, stderr="not authorized")
        with patch(f"{MODULE}.subprocess.run", return_value=failed):
            result = await tool.execute(keys="cmd+c")
        assert result.error is True

    @pytest.mark.asyncio
    async def test_empty_keys_error(self):
        result = await KeyPressTool().execute(keys="")
        assert result.error is True


# ---------------------------------------------------------------------------
# ScrollTool / MouseMoveTool / LaunchAppTool
# ---------------------------------------------------------------------------


class TestScrollTool:
    @pytest.mark.asyncio
    async def test_scroll_at_normalized_position(self):
        tool = ScrollTool()
        with patch(f"{MODULE}._scroll_macos") as mock_scroll:
            result = await tool.execute(amount=-3, x=500, y=500)
        mock_scroll.assert_called_once_with(-3, 960, 540)
        assert result.error is False
        assert "down" in result.content

    @pytest.mark.asyncio
    async def test_scroll_without_position(self):
        tool = ScrollTool()
        with patch(f"{MODULE}._scroll_macos") as mock_scroll:
            result = await tool.execute(amount=5)
        mock_scroll.assert_called_once_with(5, None, None)
        assert result.error is False


class TestMouseMoveTool:
    @pytest.mark.asyncio
    async def test_move_converts_coordinates(self):
        tool = MouseMoveTool()
        with patch(f"{MODULE}._move_macos") as mock_move:
            result = await tool.execute(x=250, y=750)
        mock_move.assert_called_once_with(480, 810)
        assert result.error is False

    @pytest.mark.asyncio
    async def test_invalid_coordinates_error(self):
        tool = MouseMoveTool()
        with patch(f"{MODULE}._move_macos") as mock_move:
            result = await tool.execute(x=cast(int, None), y=cast(int, None))
        mock_move.assert_not_called()
        assert result.error is True


class TestLaunchAppTool:
    @pytest.mark.asyncio
    async def test_launch_calls_open(self):
        tool = LaunchAppTool()
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as mock_run:
            result = await tool.execute(app_name="Safari")
        args = mock_run.call_args[0][0]
        assert args[:3] == ["open", "-a", "Safari"]
        assert result.error is False

    @pytest.mark.asyncio
    async def test_launch_failure(self):
        tool = LaunchAppTool()
        failed = make_run_ok(returncode=1, stderr="Unable to find application")
        with patch(f"{MODULE}.subprocess.run", return_value=failed):
            result = await tool.execute(app_name="Nope")
        assert result.error is True

    @pytest.mark.asyncio
    async def test_empty_name_error(self):
        result = await LaunchAppTool().execute(app_name="")
        assert result.error is True


class TestKeyPressToolNormalization:
    """E2: entry normalization must cover macOS too (same model quirks)."""

    @pytest.mark.asyncio
    async def test_double_encoded_enter(self):
        tool = KeyPressTool()
        with patch("tank_backend.tools.computer_use_macos._key_macos") as mock:
            result = await tool.execute(keys='["return"]')
        assert result.error is False
        mock.assert_called_once_with(["enter"])

    @pytest.mark.asyncio
    async def test_garbage_keys_errors(self):
        tool = KeyPressTool()
        result = await tool.execute(keys="[]]")
        assert result.error is True


class TestA3MacOSPrimitives:
    """A3: mouse_down/up, hold_key, drag on the macOS CGEvent path."""

    def test_mouse_button_uses_current_position(self, fake_quartz: _FakeQuartz) -> None:
        from tank_backend.tools import computer_use_macos as m

        fake_quartz.CGEventCreate = MagicMock(return_value=object())
        fake_quartz.CGEventGetLocation = MagicMock(return_value=(100, 200))
        fake_quartz.CGEventCreateMouseEvent = MagicMock(side_effect=lambda s, t, p, b: (t, p, b))
        fake_quartz.kCGEventLeftMouseDown = 1
        fake_quartz.kCGEventLeftMouseUp = 2
        fake_quartz.kCGMouseButtonLeft = 0

        m._mouse_button_macos("left", down=True)
        fake_quartz.CGEventPost.assert_called()
        ev = fake_quartz.CGEventCreateMouseEvent.call_args[0]
        assert ev[1] == 1 and ev[2] == (100, 200)

    def test_hold_key_down_up_with_flags(self, fake_quartz: _FakeQuartz) -> None:
        from tank_backend.tools import computer_use_macos as m

        fake_quartz.kCGEventFlagMaskShift = 0x20000
        events: list[tuple[int, bool]] = []
        fake_quartz.CGEventCreateKeyboardEvent = MagicMock(
            side_effect=lambda s, k, d: events.append((k, d)) or (k, d)
        )
        m._hold_key_macos(["shift", "a"], 0.05)
        keys = [e for e in events]
        assert keys[0] == (0, True)   # 'a' key code 0 down
        assert keys[-1] == (0, False) # up after duration
        assert fake_quartz.CGEventSetFlags.called

    def test_drag_sequence(self, fake_quartz: _FakeQuartz, monkeypatch) -> None:
        from tank_backend.tools import computer_use_macos as m

        posted: list[tuple] = []
        fake_quartz.CGEventCreateMouseEvent = MagicMock(
            side_effect=lambda s, t, p, b: (t, p, b)
        )
        fake_quartz.CGEventPost = MagicMock(side_effect=lambda tap, ev: posted.append(ev))
        fake_quartz.kCGEventLeftMouseDown = 1
        fake_quartz.kCGEventLeftMouseUp = 2
        fake_quartz.kCGEventLeftMouseDragged = 6
        fake_quartz.kCGEventMouseMoved = 5
        fake_quartz.kCGMouseButtonLeft = 0
        fake_quartz.CGPointMake = lambda x, y: (x, y)
        monkeypatch.setattr(m.time, "sleep", lambda *_: None)

        m._drag_macos(100, 100, 160, 100)
        kinds = [ev[0] for ev in posted]
        assert kinds[0] == 5          # move to start
        assert kinds[1] == 1          # button down
        assert 6 in kinds             # dragged intermediates
        assert kinds[-1] == 2         # button up
        assert posted[-1][1] == (160, 100)


class TestA3MacOSTools:
    @pytest.mark.asyncio
    async def test_tools_delegate(self, monkeypatch):
        from tank_backend.tools import computer_use_macos as m

        with (
            patch(f"{m.__name__}._mouse_button_macos") as mb,
            patch(f"{m.__name__}._hold_key_macos") as hk,
            patch(f"{m.__name__}._drag_macos") as drag,
        ):
            r1 = await m.MouseDownTool().execute(button="right")
            r2 = await m.MouseUpTool().execute()
            r3 = await m.HoldKeyTool().execute(keys="shift", duration_s=99)
            r4 = await m.DragTool().execute(x1=100, y1=100, x2=200, y2=200)
        from tank_backend.tools.computer_use_macos import _normalized_to_pixel  # noqa: F401
        assert all(r.error is False for r in (r1, r2, r3, r4))
        mb.assert_any_call("right", True)
        hk.assert_called_once_with(["shift"], 10.0)
        sx, sy = m._normalized_to_pixel(100, 100)
        ex, ey = m._normalized_to_pixel(200, 200)
        drag.assert_called_once_with(sx, sy, ex, ey)  # 1920x1080 default

    @pytest.mark.asyncio
    async def test_scroll_clamps_amount(self):
        from tank_backend.tools import computer_use_macos as m

        r = await m.ScrollTool().execute(amount=500)
        assert r.error is True
        assert "50" in r.content


class TestSpecialCharPasteFallback:
    """A5-era follow-up: bare punctuation keystrokes are eaten by some
    apps' sticky IME (Terminal eats -/. while TextEdit is fine) — any
    text beyond alnum+space must take the clipboard paste path."""

    @pytest.mark.asyncio
    async def test_ascii_punctuation_routes_to_paste(self, fake_quartz):
        tool = TypeTextTool()
        with patch("tank_backend.tools.computer_use_macos.subprocess.run") as mr:
            mr.return_value = make_run_ok()
            result = await tool.execute(text="T3-batch-ok")
        assert result.error is False
        first_cmd = mr.call_args_list[0][0][0]
        assert first_cmd[0] == "pbcopy"  # paste path, not keystroke

    @pytest.mark.asyncio
    async def test_plain_alnum_still_keystrokes(self):
        tool = TypeTextTool()
        with patch("tank_backend.tools.computer_use_macos.subprocess.run") as mr:
            mr.return_value = make_run_ok()
            await tool.execute(text="hello world 42")
        first_cmd = mr.call_args_list[0][0][0]
        assert first_cmd[0] == "osascript"  # fast keystroke path


# ---------------------------------------------------------------------------
# Screenshot zoom (A13)
# ---------------------------------------------------------------------------


class TestScreenshotZoomMacos:
    @pytest.mark.asyncio
    async def test_region_zooms_and_keeps_full_cache(self):
        tool = ScreenshotTool()
        with patch(
            f"{MODULE}._capture_screenshot_macos",
            return_value=make_png(400, 200),
        ):
            result = await tool.execute(region=[0, 0, 500, 1000])

        assert result.error is False
        assert isinstance(result.content, list) and isinstance(result.content[0], TextBlock)
        assert "ZOOMED" in result.content[0].text
        # Cache stays FULL screen (point space) for click conversion.
        assert cu_macos._screen_point_size == (400, 200)

    @pytest.mark.asyncio
    async def test_invalid_region_errors(self):
        tool = ScreenshotTool()
        with patch(
            f"{MODULE}._capture_screenshot_macos",
            return_value=make_png(100, 100),
        ):
            result = await tool.execute(region="not-a-region")
        assert result.error is True
        assert "region" in result.content


@pytest.fixture
def capture_chain(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[MagicMock, MagicMock]]:
    """Only OS boundaries are fake; capture, transport and click code stay real.

    The sips substitute performs a real Pillow resize. This verifies Tank's
    command contract, not the installed macOS sips or physical event delivery.
    """
    from PIL import Image, ImageDraw

    width, height, scale, fail_resize = getattr(request, "param", (1920, 1080, 2, False))
    quartz = MagicMock()
    quartz.CGDisplayModeGetPixelHeight.return_value = height * scale
    quartz.CGDisplayModeGetPixelWidth.return_value = width * scale
    quartz.CGDisplayModeGetWidth.return_value = width
    quartz.CGDisplayModeGetHeight.return_value = height
    quartz.CGPointMake.side_effect = lambda x, y: (x, y)
    paths: list[Path] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        path = Path(args[-1])
        if args[0] == "screencapture":
            paths.append(path)
            img = Image.new("RGB", (round(width * scale), round(height * scale)), "black")
            # Known target in the lower-right quadrant, away from crop edges.
            ImageDraw.Draw(img).rectangle(
                (width * scale * 0.7, height * scale * 0.7,
                 width * scale * 0.8, height * scale * 0.8), fill="red",
            )
            img.save(path)
        elif args[0] == "sips":
            assert args[1] == "--resampleWidth"
            if fail_resize:
                return subprocess.CompletedProcess(args, 1, "", "simulated resize failure")
            with Image.open(path) as img:
                new_width = int(args[2])
                resized = img.resize((new_width, round(img.height * new_width / img.width)))
            resized.save(path)
        else:
            raise AssertionError(f"Unexpected host command: {args[0]}")
        return subprocess.CompletedProcess(args, 0, "", "")

    command = MagicMock(side_effect=run)
    monkeypatch.setattr(cu_macos, "_load_quartz", lambda: quartz)
    monkeypatch.setattr(cu_macos.subprocess, "run", command)
    yield quartz, command
    assert all(not path.exists() for path in paths), "capture temp files must be removed"


def screenshot_wire_image(result: object) -> tuple[bytes, str]:
    """Use the actual tool-result/follow-up serializer, not the UI display."""
    from tank_backend.llm.llm import _build_follow_up_user_message, _tool_result_to_llm

    _, _, blocks = _tool_result_to_llm(result)
    message = _build_follow_up_user_message("capture-id", "screenshot", blocks)
    parts = message["content"]
    wire = next(part["image_url"] for part in parts if part["type"] == "image_url")
    image_block = next(block for block in blocks if isinstance(block, ImageBlock))
    assert wire["url"] == image_block.source
    assert wire["detail"] == "auto"
    assert wire["url"].startswith("data:image/png;base64,")
    return base64.b64decode(wire["url"].split(",", 1)[1]), "\n".join(
        part["text"] for part in parts if part["type"] == "text"
    )


@pytest.mark.parametrize("capture_chain", [
    (1920, 1080, 1, False), (1920, 1080, 2, False), (1512, 982, 2, False),
    (1600, 1000, 1.5, False),
], indirect=True)
async def test_capture_to_wire_to_quartz_preserves_coordinate_space(capture_chain):
    from PIL import Image

    quartz, command = capture_chain
    result = await ScreenshotTool().execute()
    assert not result.error
    png, note = screenshot_wire_image(result)
    with Image.open(io.BytesIO(png)) as img:
        width, height = img.size
        assert width == quartz.CGDisplayModeGetWidth.return_value
        assert height == quartz.CGDisplayModeGetHeight.return_value
        assert img.getpixel((round(width * 0.75), round(height * 0.75))) == (255, 0, 0)
    assert "0-1000" in note
    assert cu_macos._screen_point_size == (width, height)
    result = await ClickTool().execute(x=750, y=750)
    assert not result.error
    point = (int(width * 0.75), int(height * 0.75))
    events = quartz.CGEventCreateMouseEvent.call_args_list
    assert [call.args[2] for call in events] == [point, point]
    assert [call.args[1] for call in events] == [
        quartz.kCGEventLeftMouseDown, quartz.kCGEventLeftMouseUp,
    ]
    assert quartz.CGEventPost.call_count == 2
    needs_resize = quartz.CGDisplayModeGetPixelWidth() > width
    assert [call.args[0][0] for call in command.call_args_list] == (
        ["screencapture", "sips"] if needs_resize else ["screencapture"]
    )
    assert "-m" in command.call_args_list[0].args[0]  # Only the mapped main display.


async def test_successful_but_wrong_screenshot_dimensions_are_rejected(capture_chain):
    quartz, _ = capture_chain
    quartz.CGDisplayModeGetHeight.return_value = 1200
    result = await ScreenshotTool().execute()
    assert result.error
    assert "dimensions" in result.content
    quartz.CGEventCreateMouseEvent.assert_not_called()


@pytest.mark.parametrize("capture_chain", [(1920, 1080, 2, True)], indirect=True)
@pytest.mark.parametrize("use_executor", [False, True])
async def test_resize_failure_never_advertises_retina_pixels_as_points(capture_chain, use_executor):
    """A failed conversion must stop, not advertise an unusable screenshot."""
    from tank_backend.computer.executor import _MacOSExecutor

    quartz, _ = capture_chain
    if use_executor:
        executor = _MacOSExecutor()
        with pytest.raises(RuntimeError, match="sips"):
            await executor.screenshot()
    else:
        result = await ScreenshotTool().execute()
        assert result.error
        assert "sips" in result.content
        assert cu_macos._screen_point_size == (1920, 1080)
    quartz.CGEventCreateMouseEvent.assert_not_called()


async def test_zoom_wire_pixels_and_full_screen_click_mapping(capture_chain):
    from PIL import Image

    quartz, _ = capture_chain
    result = await ScreenshotTool().execute(region=[500, 500, 1000, 1000])
    png, note = screenshot_wire_image(result)
    # Crop: 960x540 at origin (960,540); upscale 2x to 1920x1080.
    with Image.open(io.BytesIO(png)) as img:
        assert img.size == (1920, 1080)
        assert img.getpixel((960, 540)) == (255, 0, 0)
        assert img.getpixel((1440, 810)) == (0, 0, 0)
    assert "full_x = 500 + (1000-500) * crop_x / 1000" in note
    assert "full_y = 500 + (1000-500) * crop_y / 1000" in note
    assert cu_macos._screen_point_size == (1920, 1080)
    # Correct model-side conversion of crop center -> full-screen (750,750).
    await ClickTool().execute(x=750, y=750)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1440, 810)
    # Current tools do NOT automatically convert crop-relative input.
    await ClickTool().execute(x=500, y=500)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (960, 540)


async def test_small_crop_caps_zoom_at_three_without_changing_click_space(capture_chain):
    from PIL import Image

    quartz, _ = capture_chain
    result = await ScreenshotTool().execute(region=[700, 700, 800, 800])
    png, _ = screenshot_wire_image(result)
    with Image.open(io.BytesIO(png)) as img:
        # 192x108 crop is capped at 3x, rather than enlarged 10x to full size.
        assert img.size == (576, 324)
        assert img.getpixel((288, 162)) == (255, 0, 0)
    assert cu_macos._screen_point_size == (1920, 1080)
    await ClickTool().execute(x=750, y=750)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1440, 810)


@pytest.mark.parametrize(("kwargs", "expected"), [
    ({"x": "690", "y": 288}, (1324, 311)),
    ({"bbox": [700, 700, 800, 800]}, (1440, 810)),
    ({"x": 0, "y": 0}, (0, 0)),
    ({"x": 1000, "y": 1000}, (1919, 1079)),
])
async def test_model_arguments_reach_quartz_after_real_capture(capture_chain, kwargs, expected):
    quartz, _ = capture_chain
    await ScreenshotTool().execute()
    result = await ClickTool().execute(**kwargs)
    assert not result.error
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == expected


@pytest.mark.parametrize(("x", "y"), [
    (1030, 403), (-1, 100), ("nan", 500), (float("inf"), 500),
    (-0.5, 100), (1000.5, 100),
    ([900, 100, 1100, 200], None),
])
@pytest.mark.parametrize("use_executor", [False, True])
async def test_macos_rejects_invalid_coordinates_before_injection(
    capture_chain, x, y, use_executor,
):
    from tank_backend.computer.executor import _MacOSExecutor

    quartz, _ = capture_chain
    if use_executor:
        executor = _MacOSExecutor()
        await executor.screenshot()
        with pytest.raises(ValueError, match="coordinates"):
            await executor.click(x, y)
    else:
        await ScreenshotTool().execute()
        result = await ClickTool().execute(x=x, y=y)
        assert result.error
    quartz.CGEventCreateMouseEvent.assert_not_called()


async def test_batch_replays_calculator_miss_and_returns_wire_screenshot(capture_chain):
    """Replay 20260918-082609/calc-open/1 trace lines 134/182.

    Bounds are manually measured from shot_001.png, not model predictions.
    This proves execution of supplied wrong coordinates, not model accuracy.
    """
    from PIL import Image

    from tank_backend.tools.computer_use_common import ComputerBatchTool

    quartz, _ = capture_chain
    screenshot = ScreenshotTool()
    click = ClickTool()
    await screenshot.execute()
    await click.execute(x="690", y=288)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1324, 311)
    result = await ComputerBatchTool({"click": click, "screenshot": screenshot}).execute(
        actions=[
            {"action": "click", "x": 643, "y": 323},
            {"action": "click", "x": 785, "y": 323},
            {"action": "click", "x": 685, "y": 323},
            {"action": "click", "x": 775, "y": 433},
        ],
    )
    assert not result.error
    points = [call.args[2] for call in quartz.CGEventCreateMouseEvent.call_args_list[::2]]
    assert points == [(1324, 311), (1234, 348), (1507, 348), (1315, 348), (1488, 467)]
    assert all(x > 1192 for x, _ in points)  # Right of the entire calculator window.
    png, _ = screenshot_wire_image(result)
    with Image.open(io.BytesIO(png)) as img:
        assert img.size == (1920, 1080)


async def test_executor_and_tool_keep_maximum_inside_display(capture_chain):
    from tank_backend.computer.executor import _MacOSExecutor

    quartz, _ = capture_chain
    await ScreenshotTool().execute()
    await ClickTool().execute(x=1000, y=1000)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1919, 1079)
    executor = _MacOSExecutor()
    await executor.screenshot()
    await executor.click(1000, 1000)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1919, 1079)


@pytest.mark.parametrize("region", [None, [500, 500, 1000, 1000]])
@pytest.mark.parametrize("image_mode", [False, True])
async def test_http_tool_loop_preserves_image_and_fragmented_coordinates(
    capture_chain, monkeypatch, region, image_mode,
):
    """Real SDK JSON + SSE parser + ToolManager, fake HTTP and OS only."""
    import httpx
    from openai import AsyncOpenAI
    from PIL import Image

    from tank_backend.llm import llm as llm_module
    from tank_backend.tools.manager import ToolManager

    quartz, _ = capture_chain
    requests: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == "/v1/chat/completions"
        turn = len(requests)
        deltas = []
        if turn <= 2:
            name = "screenshot" if turn == 1 else "click"
            args = json.dumps({"region": region} if region else {}) if turn == 1 else (
                '{"bbox":[700,700,800,800]}'
            )
            if image_mode:
                if turn == 1:
                    args = json.dumps(
                        {
                            "coordinate_space": "image",
                            **({"region": region} if region else {}),
                        }
                    )
                else:
                    import hashlib

                    parts = next(
                        m["content"]
                        for m in body["messages"]
                        if isinstance(m.get("content"), list)
                    )
                    text = next(p["text"] for p in parts if p["type"] == "text")
                    metadata = json.loads(text[text.index("{") :])
                    url = next(
                        p["image_url"]["url"] for p in parts if p["type"] == "image_url"
                    )
                    assert (
                        hashlib.sha256(
                            base64.b64decode(url.split(",", 1)[1])
                        ).hexdigest()
                        == metadata["image_sha256"]
                    )
                    args = json.dumps(
                        {
                            "coordinate_space": "image",
                            "frame_id": metadata["frame_id"],
                            "x": 960 if region else 1440,
                            "y": 540 if region else 810,
                        }
                    )
                import jsonschema

                schema = next(
                    t["function"]["parameters"]
                    for t in body["tools"]
                    if t["function"]["name"] == name
                )
                jsonschema.validate(json.loads(args), schema)
            deltas.append({"tool_calls": [{"index": 0, "id": f"call-{turn}",
                           "type": "function", "function": {"name": name, "arguments": ""}}]})
            # Split inside numbers/JSON punctuation to exercise accumulation.
            deltas.extend({"tool_calls": [{"index": 0, "function": {"arguments": c}}]}
                          for c in args)
        else:
            assert turn == 3
            deltas.append({"content": "done"})
        chunks = [{"id": "probe", "object": "chat.completion.chunk", "created": 1,
                   "model": "test", "choices": [{"index": 0, "delta": delta,
                   "finish_reason": None}]} for delta in deltas]
        chunks.append({"id": "probe", "object": "chat.completion.chunk", "created": 1,
                       "model": "test", "choices": [], "usage": {
                           "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
        sse = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse)

    client = AsyncOpenAI(api_key="test", base_url="https://probe.invalid/v1",
                         http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(llm_module, "AsyncOpenAI", lambda **kwargs: client)
    monkeypatch.setattr(llm_module, "initialize_langfuse", lambda: None)
    llm = llm_module.LLM(api_key="test", model="test", base_url="https://probe.invalid/v1")
    # Skip unrelated tool registration; dispatch and schemas are real methods.
    manager = ToolManager.__new__(ToolManager)
    manager.tools = {"screenshot": ScreenshotTool(), "click": ClickTool()}
    manager._bus = None
    manager._media_store = None
    manager._session_id = None
    if image_mode:
        from tank_backend.tools.groups import ComputerUseToolGroup

        quartz.CGMainDisplayID.return_value = 5
        quartz.CGDisplayBounds.return_value = ((0, 0), (1920, 1080))
        manager.tools = {t.get_info().name: t for t in ComputerUseToolGroup()._create_macos_tools()}
        manager.set_session_id("http-frame")
    try:
        updates = [event async for event in llm.chat_stream(
            [{"role": "user", "content": "capture then click the target"}],
            tools=manager.get_openai_tools(), tool_executor=manager,
        )]
    finally:
        await client.close()
    assert updates
    assert len(requests) == 3
    follow_up = next(msg for msg in requests[1]["messages"] if isinstance(msg.get("content"), list))
    wire = next(p["image_url"] for p in follow_up["content"] if p["type"] == "image_url")
    assert wire["detail"] == "auto"
    with Image.open(io.BytesIO(base64.b64decode(wire["url"].split(",", 1)[1]))) as img:
        assert img.size == (1920, 1080)
        target = (960, 540) if region else (1440, 810)
        assert img.getpixel(target) == (255, 0, 0)
    assert requests[2]["messages"][3]["content"] == follow_up["content"]
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1440, 810)
    click_reply = next(m for m in requests[2]["messages"] if m.get("name") == "click")
    assert "(1440, 810)" in click_reply["content"]


@pytest.mark.parametrize("filename", [
    "synthetic-model-results.json", "synthetic-complex-results.json",
    "synthetic-resolution-results.json",
])
async def test_recorded_synthetic_model_coordinates_reach_expected_points(capture_chain, filename):
    """Replay actual responses locally; no API calls or real mouse events."""
    import hashlib

    from PIL import Image

    from tank_backend.tools.computer_use_common import crop_and_upscale

    quartz, _ = capture_chain
    await ScreenshotTool().execute()
    reports = Path(__file__).resolve().parents[2] / "benchmarks/computer_use/reports"
    evidence = reports / "20260919-synthetic-coordinate-isolation"
    raw = (evidence / ("synthetic.png" if filename == "synthetic-model-results.json"
                       else "synthetic-complex.png")).read_bytes()
    for row in json.loads((evidence / filename).read_text())["results"]:
        png = raw
        if row["region"]:
            png = crop_and_upscale(raw, tuple(row["region"]), (1920, 1080))
        elif row["image_size"] != [1920, 1080]:
            buffer = io.BytesIO()
            with Image.open(io.BytesIO(raw)) as image:
                image.resize(tuple(row["image_size"]), Image.Resampling.LANCZOS).save(
                    buffer, format="PNG",
                )
            png = buffer.getvalue()
        assert hashlib.sha256(png).hexdigest() == row["sha256"]
        assert all(request["image_hashes"] == [row["sha256"]] for request in row["requests"])
        for call in row["calls"]:
            if call["name"] != "click":
                assert call["pixel"] is None and not call["inside_target"]
                continue
            quartz.CGEventCreateMouseEvent.reset_mock()
            result = await ClickTool().execute(**call["arguments"])
            if call["pixel"] is None:
                assert result.error
                quartz.CGEventCreateMouseEvent.assert_not_called()
            else:
                assert not result.error
                point = quartz.CGEventCreateMouseEvent.call_args.args[2]
                assert list(point) == call["pixel"]
                box = (994, 413, 1048, 455) if row["target"] == "AC" else (928, 467, 982, 509)
                assert call["inside_target"] == (
                    box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]
                )


async def test_frame_crop_click_uses_image_pixels_through_tool_manager(capture_chain):
    from tank_backend.tools.groups import ComputerUseToolGroup
    from tank_backend.tools.manager import ToolManager

    quartz, _ = capture_chain
    quartz.CGMainDisplayID.return_value = 5
    quartz.CGDisplayBounds.return_value = ((0, 0), (1920, 1080))
    manager = ToolManager.__new__(ToolManager)
    manager.tools = {
        t.get_info().name: t for t in ComputerUseToolGroup()._create_macos_tools()
    }
    manager._bus = None
    manager._media_store = None
    manager.set_session_id("frame-test")
    shot = await manager.execute_tool(
        "screenshot",
        coordinate_space="image",
        region=[500, 500, 1000, 1000],
    )
    assert not isinstance(shot, str) and not shot.error
    png, note = screenshot_wire_image(shot)
    metadata = json.loads(note[note.index("{") :])
    import hashlib

    assert metadata["image_sha256"] == hashlib.sha256(png).hexdigest()
    result = await manager.execute_tool(
        "click",
        coordinate_space="image",
        frame_id=metadata["frame_id"],
        x=960,
        y=540,
    )
    assert not isinstance(result, str) and not result.error
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1440, 810)


@pytest.fixture
def frame_manager(capture_chain):
    from tank_backend.tools.groups import ComputerUseToolGroup
    from tank_backend.tools.manager import ToolManager

    quartz, _ = capture_chain
    quartz.CGMainDisplayID.return_value = 5
    quartz.CGDisplayBounds.return_value = ((0, 0), (1920, 1080))
    manager = ToolManager.__new__(ToolManager)
    manager.tools = {
        t.get_info().name: t for t in ComputerUseToolGroup()._create_macos_tools()
    }
    manager._bus = None
    manager._media_store = None
    manager.set_session_id("owner")
    return manager, quartz


async def frame_metadata(manager, **kwargs):
    result = await manager.execute_tool(
        "screenshot", coordinate_space="image", **kwargs
    )
    assert not isinstance(result, str) and not result.error, result
    _, note = screenshot_wire_image(result)
    return json.loads(note[note.index("{") :])


@pytest.mark.parametrize("change", ["missing", "old", "session", "geometry", "scene"])
async def test_frame_rejects_unusable_observation_without_input(frame_manager, change):
    manager, quartz = frame_manager
    metadata = await frame_metadata(manager)
    frame_id = metadata["frame_id"]
    if change == "missing":
        frame_id = None
    elif change == "old":
        await frame_metadata(manager)
    elif change == "session":
        manager.set_session_id("other")
    elif change == "geometry":
        quartz.CGMainDisplayID.return_value = 6
    from contextlib import nullcontext

    changed_capture = patch(
        f"{MODULE}._capture_screenshot_macos", return_value=make_png(1920, 1080)
    )
    with changed_capture if change == "scene" else nullcontext():
        # All previous frames were black with a red rectangle: this is a changed scene.
        result = await manager.execute_tool(
            "click",
            coordinate_space="image",
            frame_id=frame_id,
            x=100,
            y=100,
        )
    assert result.error
    quartz.CGEventCreateMouseEvent.assert_not_called()


@pytest.mark.parametrize(
    ("name", "args", "points"),
    [
        ("click", {"bbox": [900, 500, 1020, 580]}, [(1440, 810)]),
        ("mouse_move", {"x": 960, "y": 540}, [(1440, 810)]),
        ("scroll", {"amount": 2, "x": 960, "y": 540}, [(1440, 810)]),
        ("drag", {"x1": 0, "y1": 0, "x2": 960, "y2": 540}, [(960, 540), (1440, 810)]),
    ],
)
async def test_frame_coordinate_actions_share_crop_mapping(
    frame_manager, name, args, points
):
    manager, quartz = frame_manager
    metadata = await frame_metadata(manager, region=[500, 500, 1000, 1000])
    result = await manager.execute_tool(
        name,
        coordinate_space="image",
        frame_id=metadata["frame_id"],
        **args,
    )
    assert not result.error, result
    delivered = [call.args[2] for call in quartz.CGEventCreateMouseEvent.call_args_list]
    assert delivered[0] == points[0]
    assert delivered[-1] == points[-1]
    if name == "mouse_move":
        assert len(delivered) == 1
    if name == "scroll":
        quartz.CGEventCreateScrollWheelEvent.assert_called_once()
    if name == "drag":
        assert len(delivered) > 2


@pytest.mark.parametrize("scene_changes", [False, True])
async def test_frame_batch_keeps_owner_and_stops_after_scene_change(
    frame_manager, scene_changes
):
    manager, quartz = frame_manager
    metadata = await frame_metadata(manager)
    original_post = quartz.CGEventPost

    def post(*args):
        original_post(*args)
        if scene_changes:
            quartz.CGMainDisplayID.return_value = 6

    with patch.object(quartz, "CGEventPost", side_effect=post):
        result = await manager.execute_tool(
            "computer_batch",
            coordinate_space="image",
            frame_id=metadata["frame_id"],
            actions=[
                {"action": "click", "x": 100, "y": 100},
                {"action": "click", "x": 200, "y": 200},
            ],
        )
    assert result.error == scene_changes, result
    assert quartz.CGEventCreateMouseEvent.call_count == (2 if scene_changes else 4)
    if not scene_changes:
        _, note = screenshot_wire_image(result)
        assert "frame_id" in note


@pytest.mark.parametrize("window_bound", [False, True])
@pytest.mark.parametrize("change_inside", [False, True])
async def test_scene_validation_uses_observed_scope(
    frame_manager, window_bound, change_inside,
):
    """Menu-bar changes invalidate full frames, but not unchanged window crops."""
    from PIL import Image

    manager, quartz = frame_manager
    quartz.CGWindowListCopyWindowInfo.return_value = [{
        "kCGWindowNumber": 42,
        "kCGWindowBounds": {"X": 600, "Y": 100, "Width": 674, "Height": 408},
    }]
    before = Image.new("RGB", (1920, 1080), "black")
    after = before.copy()
    after.putpixel((1000, 250) if change_inside else (1750, 10), (255, 255, 255))

    def png(image):
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return buffer.getvalue()

    kwargs = {"window_id": 42} if window_bound else {}
    with patch(f"{MODULE}._capture_screenshot_macos", return_value=png(before)):
        metadata = await frame_metadata(manager, **kwargs)
    with patch(f"{MODULE}._capture_screenshot_macos", return_value=png(after)):
        result = await manager.execute_tool(
            "click", coordinate_space="image", frame_id=metadata["frame_id"],
            x=100, y=100,
        )
    rejected = change_inside or not window_bound
    assert result.error is rejected
    if rejected:
        assert "Scene or geometry changed" in result.content
        quartz.CGEventCreateMouseEvent.assert_not_called()
    else:
        assert quartz.CGEventCreateMouseEvent.call_count == 2


@pytest.mark.parametrize("moved", [False, True])
async def test_frame_window_origin_is_bound_and_revalidated(frame_manager, moved):
    manager, quartz = frame_manager
    window = {
        "kCGWindowNumber": 42,
        "kCGWindowBounds": {
            "X": 300,
            "Y": 200,
            "Width": 800,
            "Height": 600,
        },
    }
    quartz.CGWindowListCopyWindowInfo.return_value = [window]
    metadata = await frame_metadata(manager, window_id=42)
    assert metadata["window_id"] == 42
    assert metadata["crop"] == [300, 200, 1100, 800]
    if moved:
        window["kCGWindowBounds"]["X"] = 350
    result = await manager.execute_tool(
        "click",
        coordinate_space="image",
        frame_id=metadata["frame_id"],
        x=metadata["image_size"][0] / 2,
        y=metadata["image_size"][1] / 2,
    )
    assert result.error == moved, result
    if moved:
        quartz.CGEventCreateMouseEvent.assert_not_called()
    else:
        assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (700, 500)


@pytest.mark.parametrize(
    "region",
    [[-1, 0, 100, 100], [0, 0, 1001, 100], [0, 0, True, 100], [999, 999, 999, 1000]],
)
async def test_frame_rejects_invalid_crop_instead_of_clamping(frame_manager, region):
    manager, quartz = frame_manager
    result = await manager.execute_tool(
        "screenshot", coordinate_space="image", region=region
    )
    assert result.error
    quartz.CGEventPost.assert_not_called()


async def test_frame_scroll_without_coordinates_needs_no_observation(frame_manager):
    manager, quartz = frame_manager
    result = await manager.execute_tool("scroll", coordinate_space="image", amount=2)
    assert not result.error
    quartz.CGEventCreateMouseEvent.assert_not_called()
    quartz.CGEventCreateScrollWheelEvent.assert_called_once()


@pytest.mark.parametrize(
    "bad",
    [
        {"x": -1, "y": 3},
        {"x": 1920, "y": 3},
        {"x": True, "y": 3},
        {"x": "1", "y": 3},
        {"x": float("nan"), "y": 3},
        {"bbox": [300, 300, 200, 400]},
        {"bbox": [0, 0, 2000, 400]},
        {"bbox": [1, 2, 3, 4], "x": 2, "y": 3},
        {"x": 1, "y": 2, "surprise": 3},
    ],
)
async def test_frame_bad_arguments_never_reach_os(frame_manager, bad):
    manager, quartz = frame_manager
    metadata = await frame_metadata(manager)
    result = await manager.execute_tool(
        "click", coordinate_space="image", frame_id=metadata["frame_id"], **bad
    )
    assert result.error
    quartz.CGEventPost.assert_not_called()


@pytest.mark.parametrize(
    "capture_chain",
    [
        (1920, 1080, 1, False),
        (1600, 1000, 1.5, False),
        (1512, 982, 2, False),
    ],
    indirect=True,
)
@pytest.mark.parametrize("region", [None, [500, 500, 1000, 1000], [700, 700, 800, 800]])
async def test_frame_retina_crop_and_edge_rounding(capture_chain, region):
    from tank_backend.tools.base import ToolContext
    from tank_backend.tools.computer_frame import FrameState, FrameTool

    quartz, _ = capture_chain
    width = quartz.CGDisplayModeGetWidth()
    height = quartz.CGDisplayModeGetHeight()
    quartz.CGMainDisplayID.return_value = 5
    quartz.CGDisplayBounds.return_value = ((0, 0), (width, height))
    state = FrameState()
    ctx = ToolContext(session_id="scale")
    shot = await FrameTool(ScreenshotTool(), state).execute(
        coordinate_space="image",
        ctx=ctx,
        **({"region": region} if region else {}),
    )
    png, note = screenshot_wire_image(shot)
    metadata = json.loads(note[note.index("{") :])
    image_w, image_h = metadata["image_size"]
    left, top, right, bottom = metadata["crop"]
    for x, y, expected in [
        (0, 0, (left, top)),
        (image_w - 1, image_h - 1, (right - 1, bottom - 1)),
    ]:
        result = await FrameTool(ClickTool(), state).execute(
            coordinate_space="image",
            frame_id=metadata["frame_id"],
            ctx=ctx,
            x=x,
            y=y,
        )
        assert not isinstance(result, str) and not result.error
        assert quartz.CGEventCreateMouseEvent.call_args.args[2] == expected


@pytest.mark.parametrize(
    "rect", [(-10, 20, 100, 100), (1920, 20, 100, 100), (10, -1, 100, 100)]
)
async def test_frame_rejects_non_main_window(frame_manager, rect):
    manager, quartz = frame_manager
    quartz.CGWindowListCopyWindowInfo.return_value = [
        {
            "kCGWindowNumber": 42,
            "kCGWindowBounds": dict(
                zip(("X", "Y", "Width", "Height"), rect, strict=True)
            ),
        }
    ]
    result = await manager.execute_tool(
        "screenshot", coordinate_space="image", window_id=42
    )
    assert result.error
    quartz.CGEventPost.assert_not_called()


async def test_frame_cancel_during_revalidation_never_dispatches(frame_manager):
    import asyncio
    import threading

    manager, quartz = frame_manager
    metadata = await frame_metadata(manager)
    started, release = threading.Event(), threading.Event()

    def capture(**kwargs):
        started.set()
        assert release.wait(5)
        return make_png(1920, 1080)

    with patch(f"{MODULE}._capture_screenshot_macos", side_effect=capture):
        pending = asyncio.create_task(
            manager.execute_tool(
                "click",
                coordinate_space="image",
                frame_id=metadata["frame_id"],
                x=1,
                y=2,
            )
        )
        assert await asyncio.to_thread(started.wait, 5)
        pending.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
    quartz.CGEventPost.assert_not_called()


async def test_frame_crop_ignores_pixels_outside_observed_region(frame_manager):
    from PIL import Image

    manager, quartz = frame_manager
    metadata = await frame_metadata(manager, region=[500, 500, 1000, 1000])
    original = cu_macos._capture_screenshot_macos(include_cursor=False)
    with Image.open(io.BytesIO(original)) as image:
        image.putpixel((10, 10), (1, 2, 3))
        changed = io.BytesIO()
        image.save(changed, format="PNG")
    with patch(f"{MODULE}._capture_screenshot_macos", return_value=changed.getvalue()):
        result = await manager.execute_tool(
            "click", coordinate_space="image", frame_id=metadata["frame_id"], x=960, y=540,
        )
    assert not result.error
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1440, 810)
