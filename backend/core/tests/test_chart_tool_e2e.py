"""End-to-end test for Phase 18: ChartTool → connector outbox.

Validates the full Phase 18 path including the seams introduced this
phase:

    ToolContext seam (manager injects ctx)
        ChartTool.execute → matplotlib → MediaStore.put
        → media:// URI in ToolResult
        → ToolManager publishes ``tool_completed``
        → ToolOutputObserver translates → ``outbound_attachment``
        → _ImageDispatcher resolves media:// via MediaStore.get
        → FakeConnector.send(text=caption, attachments=[Attachment])

What's mocked:
- The LLM. We invoke ``ToolManager.execute_tool`` directly with the
  arguments the LLM would emit. The contract under test is "if a tool
  returns an ImageBlock with a media:// URI, the user sees the bytes."
- The actual platform SDK. ``FakeConnector`` stands in for Slack /
  Telegram / Discord / WebSocket; per-platform send paths are exercised
  in the plugin and WS-attachment test suites.

What's real:
- ``ChartTool`` — the Phase 18 tool itself, including matplotlib
  rendering and the actual PNG bytes.
- ``ToolManager`` — including the Phase 18 ``ToolContext`` injection.
- ``MediaStore`` — real filesystem persistence in a tempdir.
- ``Bus`` — actual pipeline message broker.
- ``ToolOutputObserver`` (Phase 17) and ``_ImageDispatcher`` (Phase 4).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
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
from tank_backend.connectors.base import Identity
from tank_backend.connectors.fake import FakeConnector
from tank_backend.connectors.manager import _ImageDispatcher
from tank_backend.connectors.tool_output_observer import ToolOutputObserver
from tank_backend.media.store import MediaStore
from tank_backend.pipeline.bus import Bus
from tank_backend.tools.manager import ToolManager


def _make_app_config() -> MagicMock:
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


@pytest.fixture()
def wired_chart_pipeline():
    """Real ToolManager + Bus + ToolOutputObserver + MediaStore + FakeConnector,
    paired with a deferred-attach helper for ``_ImageDispatcher`` so it's
    constructed inside the test's event loop (same caveat as
    ``test_echo_image_e2e.py``).

    Returns ``(tool_manager, bus, fake, identity, store, attach_dispatcher)``.
    """
    with tempfile.TemporaryDirectory() as tmp:
        bus = Bus()
        store = MediaStore(Path(tmp))
        tm = ToolManager(
            app_config=_make_app_config(),
            bus=bus,
            media_store=store,
        )
        tm.set_session_id("e2e-chart-session")

        ToolOutputObserver(bus)

        fake = FakeConnector("e2e-chart")
        identity = Identity(platform="fake", external_id="user-1")

        def attach_dispatcher() -> _ImageDispatcher:
            dispatcher = _ImageDispatcher(
                connector=fake,
                identity=identity,
                # Real MediaStore so the dispatcher can resolve the
                # ``media://`` URI to bytes — that's the point of this E2E.
                media_store=store,
            )
            bus.subscribe("outbound_attachment", dispatcher.on_event)
            return dispatcher

        yield tm, bus, fake, identity, store, attach_dispatcher


async def _drain_until_send(
    fake: FakeConnector, bus: Bus, timeout_s: float = 2.0,
) -> None:
    """Drain the bus + yield to the loop until the dispatcher's send
    coroutine completes. Same shape as the echo_image E2E helper —
    Phase 17's two-hop cascade plus the dispatcher's
    ``run_coroutine_threadsafe`` hop both need to settle."""
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        while bus.poll() > 0:
            pass
        if any(r.kind == "send" and r.attachments for r in fake.outbox):
            return
        await asyncio.sleep(0.01)


def _is_png(data: bytes) -> bool:
    return data.startswith(b"\x89PNG\r\n\x1a\n")


class TestChartE2E:
    async def test_bar_chart_arrives_with_png_bytes_and_caption(
        self, wired_chart_pipeline,
    ) -> None:
        """The headline scenario: an LLM (simulated by direct call here)
        invokes ``render_chart`` with bar data and a title. The user's
        connector outbox ends up with one ``send`` record carrying the
        rendered PNG bytes (resolved from MediaStore) AND the title as
        the caption.

        This validates every Phase 18 piece end-to-end:
        - ``ToolContext`` injection (chart tool reaches MediaStore)
        - matplotlib rendering produces real PNG bytes
        - MediaStore persistence produces a ``media://`` URI
        - ToolOutputObserver fires on tool_completed
        - ``_ImageDispatcher`` resolves media:// to bytes
        - Caption rides on the send call (Phase 15)
        """
        tm, bus, fake, _identity, _store, attach_dispatcher = wired_chart_pipeline
        attach_dispatcher()

        result = await tm.execute_tool(
            "render_chart",
            kind="bar",
            data=[
                {"label": "Q1", "value": 12000},
                {"label": "Q2", "value": 18500},
                {"label": "Q3", "value": 21000},
                {"label": "Q4", "value": 19500},
            ],
            title="2026 Revenue by Quarter",
            xlabel="Quarter",
            ylabel="Revenue ($)",
        )

        # Tool result itself stays clean — error=False, ImageBlock+TextBlock.
        assert not result.error
        await _drain_until_send(fake, bus)

        sends = [r for r in fake.outbox if r.kind == "send" and r.attachments]
        assert len(sends) == 1
        record = sends[0]

        # The image arrives as Attachment(kind=image) with REAL PNG bytes
        # — the dispatcher resolved the media:// URI through MediaStore.
        assert len(record.attachments) == 1
        att = record.attachments[0]
        assert att.kind == "image"
        assert att.mime_type == "image/png"
        # Bytes payload (not a string URL) — the resolution path went
        # through MediaStore.get rather than the http(s) pass-through.
        assert isinstance(att.data, bytes)
        assert _is_png(att.data)
        # Sanity: a real chart's PNG is at least a few KB.
        assert len(att.data) > 1024

        # Caption rides on the same send call — Phase 15's
        # caption-with-first-attachment guarantee, end to end.
        assert record.text == "2026 Revenue by Quarter"

    async def test_pie_chart_renders_and_arrives(
        self, wired_chart_pipeline,
    ) -> None:
        """Different kind, same path — confirms the dispatch + render
        is kind-agnostic."""
        tm, bus, fake, _identity, _store, attach_dispatcher = wired_chart_pipeline
        attach_dispatcher()

        result = await tm.execute_tool(
            "render_chart",
            kind="pie",
            data=[
                {"label": "Web", "value": 45},
                {"label": "Mobile", "value": 35},
                {"label": "Desktop", "value": 20},
            ],
            title="Traffic by platform",
        )
        assert not result.error
        await _drain_until_send(fake, bus)

        sends = [r for r in fake.outbox if r.kind == "send" and r.attachments]
        assert len(sends) == 1
        assert _is_png(sends[0].attachments[0].data)
        assert sends[0].text == "Traffic by platform"

    async def test_invalid_data_returns_error_no_outbound(
        self, wired_chart_pipeline,
    ) -> None:
        """Validation errors short-circuit before any image is rendered
        — no PNG produced, no MediaStore write, no outbound_attachment.
        Failure mode is "nothing in outbox", not "broken image
        attachment"."""
        tm, bus, fake, _identity, _store, attach_dispatcher = wired_chart_pipeline
        attach_dispatcher()

        result = await tm.execute_tool(
            "render_chart",
            kind="pie",
            # Negative value → pie chart validator rejects.
            data=[
                {"label": "A", "value": 5},
                {"label": "B", "value": -3},
            ],
        )
        assert result.error is True
        # Drain everything that might be queued.
        while bus.poll() > 0:
            pass
        await asyncio.sleep(0.05)

        sends_with_attachments = [
            r for r in fake.outbox if r.kind == "send" and r.attachments
        ]
        assert sends_with_attachments == []

    async def test_session_id_threading_picks_up_post_construction(
        self,
    ) -> None:
        """The chart tool needs ``ctx.session_id`` to address its
        MediaStore folder. Verify that ``ToolManager.set_session_id``
        called *after* construction takes effect — that's the path
        the assistant uses (``new_conversation`` /
        ``resume_conversation`` both update the session id post-init).
        """
        with tempfile.TemporaryDirectory() as tmp:
            bus = Bus()
            store = MediaStore(Path(tmp))
            tm = ToolManager(
                app_config=_make_app_config(),
                bus=bus,
                media_store=store,
            )

            # Don't set session yet — chart should fail.
            result_no_session = await tm.execute_tool(
                "render_chart",
                kind="bar",
                data=[{"label": "x", "value": 1}],
            )
            assert result_no_session.error is True
            assert "session" in result_no_session.content.lower()

            # Now set it; same call should succeed.
            tm.set_session_id("late-bound-session")
            result_with_session = await tm.execute_tool(
                "render_chart",
                kind="bar",
                data=[{"label": "x", "value": 1}],
            )
            assert not result_with_session.error
            # Image arrives in the right session-scoped folder.
            assert "media://late-bound-session/" in result_with_session.content[1].source
