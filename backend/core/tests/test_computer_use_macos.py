"""Tests for macOS computer-use tools (screencapture + CGEvent + AppleScript).

Runs on any platform: Quartz is imported lazily inside functions, so these
tests mock ``subprocess.run`` (screencapture/sips/osascript/pbcopy) and the
Quartz-backed helpers directly. A fake ``Quartz`` module is injected into
``sys.modules`` for the clipboard-paste path.
"""

from __future__ import annotations

import io
import sys
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_profile():
    """Minimal LLMProfile-like object for ScreenshotTool."""
    profile = MagicMock()
    profile.name = "computer_use"
    profile.model = "qwen/qwen3.5-27b"
    profile.capabilities = frozenset({"text", "image"})
    return profile


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


@pytest.fixture
def fake_quartz(monkeypatch: pytest.MonkeyPatch) -> _FakeQuartz:
    """Inject a fake Quartz module for functions that ``import Quartz``."""
    quartz = _FakeQuartz()
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


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


class TestNormalizedToPixel:
    def test_identity_at_origin(self):
        assert _normalized_to_pixel(0, 0) == (0, 0)

    def test_max_maps_to_screen_size(self):
        cu_macos._screen_point_size = (2560, 1600)
        assert _normalized_to_pixel(1000, 1000) == (2560, 1600)

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
        assert _normalized_to_pixel(1000, 1000) == (1920, 1080)


# ---------------------------------------------------------------------------
# ScreenshotTool
# ---------------------------------------------------------------------------


class TestScreenshotTool:
    @pytest.mark.asyncio
    async def test_returns_image_and_updates_cache(self, fake_profile):
        tool = ScreenshotTool(fake_profile)
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
    async def test_capture_failure(self, fake_profile):
        tool = ScreenshotTool(fake_profile)
        with patch(
            f"{MODULE}._capture_screenshot_macos",
            side_effect=RuntimeError("screencapture failed: no permission"),
        ):
            result = await tool.execute(task="")
        assert result.error is True
        assert "failed to capture" in result.content

    def test_get_info(self, fake_profile):
        info = ScreenshotTool(fake_profile).get_info()
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
    async def test_ascii_escapes_quotes(self):
        tool = TypeTextTool()
        with patch(f"{MODULE}.subprocess.run", return_value=make_run_ok()) as mock_run:
            await tool.execute(text='say "hi"')
        script = mock_run.call_args[0][0][2]
        assert '\\"hi\\"' in script

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
        assert fake_quartz.CGEventCreateKeyboardEvent.call_count == 2  # down + up
        assert fake_quartz.CGEventSetFlags.call_count == 2
        assert result.error is False

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

        fake_quartz.CGEventCreate = MagicMock(
            return_value=MagicMock(getLocation=MagicMock(return_value=(100, 200)))
        )
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
