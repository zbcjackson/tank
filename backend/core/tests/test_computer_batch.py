"""A10: computer_batch — sequential actions, fail-fast, auto screenshot."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

from tank_backend.tools.base import ToolResult
from tank_backend.tools.computer_use_common import ComputerBatchTool


def _fake_tool(name: str, *, error: bool = False, calls: list | None = None):
    tool = MagicMock()
    tool.get_info.return_value = MagicMock(name=name)

    async def run(**kwargs: Any):
        if calls is not None:
            calls.append((name, kwargs))
        if error:
            return ToolResult(content=f"{name} failed", error=True)
        return ToolResult(content=f"{name} ok")

    tool.execute = run
    return tool


def _screenshot_tool(shots: list):
    from tank_backend.core.content import TextBlock

    tool = MagicMock()

    async def run(**kwargs: Any):
        shots.append(kwargs)
        return ToolResult(content=[TextBlock(text="Screenshot captured. NOTE")])

    tool.execute = run
    return tool


def _tools(**overrides):
    tools: dict[str, Any] = {
        "click": _fake_tool("click"),
        "type_text": _fake_tool("type_text"),
        "screenshot": _screenshot_tool([]),
    }
    tools.update(overrides)
    return tools


async def test_sequence_executes_in_order():
    calls: list = []
    tools = _tools(
        click=_fake_tool("click", calls=calls),
        type_text=_fake_tool("type_text", calls=calls),
    )
    result = await ComputerBatchTool(tools).execute(
        actions=[{"action": "click", "x": 1}, {"action": "type_text", "text": "hi"}],
    )
    assert result.error is False
    data = json.loads(result.content)
    assert data["failed_at"] is None
    assert [s["status"] for s in data["steps"]] == ["ok", "ok"]
    assert [c[0] for c in calls] == ["click", "type_text"]


async def test_fail_fast_records_skipped():
    calls: list = []
    tools = _tools(
        click=_fake_tool("click", error=True, calls=calls),
        type_text=_fake_tool("type_text", calls=calls),
    )
    result = await ComputerBatchTool(tools).execute(
        actions=[{"action": "click", "x": 1}, {"action": "type_text", "text": "a"}],
    )
    data = json.loads(result.content)
    assert data["failed_at"] == 0
    assert data["steps"][0]["status"] == "error"
    assert data["skipped"] == ["type_text"]
    assert calls == [("click", {"x": 1})]


async def test_wait_action_and_clamp(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr("tank_backend.tools.computer_use_common.asyncio.sleep", fake_sleep)
    result = await ComputerBatchTool(_tools()).execute(
        actions=[{"action": "wait", "delay_s": 99}, {"action": "wait"}],
    )
    assert result.error is False
    assert sleeps == [5.0, 1.0]


async def test_auto_screenshot_once_after_batch():
    shots: list = []
    tool = ComputerBatchTool(_tools(screenshot=_screenshot_tool(shots)))
    result = await tool.execute(actions=[{"action": "click", "x": 1}])
    assert len(shots) == 1
    assert "Screenshot captured" in json.loads(result.content)["screenshot"]

    await tool.execute(actions=[{"action": "click", "x": 1}], screenshot=False)
    assert len(shots) == 1


async def test_batch_returns_image_to_llm_and_benchmark(tmp_path):
    from tank_backend.benchmarks.driver import TracedScreenshotTool
    from tank_backend.benchmarks.trace import TraceSink
    from tank_backend.core.content import ImageBlock, TextBlock

    image = ImageBlock(source="data:image/png;base64,aGVsbG8=", mime_type="image/png")
    screenshot = MagicMock()

    async def capture(**kwargs):
        return ToolResult(content=[TextBlock(text="Screenshot captured. NOTE"), image])

    screenshot.execute = capture
    tool = ComputerBatchTool(_tools(screenshot=screenshot))
    trace = TraceSink(tmp_path)
    try:
        result = await TracedScreenshotTool(tool, lambda: trace).execute(
            actions=[{"action": "click", "x": 1}],
        )
        assert isinstance(result, ToolResult) and isinstance(result.content, list)
        assert result.content[-1] == image
        assert isinstance(result.content[0], TextBlock)
        assert json.loads(result.content[0].text)["failed_at"] is None
        assert trace.screenshot_count == 1
    finally:
        trace.close()


async def test_unknown_action_errors():
    result = await ComputerBatchTool(_tools()).execute(actions=[{"action": "explode"}])
    assert result.error is True
    assert "explode" in result.content


async def test_empty_actions_error():
    result = await ComputerBatchTool(_tools()).execute(actions=[])
    assert result.error is True


def test_category_is_computer():
    assert ComputerBatchTool(_tools()).get_metadata().category == "computer"
