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
