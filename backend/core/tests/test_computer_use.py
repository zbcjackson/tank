"""Tests for computer-use tools (screenshot, click, type, key, scroll, move)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tank_backend.tools.computer_use import (  # noqa: I001
    ClickTool,
    KeyPressTool,
    MouseMoveTool,
    ScreenshotTool,
    ScrollTool,
    TypeTextTool,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_profile():
    """Minimal LLMProfile-like object for ScreenshotTool."""
    profile = MagicMock()
    profile.name = "computer_use"
    profile.api_key = "test-key"
    profile.model = "qwen/qwen3.5-27b"
    profile.base_url = "https://openrouter.ai/api/v1"
    profile.temperature = 0.1
    profile.max_tokens = 4096
    profile.extra_headers = {}
    profile.stream_options = False
    profile.extra_body = {}
    profile.capabilities = frozenset({"text", "image"})
    return profile


# ---------------------------------------------------------------------------
# ScreenshotTool
# ---------------------------------------------------------------------------

class TestScreenshotTool:
    def test_get_info(self, fake_profile):
        tool = ScreenshotTool(fake_profile)
        info = tool.get_info()
        assert info.name == "screenshot"
        assert len(info.parameters) == 1
        assert info.parameters[0].name == "task"

    def test_metadata(self, fake_profile):
        tool = ScreenshotTool(fake_profile)
        meta = tool.get_metadata()
        assert meta.idempotent is True

    @pytest.mark.asyncio
    async def test_missing_task(self, fake_profile):
        tool = ScreenshotTool(fake_profile)
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch(
            "tank_backend.tools.computer_use._capture_screenshot",
            return_value=fake_png,
        ):
            result = await tool.execute(task="")
        assert result.error is False
        assert "Screenshot captured." in result.content[0].text

    @pytest.mark.asyncio
    async def test_screenshot_capture_failure(self, fake_profile):
        tool = ScreenshotTool(fake_profile)
        with patch(
            "tank_backend.tools.computer_use._capture_screenshot",
            side_effect=RuntimeError("no display"),
        ):
            result = await tool.execute(task="find the button")
        assert result.error is True
        assert "failed to capture" in result.content

    @pytest.mark.asyncio
    async def test_screenshot_success(self, fake_profile):
        tool = ScreenshotTool(fake_profile)
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch(
            "tank_backend.tools.computer_use._capture_screenshot",
            return_value=fake_png,
        ):
            result = await tool.execute(task="find the button")

        assert result.error is False
        assert "Screenshot captured." in result.content[0].text
        assert "find the button" in result.content[0].text
        assert result.content[1].source.startswith("data:image/png;base64,")

    @pytest.mark.asyncio
    async def test_screenshot_no_task(self, fake_profile):
        tool = ScreenshotTool(fake_profile)
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        with patch(
            "tank_backend.tools.computer_use._capture_screenshot",
            return_value=fake_png,
        ):
            result = await tool.execute()

        assert result.error is False
        assert "Screenshot captured." in result.content[0].text
        assert "NORMALIZED coordinates" in result.content[0].text


# ---------------------------------------------------------------------------
# ClickTool
# ---------------------------------------------------------------------------

class TestClickTool:
    def test_get_info(self):
        tool = ClickTool()
        info = tool.get_info()
        assert info.name == "click"
        param_names = [p.name for p in info.parameters]
        assert "x" in param_names
        assert "y" in param_names

    @pytest.mark.asyncio
    async def test_click_success(self):
        tool = ClickTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
            patch("tank_backend.tools.computer_use._screen_size", (1000, 1000)),
        ):
            result = await tool.execute(x=100, y=200)
        assert result.error is False
        assert "(100, 200)" in result.content
        mock.assert_called_once_with("click", 100, 200, button="left", clicks=1)

    @pytest.mark.asyncio
    async def test_click_right_double(self):
        tool = ClickTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
            patch("tank_backend.tools.computer_use._screen_size", (1000, 1000)),
        ):
            result = await tool.execute(x=50, y=75, button="right", clicks=2)
        assert result.error is False
        mock.assert_called_once_with("click", 50, 75, button="right", clicks=2)

    @pytest.mark.asyncio
    async def test_click_failure(self):
        tool = ClickTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch(
                "tank_backend.tools.computer_use._run_pyautogui",
                side_effect=RuntimeError("fail"),
            ),
        ):
            result = await tool.execute(x=0, y=0)
        assert result.error is True

    @pytest.mark.asyncio
    async def test_click_ydotool(self):
        tool = ClickTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=True),
            patch("tank_backend.tools.computer_use._click_ydotool") as mock,
            patch("tank_backend.tools.computer_use._screen_size", (1000, 1000)),
        ):
            result = await tool.execute(x=300, y=400)
        assert result.error is False
        assert "(300, 400)" in result.content
        mock.assert_called_once_with(300, 400, "left", 1)


# ---------------------------------------------------------------------------
# TypeTextTool
# ---------------------------------------------------------------------------

class TestTypeTextTool:
    def test_get_info(self):
        tool = TypeTextTool()
        info = tool.get_info()
        assert info.name == "type_text"

    @pytest.mark.asyncio
    async def test_type_success(self):
        tool = TypeTextTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
        ):
            result = await tool.execute(text="hello world")
        assert result.error is False
        assert "hello world" in result.content
        mock.assert_called_once_with("write", "hello world", interval=0)

    @pytest.mark.asyncio
    async def test_type_empty(self):
        tool = TypeTextTool()
        result = await tool.execute(text="")
        assert result.error is True

    @pytest.mark.asyncio
    async def test_type_with_interval(self):
        tool = TypeTextTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
        ):
            result = await tool.execute(text="abc", interval=0.05)
        mock.assert_called_once_with("write", "abc", interval=0.05)
        assert result.error is False


# ---------------------------------------------------------------------------
# KeyPressTool
# ---------------------------------------------------------------------------

class TestKeyPressTool:
    def test_get_info(self):
        tool = KeyPressTool()
        info = tool.get_info()
        assert info.name == "key_press"

    @pytest.mark.asyncio
    async def test_single_key(self):
        tool = KeyPressTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
        ):
            result = await tool.execute(keys="enter")
        assert result.error is False
        mock.assert_called_once_with("hotkey", "enter")

    @pytest.mark.asyncio
    async def test_key_combo(self):
        tool = KeyPressTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
        ):
            result = await tool.execute(keys="ctrl+c")
        assert result.error is False
        mock.assert_called_once_with("hotkey", "ctrl", "c")

    @pytest.mark.asyncio
    async def test_cmd_alias(self):
        """cmd → winleft on the pyautogui (X11) backend; meta on ydotool."""
        tool = KeyPressTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
        ):
            await tool.execute(keys="cmd+space")
        mock.assert_called_once_with("hotkey", "winleft", "space")

    @pytest.mark.asyncio
    async def test_empty_keys(self):
        tool = KeyPressTool()
        result = await tool.execute(keys="")
        assert result.error is True

    @pytest.mark.asyncio
    async def test_double_encoded_json_array(self):
        """Real qwen artifact from the 2026-09-11 baseline: '["return"]'."""
        tool = KeyPressTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
        ):
            result = await tool.execute(keys='["return"]')
        assert result.error is False
        mock.assert_called_once_with("hotkey", "enter")

    @pytest.mark.asyncio
    async def test_garbage_keys_errors_with_guidance(self):
        tool = KeyPressTool()
        result = await tool.execute(keys="[1, 2]")
        assert result.error is True
        assert "enter" in result.content  # valid names listed for self-correction


# ---------------------------------------------------------------------------
# ScrollTool
# ---------------------------------------------------------------------------

class TestScrollTool:
    def test_get_info(self):
        tool = ScrollTool()
        info = tool.get_info()
        assert info.name == "scroll"

    @pytest.mark.asyncio
    async def test_scroll_down(self):
        tool = ScrollTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
        ):
            result = await tool.execute(amount=-3)
        assert result.error is False
        assert "down" in result.content
        mock.assert_called_once_with("scroll", -3)

    @pytest.mark.asyncio
    async def test_scroll_up_at_position(self):
        tool = ScrollTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
            patch("tank_backend.tools.computer_use._screen_size", (1000, 1000)),
        ):
            result = await tool.execute(amount=5, x=400, y=300)
        assert result.error is False
        assert "up" in result.content
        mock.assert_called_once_with("scroll", 5, x=400, y=300)


# ---------------------------------------------------------------------------
# MouseMoveTool
# ---------------------------------------------------------------------------

class TestMouseMoveTool:
    def test_get_info(self):
        tool = MouseMoveTool()
        info = tool.get_info()
        assert info.name == "mouse_move"

    @pytest.mark.asyncio
    async def test_move_success(self):
        tool = MouseMoveTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch("tank_backend.tools.computer_use._run_pyautogui") as mock,
            patch("tank_backend.tools.computer_use._screen_size", (1000, 1000)),
        ):
            result = await tool.execute(x=500, y=600)
        assert result.error is False
        assert "(500, 600)" in result.content
        # 600 normalized → 599 px even on a 1000×1000 screen (n*(size-1)/1000)
        mock.assert_called_once_with("moveTo", 500, 599)

    @pytest.mark.asyncio
    async def test_move_failure(self):
        tool = MouseMoveTool()
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch(
                "tank_backend.tools.computer_use._run_pyautogui",
                side_effect=OSError("no display"),
            ),
        ):
            result = await tool.execute(x=0, y=0)
        assert result.error is True


# ---------------------------------------------------------------------------
# TypeTextTool — non-ASCII clipboard path (A2)
# ---------------------------------------------------------------------------


class TestTypeTextClipboard:
    @pytest.mark.asyncio
    async def test_non_ascii_pastes_via_wl_copy(self):
        """Chinese text → wl-copy + ctrl+v (ydotool), never typed raw."""
        from tank_backend.tools import computer_use as m

        with (
            patch(f"{m.__name__}._ydotool_available", return_value=True),
            patch(f"{m.__name__}._type_ydotool") as raw_type,
            patch(f"{m.__name__}._key_ydotool") as key_mock,
            patch(f"{m.__name__}._paste_linux") as paste,
        ):
            result = await m.TypeTextTool().execute(text="你好，世界")
        assert result.error is False
        raw_type.assert_not_called()
        paste.assert_called_once_with("你好，世界")
        # paste itself: verify wiring in the helper test below
        key_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_paste_uses_wl_copy_then_ctrl_v(self):
        import subprocess as sp
        from unittest.mock import MagicMock

        from tank_backend.tools import computer_use as m

        run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch(
                "shutil.which",
                side_effect=lambda n: f"/usr/bin/{n}" if n == "wl-copy" else None,
            ),
            patch(f"{sp.__name__}.run", run),
            patch(f"{m.__name__}._ydotool_available", return_value=True),
            patch(f"{m.__name__}._key_ydotool") as key_mock,
            patch("time.sleep"),
        ):
            m._paste_linux("你好")
        assert run.call_args[0][0] == ["/usr/bin/wl-copy"]
        assert run.call_args[1]["input"] == "你好".encode()
        key_mock.assert_called_once_with(["ctrl", "v"])

    @pytest.mark.asyncio
    async def test_paste_falls_back_to_xclip(self):
        import subprocess as sp
        from unittest.mock import MagicMock

        from tank_backend.tools import computer_use as m

        run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("shutil.which", side_effect=lambda n: f"/usr/bin/{n}" if n == "xclip" else None),
            patch(f"{sp.__name__}.run", run),
            patch(f"{m.__name__}._ydotool_available", return_value=False),
            patch(f"{m.__name__}._run_pyautogui") as pyag,
            patch("time.sleep"),
        ):
            m._paste_linux("héllo")
        assert run.call_args[0][0] == ["/usr/bin/xclip", "-selection", "clipboard"]
        pyag.assert_called_once_with("hotkey", "ctrl", "v")

    @pytest.mark.asyncio
    async def test_paste_without_tool_errors_with_hint(self):
        from tank_backend.tools import computer_use as m

        with patch("shutil.which", return_value=None):
            result = await m.TypeTextTool().execute(text="你好")
        assert result.error is True
        assert "wl-clipboard" in result.content or "xclip" in result.content

    @pytest.mark.asyncio
    async def test_paste_on_wayland_requires_wl_copy(self, monkeypatch):
        """On Wayland, missing wl-copy must fail fast — xclip hangs there."""
        from tank_backend.tools import computer_use as m

        monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
        with patch("shutil.which", return_value=None):
            result = await m.TypeTextTool().execute(text="你好")
        assert result.error is True
        assert "wl-clipboard" in result.content


class TestYdotoolSocketDiscovery:
    """Ubuntu's systemd ydotoold listens at $XDG_RUNTIME_DIR/.ydotool_socket,
    not the legacy /tmp path — discovery must find it without manual config."""

    def test_xdg_runtime_dir_socket_found(self, tmp_path, monkeypatch):
        from tank_backend.tools import computer_use as m

        (tmp_path / ".ydotool_socket").touch()
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        monkeypatch.delenv("YDOTOOL_SOCKET", raising=False)
        assert m._ydotool_socket() == str(tmp_path / ".ydotool_socket")

    def test_env_override_wins(self, tmp_path, monkeypatch):
        from tank_backend.tools import computer_use as m

        override = tmp_path / "custom.sock"
        override.touch()
        monkeypatch.setenv("YDOTOOL_SOCKET", str(override))
        assert m._ydotool_socket() == str(override)

    def test_none_when_no_socket(self, tmp_path, monkeypatch):
        from tank_backend.tools import computer_use as m

        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        monkeypatch.delenv("YDOTOOL_SOCKET", raising=False)
        assert m._ydotool_socket() is None
