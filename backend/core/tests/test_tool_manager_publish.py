"""Unit tests for Phase 17: ToolManager publishes tool_completed.

After the OCP refactor, ``ToolManager.execute_tool`` doesn't know about
``ImageBlock`` or the ``outbound_attachment`` event — it only publishes
a generic ``tool_completed`` event with the ``(tool_name, result)``
pair. Subscribers (today: :class:`ToolOutputObserver`; tomorrow:
audit logging, telemetry, new content kinds) react without modifying
the manager.

These tests pin the publishing contract: when does the event fire,
what payload does it carry, what failure modes does it tolerate.
The downstream image translation is covered in
``test_tool_output_observer.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tank_backend.config.models import (
    AuditConfig,
    CommandSecurityConfig,
    FileAccessConfig,
    NetworkAccessConfig,
    SandboxConfig,
    SkillsConfig,
)
from tank_backend.core.content import ImageBlock, TextBlock
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.tools.base import BaseTool, ToolInfo, ToolResult
from tank_backend.tools.manager import ToolManager


def _make_app_config() -> MagicMock:
    """Minimal AppConfig stub so ``ToolManager`` can initialise."""
    cfg = MagicMock()
    cfg.network_access = NetworkAccessConfig()
    cfg.file_access = FileAccessConfig()
    cfg.audit = AuditConfig()
    cfg.command_security = CommandSecurityConfig()
    cfg.sandbox = SandboxConfig(enabled=False)
    cfg.skills = SkillsConfig(enabled=False)
    cfg.get_llm_profile = MagicMock(
        side_effect=lambda name: MagicMock(
            api_key="test", model="test", base_url="http://test",
            extra_headers={}, stream_options=False,
        ),
    )
    return cfg


class _ImageReturningTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="test_image_tool",
            description="Test-only tool that returns an ImageBlock.",
            parameters=[],
        )

    async def execute(self, **_kwargs) -> ToolResult:
        return ToolResult(
            content=[
                TextBlock(text="Here's the image:"),
                ImageBlock(
                    source="https://example.com/cat.jpg",
                    mime_type="image/jpeg",
                ),
            ],
            display="A picture of a cat",
        )


class _TextOnlyTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="test_text_tool",
            description="Test-only tool that returns plain text.",
            parameters=[],
        )

    async def execute(self, **_kwargs) -> ToolResult:
        return ToolResult(content="plain string", display="done")


class _RaisingTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="test_raising_tool",
            description="Test-only tool that raises during execute.",
            parameters=[],
        )

    async def execute(self, **_kwargs) -> ToolResult:
        raise RuntimeError("synthetic")


@pytest.fixture()
def tool_manager_with_bus() -> tuple[ToolManager, Bus]:
    bus = Bus()
    tm = ToolManager(app_config=_make_app_config(), bus=bus)
    # Strip default tools so each test starts with a clean registry.
    tm.tools.clear()
    return tm, bus


class TestToolCompletedPublishing:
    async def test_image_returning_tool_publishes_event_with_full_result(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """Happy path: any successful tool — image-returning or
        otherwise — produces exactly one ``tool_completed`` event whose
        payload carries the tool name and the original ``ToolResult``
        unchanged. ``ToolManager`` does not inspect the result here;
        subscribers do."""
        tm, bus = tool_manager_with_bus
        tm.tools["test_image_tool"] = _ImageReturningTool()

        captured: list[BusMessage] = []
        bus.subscribe("tool_completed", captured.append)

        result = await tm.execute_tool("test_image_tool")
        bus.poll()

        assert isinstance(result, ToolResult)
        assert not result.error

        assert len(captured) == 1
        msg = captured[0]
        assert msg.type == "tool_completed"
        # source tag follows the same convention the prior emit used,
        # so anything grepping bus logs by ``tool:<name>`` keeps
        # working across the refactor.
        assert msg.source == "tool:test_image_tool"
        assert msg.payload["tool_name"] == "test_image_tool"
        # The whole ToolResult travels through the event — observers
        # decide what to extract.
        assert msg.payload["result"] is result

    async def test_text_only_tool_still_publishes_event(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """``ToolManager`` publishes ``tool_completed`` for *every*
        tool result, even text-only ones. That's the OCP win:
        observers that care about images filter; observers that want
        every invocation (audit logging, metrics) get them all."""
        tm, bus = tool_manager_with_bus
        tm.tools["test_text_tool"] = _TextOnlyTool()

        captured: list[BusMessage] = []
        bus.subscribe("tool_completed", captured.append)

        await tm.execute_tool("test_text_tool")
        bus.poll()

        assert len(captured) == 1
        assert captured[0].payload["tool_name"] == "test_text_tool"

    async def test_bus_none_is_safe_noop(self) -> None:
        """Some ``ToolManager`` construction paths pass ``bus=None``
        (narrow unit tests, offline tool execution). The publish step
        must not crash — the tool still returns its ``ToolResult``,
        callers just don't get a bus event."""
        tm = ToolManager(app_config=_make_app_config(), bus=None)
        tm.tools.clear()
        tm.tools["test_image_tool"] = _ImageReturningTool()

        # Must not raise.
        result = await tm.execute_tool("test_image_tool")
        assert isinstance(result, ToolResult)
        assert not result.error

    async def test_tool_error_publishes_event_with_error_result(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """When the tool raises, ``execute_tool`` catches and returns
        an error-flagged ``ToolResult``. The event still fires — error
        observers (audit logging, alerting) need to see error
        invocations too."""
        tm, bus = tool_manager_with_bus
        tm.tools["test_raising_tool"] = _RaisingTool()

        captured: list[BusMessage] = []
        bus.subscribe("tool_completed", captured.append)

        result = await tm.execute_tool("test_raising_tool")
        bus.poll()

        assert isinstance(result, ToolResult)
        assert result.error is True
        # Event published even on the error path — important for
        # downstream audit/metrics observers.
        assert len(captured) == 1
        assert captured[0].payload["result"].error is True

    async def test_bus_post_failure_swallowed(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """A bus that raises on ``post`` must not break the tool
        call — the tool's text content still needs to reach the LLM
        even if the publish fails. Worst case, observers miss this
        invocation."""
        tm, _bus = tool_manager_with_bus
        tm.tools["test_image_tool"] = _ImageReturningTool()

        crashing_bus = MagicMock()
        crashing_bus.post.side_effect = RuntimeError("bus offline")
        tm._bus = crashing_bus  # noqa: SLF001

        # Must not raise.
        result = await tm.execute_tool("test_image_tool")
        assert isinstance(result, ToolResult)
        assert not result.error
        crashing_bus.post.assert_called_once()

    async def test_openai_tool_call_path_also_publishes(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """``execute_openai_tool_call`` delegates to ``execute_tool``
        internally, so the publish works through the LLM's calling path
        too. Regression guard in case someone later adds a parallel
        execute funnel that bypasses ``execute_tool``."""
        tm, bus = tool_manager_with_bus
        tm.tools["test_image_tool"] = _ImageReturningTool()

        captured: list[BusMessage] = []
        bus.subscribe("tool_completed", captured.append)

        fake_tool_call = MagicMock()
        fake_tool_call.function.name = "test_image_tool"
        fake_tool_call.function.arguments = "{}"

        await tm.execute_openai_tool_call(fake_tool_call)
        bus.poll()

        assert len(captured) == 1
        assert captured[0].payload["tool_name"] == "test_image_tool"
