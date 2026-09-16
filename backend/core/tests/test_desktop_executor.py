"""Tests for DesktopExecutor — the capability interface for plugin agents.

Bash and file operations run for real (they only touch tmp dirs); the
desktop primitives are exercised by mocking the platform backends
(``computer_use`` module attributes), mirroring the tool tests.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tank_backend.computer.executor import (
    _SUDO_RE,
    BashResult,
    create_desktop_executor,
)
from tank_backend.tools import computer_use
from tank_backend.tools.computer_use_common import normalized_to_pixel


def _make_png(w: int, h: int) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def executor(tmp_path: Path):
    ex = create_desktop_executor(cwd=tmp_path)
    ex._size = (1000, 1000)
    return ex


# ---------------------------------------------------------------------------
# sudo guard
# ---------------------------------------------------------------------------


class TestSudoGuard:
    def test_rejects_leading_sudo(self):
        assert _SUDO_RE.search("sudo rm -rf /")

    def test_rejects_sudo_in_pipeline(self):
        assert _SUDO_RE.search("echo hi && sudo apt install x")
        assert _SUDO_RE.search("echo hi ; su - root")
        assert _SUDO_RE.search("cat f | sudo tee /etc/hosts")

    def test_allows_sudo_as_word(self):
        assert _SUDO_RE.search("echo sudo") is None
        assert _SUDO_RE.search("catalog sudoish") is None

    @pytest.mark.asyncio
    async def test_bash_rejects_sudo(self, executor):
        with pytest.raises(PermissionError):
            await executor.bash("sudo echo hi")


# ---------------------------------------------------------------------------
# bash: cwd persistence / exit code / truncation
# ---------------------------------------------------------------------------


class TestBash:
    @pytest.mark.asyncio
    async def test_exit_code_and_stdout(self, executor):
        result = await executor.bash("echo hello")
        assert isinstance(result, BashResult)
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert "__TANK_PWD__" not in result.stdout

    @pytest.mark.asyncio
    async def test_failure_exit_code(self, executor):
        result = await executor.bash("exit 3")
        assert result.exit_code == 3

    @pytest.mark.asyncio
    async def test_cwd_persists(self, executor, tmp_path: Path):
        sub = tmp_path / "sub"
        await executor.bash("mkdir sub && cd sub")
        result = await executor.bash("pwd")
        assert Path(result.stdout.strip()).resolve() == sub.resolve()

    @pytest.mark.asyncio
    async def test_output_truncated(self, executor):
        result = await executor.bash("python3 -c \"print('x' * 30000)\"")
        assert result.truncated is True
        assert len(result.stdout) < 12000
        assert "truncated" in result.stdout


# ---------------------------------------------------------------------------
# file operations
# ---------------------------------------------------------------------------


class TestFiles:
    @pytest.mark.asyncio
    async def test_write_read_roundtrip(self, executor, tmp_path: Path):
        await executor.write_file("notes.txt", "hello world")
        assert (tmp_path / "notes.txt").read_text() == "hello world"
        assert await executor.read_file("notes.txt") == "hello world"

    @pytest.mark.asyncio
    async def test_relative_path_resolves_against_cwd(self, executor, tmp_path):
        await executor.write_file("rel.txt", "x")
        assert (tmp_path / "rel.txt").exists()

    @pytest.mark.asyncio
    async def test_edit_requires_unique_match(self, executor):
        await executor.write_file("f.txt", "one two one")
        with pytest.raises(ValueError):
            await executor.edit_file("f.txt", "one", "1")  # appears twice

    @pytest.mark.asyncio
    async def test_edit_replaces_unique_match(self, executor):
        await executor.write_file("f.txt", "alpha beta")
        await executor.edit_file("f.txt", "beta", "gamma")
        assert await executor.read_file("f.txt") == "alpha gamma"

    @pytest.mark.asyncio
    async def test_edit_missing_match_errors(self, executor):
        await executor.write_file("f.txt", "alpha")
        with pytest.raises(ValueError):
            await executor.edit_file("f.txt", "nope", "x")


# ---------------------------------------------------------------------------
# wait clamp
# ---------------------------------------------------------------------------


class TestWait:
    @pytest.mark.asyncio
    async def test_wait_clamped(self, executor):
        with patch(
            "tank_backend.computer.executor.asyncio.sleep", new=AsyncMock()
        ) as mock_sleep:
            await executor.wait(0)
            await executor.wait(99)
        mock_sleep.assert_any_call(0.1)
        mock_sleep.assert_any_call(5.0)


# ---------------------------------------------------------------------------
# batch (A10 semantics against executor methods)
# ---------------------------------------------------------------------------


class TestBatch:
    @pytest.mark.asyncio
    async def test_batch_runs_in_order(self, executor):
        calls = []

        async def fake_click(x, y, button="left", clicks=1):
            calls.append(("click", x, y))

        async def fake_type(text):
            calls.append(("type", text))

        with (
            patch.object(executor, "click", fake_click),
            patch.object(executor, "type_text", fake_type),
            patch.object(executor, "screenshot", AsyncMock()),
        ):
            result = await executor.batch(
                [
                    {"action": "click", "x": 100, "y": 200},
                    {"action": "type_text", "text": "hi"},
                ]
            )

        assert calls == [("click", 100, 200), ("type", "hi")]
        assert result.failed_at is None
        assert result.skipped == ()
        assert [s.action for s in result.steps] == ["click", "type_text"]
        assert all(s.ok for s in result.steps)

    @pytest.mark.asyncio
    async def test_batch_fail_fast_with_skipped(self, executor):
        async def bad_click(x, y, button="left", clicks=1):
            raise RuntimeError("nope")

        with (
            patch.object(executor, "click", bad_click),
            patch.object(executor, "type_text", AsyncMock()) as mock_type,
            patch.object(executor, "screenshot", AsyncMock()),
        ):
            result = await executor.batch(
                [
                    {"action": "click", "x": 1, "y": 1},
                    {"action": "type_text", "text": "never"},
                    {"action": "click", "x": 2, "y": 2},
                ]
            )

        mock_type.assert_not_called()
        assert result.failed_at == 0
        assert result.skipped == ("type_text", "click")
        assert result.steps[0].ok is False
        assert "nope" in result.steps[0].detail

    @pytest.mark.asyncio
    async def test_batch_unknown_action_rejected(self, executor):
        with pytest.raises(ValueError):
            await executor.batch([{"action": "hack"}])


# ---------------------------------------------------------------------------
# screenshot + click coordinate math (platform backends mocked)
# ---------------------------------------------------------------------------


class TestPrimitives:
    @pytest.mark.asyncio
    async def test_screenshot_sets_size(self, executor):
        png = _make_png(400, 200)
        with patch.object(
            computer_use, "_capture_screenshot", return_value=png
        ):
            shot = await executor.screenshot()

        assert (shot.width, shot.height) == (400, 200)
        assert shot.region is None
        assert shot.png[:4] == b"\x89PNG"
        assert executor._size == (400, 200)

    @pytest.mark.asyncio
    async def test_screenshot_region_crop(self, executor):
        with patch.object(
            computer_use, "_capture_screenshot", return_value=_make_png(400, 200)
        ):
            shot = await executor.screenshot(region=[0, 0, 500, 1000])

        assert shot.region == (0, 0, 500, 1000)
        assert (shot.width, shot.height) == (400, 200)  # full screen retained

    @pytest.mark.asyncio
    async def test_screenshot_invalid_region_raises(self, executor):
        with patch.object(
            computer_use, "_capture_screenshot", return_value=_make_png(100, 100)
        ), pytest.raises(ValueError):
            await executor.screenshot(region=[500, 100, 100, 600])

    @pytest.mark.asyncio
    async def test_click_converts_normalized_to_pixel(self, executor):
        executor._size = (1000, 1000)
        with (
            patch.object(computer_use, "_ydotool_available", return_value=True),
            patch.object(computer_use, "_click_ydotool") as mock_click,
        ):
            await executor.click(x=250, y=750)

        px, py = normalized_to_pixel(250, 750, (1000, 1000))
        mock_click.assert_called_once_with(px, py, "left", 1)

    @pytest.mark.asyncio
    async def test_click_bbox_center(self, executor):
        with (
            patch.object(computer_use, "_ydotool_available", return_value=True),
            patch.object(computer_use, "_click_ydotool") as mock_click,
        ):
            await executor.click(x=[100, 100, 300, 300], y=None)

        px, py = normalized_to_pixel(200, 200, (1000, 1000))
        mock_click.assert_called_once_with(px, py, "left", 1)

    @pytest.mark.asyncio
    async def test_type_text_routes_ascii_and_unicode(self, executor):
        with (
            patch.object(computer_use, "_ydotool_available", return_value=True),
            patch.object(computer_use, "_type_ydotool") as mock_type,
            patch.object(computer_use, "_paste_linux") as mock_paste,
        ):
            await executor.type_text("abc")
            await executor.type_text("你好")

        mock_type.assert_called_once_with("abc")
        mock_paste.assert_called_once_with("你好")

    @pytest.mark.asyncio
    async def test_key_press_normalizes(self, executor):
        with (
            patch.object(computer_use, "_ydotool_available", return_value=True),
            patch.object(computer_use, "_key_ydotool") as mock_key,
        ):
            await executor.key_press('["cmd", "c"]')

        mock_key.assert_called_once_with(["meta", "c"])


def test_factory_returns_executor():
    ex = create_desktop_executor()
    # Protocol is runtime-checkable on the public surface
    from tank_backend.computer.executor import DesktopExecutor

    assert isinstance(ex, DesktopExecutor)
