"""Tests for markdown image extraction from LLM output.

When the LLM includes ``![alt](https://example.com/image.png)`` in its
streamed text, Brain's ``_extract_and_emit_markdown_images`` strips the
markdown syntax and emits an ``outbound_attachment`` bus event so
connectors render the image inline.

These tests exercise the extraction + emission logic in isolation
(calling the method directly on a Brain instance with a real Bus)
rather than driving a full LLM turn — keeps them fast and focused on
the regex + bus-post contract.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from brain_test_helpers import make_brain

from tank_backend.core.content import ImageBlock
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.processors.brain import BrainConfig


def _make_brain_with_bus():
    """Create a Brain with a real Bus so we can observe outbound events."""
    bus = Bus()
    tool_manager = MagicMock()
    tool_manager.get_openai_tools.return_value = []
    tool_manager.approval_policy = MagicMock()
    config = BrainConfig(max_history_tokens=8000)
    interrupt_event = threading.Event()

    brain = make_brain(
        llm=MagicMock(),
        tool_manager=tool_manager,
        config=config,
        bus=bus,
        interrupt_event=interrupt_event,
        tts_enabled=False,
    )
    return brain, bus


class TestMarkdownImageExtraction:
    def test_no_images_returns_text_unchanged(self) -> None:
        """Text without markdown image links passes through untouched."""
        brain, bus = _make_brain_with_bus()
        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        result = brain._extract_and_emit_markdown_images(
            "Hello, here's some plain text.", "msg-1",
        )
        bus.poll()

        assert result == "Hello, here's some plain text."
        assert captured == []

    def test_single_image_extracted_and_emitted(self) -> None:
        """A single ![alt](url) is stripped from text and emitted as
        an outbound_attachment with the URL as ImageBlock source."""
        brain, bus = _make_brain_with_bus()
        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        text = "Here's the chart: ![Q1 Revenue](https://example.com/chart.png)"
        result = brain._extract_and_emit_markdown_images(text, "msg-1")
        bus.poll()

        # Text cleaned: markdown syntax replaced with alt text
        assert result == "Here's the chart: Q1 Revenue"
        assert "![" not in result
        assert "https://example.com/chart.png" not in result

        # One outbound_attachment emitted
        assert len(captured) == 1
        payload = captured[0].payload
        assert payload["caption"] == "Q1 Revenue"
        assert len(payload["blocks"]) == 1
        assert isinstance(payload["blocks"][0], ImageBlock)
        assert payload["blocks"][0].source == "https://example.com/chart.png"

    def test_multiple_images_each_emitted_separately(self) -> None:
        """Multiple markdown images in one response each get their own
        outbound_attachment event — the dispatcher applies caption-once
        per the Phase 15 contract."""
        brain, bus = _make_brain_with_bus()
        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        text = (
            "Two views:\n"
            "![Front](https://example.com/front.jpg)\n"
            "![Back](https://example.com/back.jpg)"
        )
        result = brain._extract_and_emit_markdown_images(text, "msg-1")
        bus.poll()

        assert result == "Two views:\nFront\nBack"
        assert len(captured) == 2
        assert captured[0].payload["blocks"][0].source == "https://example.com/front.jpg"
        assert captured[1].payload["blocks"][0].source == "https://example.com/back.jpg"
        assert captured[0].payload["caption"] == "Front"
        assert captured[1].payload["caption"] == "Back"

    def test_empty_alt_text_uses_none_caption(self) -> None:
        """![](url) with empty alt text emits caption=None so the
        connector doesn't render an empty string above the image."""
        brain, bus = _make_brain_with_bus()
        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        text = "Look: ![](https://example.com/x.png)"
        result = brain._extract_and_emit_markdown_images(text, "msg-1")
        bus.poll()

        assert result == "Look: "
        assert captured[0].payload["caption"] is None

    def test_only_http_urls_matched(self) -> None:
        """Non-http(s) URLs in markdown image syntax are NOT extracted.
        This prevents accidental extraction of file:// paths or
        media:// URIs that the LLM might hallucinate."""
        brain, bus = _make_brain_with_bus()
        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        text = "![local](file:///etc/passwd) ![media](media://s/x.png)"
        result = brain._extract_and_emit_markdown_images(text, "msg-1")
        bus.poll()

        # Neither matched — text unchanged, no events
        assert result == text
        assert captured == []

    def test_regular_markdown_links_not_matched(self) -> None:
        """Regular markdown links [text](url) (without the leading !)
        are NOT images and must not be extracted."""
        brain, bus = _make_brain_with_bus()
        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        text = "See [the docs](https://example.com/docs) for details."
        result = brain._extract_and_emit_markdown_images(text, "msg-1")
        bus.poll()

        assert result == text
        assert captured == []

    def test_bus_post_failure_does_not_crash(self) -> None:
        """If the bus raises on post, the extraction still returns
        cleaned text — the image just doesn't render on the user's
        side. Better than crashing the whole turn."""
        brain, bus = _make_brain_with_bus()

        # Patch bus.post to raise
        original_post = bus.post
        def crashing_post(msg: BusMessage) -> None:
            if msg.type == "outbound_attachment":
                raise RuntimeError("bus offline")
            return original_post(msg)
        bus.post = crashing_post  # type: ignore[method-assign]

        text = "![x](https://example.com/x.png)"
        # Must not raise
        result = brain._extract_and_emit_markdown_images(text, "msg-1")

        # Text still cleaned even though the emit failed
        assert result == "x"

    def test_msg_id_forwarded_in_payload(self) -> None:
        """The msg_id from the turn is forwarded so the frontend can
        group the image with the surrounding text in the same
        conversation turn."""
        brain, bus = _make_brain_with_bus()
        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        brain._extract_and_emit_markdown_images(
            "![cat](https://x/cat.jpg)", "msg-42",
        )
        bus.poll()

        assert captured[0].payload["msg_id"] == "msg-42"
