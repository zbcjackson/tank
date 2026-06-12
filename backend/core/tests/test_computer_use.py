"""Tests for computer-use tools (screenshot, click, type, key, scroll, move)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
        result = await tool.execute(task="")
        assert result.error is True
        assert "required" in result.content

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

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(return_value="Button is at (200, 300)")

        with (
            patch(
                "tank_backend.tools.computer_use._capture_screenshot",
                return_value=fake_png,
            ),
            patch(
                "tank_backend.llm.profile.create_llm_from_profile",
                return_value=mock_llm,
            ),
        ):
            result = await tool.execute(task="find the button")

        assert result.error is False
        assert "200, 300" in result.content[0].text
        mock_llm.complete.assert_called_once()
        messages = mock_llm.complete.call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"][0]["type"] == "image_url"

    @pytest.mark.asyncio
    async def test_vision_llm_failure(self, fake_profile):
        tool = ScreenshotTool(fake_profile)
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("API error"))

        with (
            patch(
                "tank_backend.tools.computer_use._capture_screenshot",
                return_value=fake_png,
            ),
            patch(
                "tank_backend.llm.profile.create_llm_from_profile",
                return_value=mock_llm,
            ),
        ):
            result = await tool.execute(task="find the button")

        assert result.error is True
        assert "vision LLM call failed" in result.content


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
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
                result = await tool.execute(x=100, y=200)
        assert result.error is False
        assert "(100, 200)" in result.content
        mock.assert_called_once_with("click", 100, 200, button="left", clicks=1)

    @pytest.mark.asyncio
    async def test_click_right_double(self):
        tool = ClickTool()
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
                result = await tool.execute(x=50, y=75, button="right", clicks=2)
        assert result.error is False
        mock.assert_called_once_with("click", 50, 75, button="right", clicks=2)

    @pytest.mark.asyncio
    async def test_click_failure(self):
        tool = ClickTool()
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch(
                "tank_backend.tools.computer_use._run_pyautogui",
                side_effect=RuntimeError("fail"),
            ):
                result = await tool.execute(x=0, y=0)
        assert result.error is True

    @pytest.mark.asyncio
    async def test_click_ydotool(self):
        tool = ClickTool()
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=True):
            with patch("tank_backend.tools.computer_use._click_ydotool") as mock:
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
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
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
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
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
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
                result = await tool.execute(keys="enter")
        assert result.error is False
        mock.assert_called_once_with("hotkey", "enter")

    @pytest.mark.asyncio
    async def test_key_combo(self):
        tool = KeyPressTool()
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
                result = await tool.execute(keys="ctrl+c")
        assert result.error is False
        mock.assert_called_once_with("hotkey", "ctrl", "c")

    @pytest.mark.asyncio
    async def test_cmd_alias(self):
        tool = KeyPressTool()
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
                await tool.execute(keys="cmd+space")
        mock.assert_called_once_with("hotkey", "command", "space")

    @pytest.mark.asyncio
    async def test_empty_keys(self):
        tool = KeyPressTool()
        result = await tool.execute(keys="")
        assert result.error is True


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
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
                result = await tool.execute(amount=-3)
        assert result.error is False
        assert "down" in result.content
        mock.assert_called_once_with("scroll", -3)

    @pytest.mark.asyncio
    async def test_scroll_up_at_position(self):
        tool = ScrollTool()
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
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
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch("tank_backend.tools.computer_use._run_pyautogui") as mock:
                result = await tool.execute(x=500, y=600)
        assert result.error is False
        assert "(500, 600)" in result.content
        mock.assert_called_once_with("moveTo", 500, 600)

    @pytest.mark.asyncio
    async def test_move_failure(self):
        tool = MouseMoveTool()
        with patch("tank_backend.tools.computer_use._ydotool_available", return_value=False):
            with patch(
                "tank_backend.tools.computer_use._run_pyautogui",
                side_effect=OSError("no display"),
            ):
                result = await tool.execute(x=0, y=0)
        assert result.error is True
