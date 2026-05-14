"""End-to-end test for Phase 16/17: tool-initiated images reach the user.

This test wires every real component on the path from a tool returning
an :class:`ImageBlock` to a connector's outbox:

    EchoImageTool → ToolManager.execute_tool
        → Bus.post("tool_completed")
        → ToolOutputObserver._on_tool_completed (Phase 17 refactor)
        → Bus.post("outbound_attachment")
        → _ImageDispatcher.on_event
        → FakeConnector.send(text=caption, attachments=[Attachment])

What's mocked:
- The LLM. Phase 16's E2E is not "ask the LLM to call echo_image and
  watch what happens" — that would test the LLM provider, not Tank.
  Instead we drive ``ToolManager.execute_tool`` directly with the
  arguments the LLM would have produced. The contract this test
  pins is "if a tool returns an ImageBlock, the user sees it."
- The actual platform SDK. ``FakeConnector`` stands in for Slack /
  Telegram / Discord; per-platform send paths are exercised in the
  plugin test suites.

What's real:
- ``EchoImageTool`` — the Phase 16 tool itself.
- ``ToolManager`` — funnels tool invocations and publishes a generic
  ``tool_completed`` event. After Phase 17 it doesn't know about
  ``ImageBlock``, attachments, or the UI.
- ``ToolOutputObserver`` — Phase 17 subscriber that turns
  ``tool_completed`` into ``outbound_attachment``. Where the
  content-kind awareness lives.
- ``Bus`` — actual pipeline message broker.
- ``_ImageDispatcher`` — connector-side subscriber that turns the
  ``outbound_attachment`` event into a ``connector.send`` call.
- The ``Attachment`` ↔ ``ImageBlock`` round-trip via
  ``_ImageDispatcher._resolve_image_attachment``.
"""

from __future__ import annotations

import asyncio
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
def wired_pipeline():
    """Real ToolManager + Bus + ToolOutputObserver + FakeConnector,
    paired with a helper that attaches a real :class:`_ImageDispatcher`
    once we're inside the test's event loop.

    Why the deferred attach: :class:`_ImageDispatcher` captures
    ``asyncio.get_running_loop()`` at construction time and routes its
    coroutine scheduling through :func:`asyncio.run_coroutine_threadsafe`
    on that captured loop. pytest-asyncio creates a fresh loop per
    test, so a dispatcher built in this sync fixture would target a
    loop that's already gone by the time the test calls the tool.
    Returning an ``attach_dispatcher`` callable lets each test do the
    construction after its own loop is live.

    Returns ``(tool_manager, bus, fake_connector, identity, attach_dispatcher)``.
    """
    bus = Bus()
    tm = ToolManager(app_config=_make_app_config(), bus=bus)
    fake = FakeConnector("e2e")

    # Phase 17 refactor: ToolManager publishes a generic
    # ``tool_completed`` event; ToolOutputObserver translates it into
    # ``outbound_attachment`` for the connector path. We instantiate
    # the observer here so the E2E covers the full chain (real
    # ToolManager → real bus event → real observer → real dispatcher
    # → fake connector).
    _observer = ToolOutputObserver(bus)

    identity = Identity(platform="fake", external_id="user-1")

    def attach_dispatcher() -> _ImageDispatcher:
        dispatcher = _ImageDispatcher(
            connector=fake, identity=identity, media_store=None,
        )
        bus.subscribe("outbound_attachment", dispatcher.on_event)
        return dispatcher

    return tm, bus, fake, identity, attach_dispatcher


async def _wait_for_send(
    fake: FakeConnector, bus: Bus, timeout_s: float = 1.0,
) -> None:
    """Spin briefly until the dispatcher's run_coroutine_threadsafe hop
    lands in the outbox.

    Two cooperating things happen between ``execute_tool`` returning and
    the connector's outbox getting a record:

    1. **Bus cascade** — Phase 17 introduced a two-hop chain
       (``tool_completed`` → ``ToolOutputObserver`` → ``outbound_attachment``).
       Each ``Bus.post`` queues into ``_pending``; only ``poll()``
       dispatches. So one ``poll()`` per hop. We drain the queue in a
       loop until empty.
    2. **Coroutine hop** — ``_ImageDispatcher.on_event`` schedules
       ``connector.send`` via ``run_coroutine_threadsafe``, so we yield
       to the loop a few times after each drain to let the task run.

    The combined wait covers both.
    """
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        # Drain until quiescent — any cascade-style chain is fully
        # dispatched once a poll returns 0.
        while bus.poll() > 0:
            pass
        if any(r.kind == "send" and r.attachments for r in fake.outbox):
            return
        await asyncio.sleep(0.01)


