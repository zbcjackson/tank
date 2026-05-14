"""Unit tests for Phase 16: ToolManager emits outbound images.

When a tool returns a :class:`ToolResult` whose content includes an
:class:`ImageBlock`,
:meth:`~tank_backend.tools.manager.ToolManager.execute_tool` posts an
``outbound_attachment`` bus event so the image reaches the user's
connector. These tests pin that contract without depending on a real
connector or the full pipeline — we subscribe to the bus directly and
check what got posted.
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
    """Minimal AppConfig stub so ``ToolManager`` can initialise.

    Mirrors the one in ``test_tool_groups.py``; repeating it here
    keeps this file self-contained without cross-test imports.
    """
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
    """Test tool that returns a ToolResult with an ImageBlock.

    Mirrors the shape real ``echo_image`` / future chart tools use —
    a TextBlock narrative followed by an ImageBlock. The ``display``
    becomes the caption on the outbound side.
    """

    def __init__(
        self,
        *,
        url: str = "https://example.com/cat.jpg",
        display: str = "A picture of a cat",
    ) -> None:
        self._url = url
        self._display = display

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
                ImageBlock(source=self._url, mime_type="image/jpeg"),
            ],
            display=self._display,
        )


class _TextOnlyTool(BaseTool):
    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="test_text_tool",
            description="Test-only tool that returns a text ToolResult.",
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


def _collect_outbound_attachments(bus: Bus) -> list[BusMessage]:
    captured: list[BusMessage] = []
    bus.subscribe("outbound_attachment", captured.append)
    # ``Bus.post`` is synchronous-dispatching in tank's implementation
    # (see tests elsewhere that poll()). Poll once so subscribers fire.
    bus.poll()
    return captured


@pytest.fixture()
def tool_manager_with_bus() -> tuple[ToolManager, Bus]:
    """ToolManager wired to a real Bus so outbound_attachment events
    can be observed by the test. Default tools are irrelevant here —
    tests register their own minimal tool into ``tm.tools``."""
    bus = Bus()
    tm = ToolManager(app_config=_make_app_config(), bus=bus)
    # Strip default tools so each test starts with a clean registry.
    tm.tools.clear()
    return tm, bus


class TestToolOutboundAttachments:
    async def test_image_block_emits_outbound_attachment(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """Happy path: a tool that returns ``[TextBlock, ImageBlock]``
        causes the manager to post an ``outbound_attachment`` event
        whose payload has the ImageBlock and the tool's ``display``
        as the caption."""
        tm, bus = tool_manager_with_bus
        tool = _ImageReturningTool(
            url="https://example.com/cat.jpg",
            display="A picture of a cat",
        )
        tm.tools[tool.get_info().name] = tool

        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        result = await tm.execute_tool("test_image_tool")
        bus.poll()

        # Tool result shape preserved (nothing was stripped from what
        # the LLM sees on the follow-up side).
        assert isinstance(result, ToolResult)
        assert not result.error

        # Exactly one outbound_attachment event with our image.
        assert len(captured) == 1
        payload = captured[0].payload
        blocks = payload["blocks"]
        assert len(blocks) == 1
        assert isinstance(blocks[0], ImageBlock)
        assert blocks[0].source == "https://example.com/cat.jpg"
        # Caption carries the tool's display string.
        assert payload["caption"] == "A picture of a cat"
        # source tag makes it easy to grep for tool-initiated attachments
        # in bus logs. Uses the tool name under a ``tool:`` prefix.
        assert captured[0].source == "tool:test_image_tool"

    async def test_text_only_tool_does_not_emit(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """Text-only ``ToolResult`` must not post an
        ``outbound_attachment`` — otherwise every tool call would
        wake the image dispatcher for nothing, wasting cycles and
        potentially posting empty attachment lists."""
        tm, bus = tool_manager_with_bus
        tm.tools["test_text_tool"] = _TextOnlyTool()

        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        await tm.execute_tool("test_text_tool")
        bus.poll()

        assert captured == []

    async def test_bus_none_is_safe_noop(self) -> None:
        """Some ToolManager construction paths pass ``bus=None``
        (narrow unit tests, offline tool execution). The emit hook
        must not crash in that case — the tool still returns normally,
        just without a published event."""
        tm = ToolManager(app_config=_make_app_config(), bus=None)
        tm.tools.clear()
        tm.tools["test_image_tool"] = _ImageReturningTool()

        # Must not raise.
        result = await tm.execute_tool("test_image_tool")
        assert isinstance(result, ToolResult)
        assert not result.error

    async def test_tool_error_short_circuits_emit(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """When the tool raises, ``execute_tool`` catches and returns
        an error-flagged ``ToolResult`` with a text message. The error
        ToolResult has no ImageBlocks, so no outbound_attachment —
        we don't want to flash an empty image to the user when the
        tool crashed."""
        tm, bus = tool_manager_with_bus
        tm.tools["test_raising_tool"] = _RaisingTool()

        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        result = await tm.execute_tool("test_raising_tool")
        bus.poll()

        assert isinstance(result, ToolResult)
        assert result.error is True
        assert captured == []

    async def test_bus_post_failure_swallowed(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """A bus that raises on ``post`` must not break the tool
        call — the tool's text content still needs to reach the LLM
        even if the image-emit fails. Worst case, the user just
        doesn't see the image on this turn."""
        tm, _bus = tool_manager_with_bus
        tm.tools["test_image_tool"] = _ImageReturningTool()

        # Swap in a bus whose ``.post`` always raises, so we can
        # confirm the tool result still comes back.
        crashing_bus = MagicMock()
        crashing_bus.post.side_effect = RuntimeError("bus offline")
        tm._bus = crashing_bus  # noqa: SLF001

        # Must not raise.
        result = await tm.execute_tool("test_image_tool")
        assert isinstance(result, ToolResult)
        assert not result.error
        # We did *try* to post — confirms we actually hit the emit path
        # rather than short-circuiting elsewhere.
        crashing_bus.post.assert_called_once()

    async def test_openai_tool_call_path_also_emits(
        self, tool_manager_with_bus: tuple[ToolManager, Bus],
    ) -> None:
        """``execute_openai_tool_call`` delegates to ``execute_tool``
        internally, so the emit works through the LLM's calling path
        too. Regression guard in case someone later adds a parallel
        execute funnel that bypasses ``execute_tool``."""
        tm, bus = tool_manager_with_bus
        tm.tools["test_image_tool"] = _ImageReturningTool()

        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        fake_tool_call = MagicMock()
        fake_tool_call.function.name = "test_image_tool"
        fake_tool_call.function.arguments = "{}"

        await tm.execute_openai_tool_call(fake_tool_call)
        bus.poll()

        assert len(captured) == 1
        assert isinstance(captured[0].payload["blocks"][0], ImageBlock)
