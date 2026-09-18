"""Tests for macOS computer-use tools (screencapture + CGEvent + AppleScript).

Runs on any platform: Quartz is imported lazily inside functions, so these
tests mock ``subprocess.run`` (screencapture/sips/osascript/pbcopy) and the
Quartz-backed helpers directly. A fake ``Quartz`` module is injected into
``sys.modules`` for the clipboard-paste path.
"""

from __future__ import annotations

import base64
import io
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    quartz.CGDisplayModeGetPixelWidth.return_value = width * scale
    quartz.CGDisplayModeGetWidth.return_value = width
    quartz.CGDisplayModeGetHeight.return_value = height
    quartz.CGPointMake.side_effect = lambda x, y: (x, y)
    paths: list[Path] = []

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        path = Path(args[-1])
        if args[0] == "screencapture":
            paths.append(path)
            img = Image.new("RGB", (width * scale, height * scale), "black")
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


@pytest.mark.parametrize("capture_chain", [(1920, 1080, 2, True)], indirect=True)
@pytest.mark.parametrize("use_executor", [False, True])
async def test_known_resize_failure_uses_retina_pixels_as_points(capture_chain, use_executor):
    """Characterize the existing defect; passing does NOT mean safe fallback.

    When fixed, replace the doubled-position assertion with the logical
    center (960, 540), or assert an explicit screenshot failure.
    """
    from tank_backend.computer.executor import _MacOSExecutor

    quartz, _ = capture_chain
    if use_executor:
        executor = _MacOSExecutor()
        shot = await executor.screenshot()
        assert (shot.width, shot.height) == (3840, 2160)
        await executor.click(500, 500)
    else:
        result = await ScreenshotTool().execute()
        assert not result.error  # Raw Retina fallback is reported as success.
        assert cu_macos._screen_point_size == (3840, 2160)
        await ClickTool().execute(x=500, y=500)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1920, 1080)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] != (960, 540)


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
    ({"x": 1030, "y": 403}, (1920, 435)),
    ({"x": 0, "y": 0}, (0, 0)),
    ({"x": 1000, "y": 1000}, (1920, 1080)),
])
async def test_model_arguments_reach_quartz_after_real_capture(capture_chain, kwargs, expected):
    quartz, _ = capture_chain
    await ScreenshotTool().execute()
    result = await ClickTool().execute(**kwargs)
    assert not result.error
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == expected


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


async def test_executor_and_tool_have_different_edge_rounding(capture_chain):
    from tank_backend.computer.executor import _MacOSExecutor

    quartz, _ = capture_chain
    await ScreenshotTool().execute()
    await ClickTool().execute(x=1000, y=1000)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1920, 1080)
    executor = _MacOSExecutor()
    await executor.screenshot()
    await executor.click(1000, 1000)
    assert quartz.CGEventCreateMouseEvent.call_args.args[2] == (1919, 1079)