class TestEchoImageEndToEnd:
    async def test_echo_image_url_arrives_with_caption(
        self, wired_pipeline,
    ) -> None:
        """The headline scenario: an LLM (simulated by direct call here)
        invokes ``echo_image`` with a URL and a caption. The user's
        connector outbox ends up with one ``send`` record carrying the
        URL as an image attachment AND the caption as the message
        text. Validates the full Phase 16/17 path including the Phase
        15 caption hand-off."""
        tm, bus, fake, _identity, attach_dispatcher = wired_pipeline
        attach_dispatcher()

        result = await tm.execute_tool(
            "echo_image",
            url="https://example.com/cat.jpg",
            caption="Here's the cat you asked about:",
        )

        # Tool result itself remains the LLM's view of the call.
        assert not result.error
        await _wait_for_send(fake, bus)

        sends = [r for r in fake.outbox if r.kind == "send" and r.attachments]
        assert len(sends) == 1
        record = sends[0]

        # The image arrives as an Attachment with the URL as the data
        # payload (no MediaStore in this fixture, so no resolution).
        assert len(record.attachments) == 1
        att = record.attachments[0]
        assert att.kind == "image"
        assert att.data == "https://example.com/cat.jpg"
        assert att.mime_type == "image/jpeg"

        # The caption rides on the same send call so the user sees
        # "Here's the cat you asked about:" right next to the image,
        # not in a separate prior message. This is the Phase 15
        # caption-on-first-attachment guarantee, exercised end-to-end.
        assert record.text == "Here's the cat you asked about:"

    async def test_echo_image_without_caption_falls_back_to_default(
        self, wired_pipeline,
    ) -> None:
        """When the LLM omits ``caption``, the tool's ``display`` falls
        back to ``"Sent image"``. The user still sees a non-empty caption
        — better than a bare attachment with no context."""
        tm, bus, fake, _identity, attach_dispatcher = wired_pipeline
        attach_dispatcher()

        result = await tm.execute_tool(
            "echo_image", url="https://example.com/diagram.png",
        )
        assert not result.error
        await _wait_for_send(fake, bus)

        sends = [r for r in fake.outbox if r.kind == "send" and r.attachments]
        assert len(sends) == 1
        # Default display from EchoImageTool when caption is empty.
        assert sends[0].text == "Sent image"
        assert sends[0].attachments[0].mime_type == "image/png"

    async def test_invalid_scheme_returns_error_no_attachment_sent(
        self, wired_pipeline,
    ) -> None:
        """An LLM hallucinated ``echo_image(url="file:///etc/passwd")``
        must NOT exfiltrate or attempt to send. The tool returns an
        error result with no ImageBlock, so no outbound_attachment is
        published, so the connector outbox stays clean."""
        tm, bus, fake, _identity, attach_dispatcher = wired_pipeline
        attach_dispatcher()

        result = await tm.execute_tool(
            "echo_image", url="file:///etc/passwd",
        )
        assert result.error is True
        # Drain the cascade — observer should look at the error result
        # and skip emitting an outbound_attachment.
        while bus.poll() > 0:
            pass
        # Give the dispatcher loop the same time the happy-path test
        # gives it — if anything WAS going to come through, it would
        # have by now.
        await asyncio.sleep(0.05)

        sends_with_attachments = [
            r for r in fake.outbox if r.kind == "send" and r.attachments
        ]
        assert sends_with_attachments == []

    async def test_capability_gate_drops_image_on_text_only_connector(
        self,
    ) -> None:
        """When the receiving connector advertises
        ``supports_images_out=False``, the dispatcher logs and drops
        the image rather than forcing the connector to fail-and-fallback.
        Mirrors the existing TestOutboundImageDispatcher gate test, but
        from the tool-invocation entry point — confirms the gate is
        platform-agnostic regardless of which side originated the
        outbound."""
        from tank_backend.connectors.base import ConnectorCapabilities

        bus = Bus()
        tm = ToolManager(app_config=_make_app_config(), bus=bus)
        # Same observer wiring as the main fixture — real
        # tool_completed → outbound_attachment translation lives here.
        _observer = ToolOutputObserver(bus)

        text_only_caps = ConnectorCapabilities(
            supports_edits=True, supports_images_out=False,
        )
        fake = FakeConnector("text-only", capabilities=text_only_caps)

        dispatcher = _ImageDispatcher(
            connector=fake,
            identity=Identity(platform="fake", external_id="user-1"),
            media_store=None,
        )
        bus.subscribe("outbound_attachment", dispatcher.on_event)

        await tm.execute_tool(
            "echo_image", url="https://example.com/cat.jpg",
            caption="Should be dropped.",
        )
        # Drain the two-hop cascade.
        while bus.poll() > 0:
            pass
        await asyncio.sleep(0.05)

        # No send call landed at all — the dispatcher returned early on
        # the capability check.
        assert all(
            not (r.kind == "send" and r.attachments) for r in fake.outbox
        )
