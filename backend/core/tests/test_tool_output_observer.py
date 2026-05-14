"""Unit tests for Phase 17: ToolOutputObserver.

The observer subscribes to ``tool_completed`` events that
:meth:`ToolManager.execute_tool` publishes after every tool
invocation, and re-publishes any image content as an
``outbound_attachment`` event the existing dispatchers consume.

These tests pin the translation contract: when the observer fires,
what payload it produces, what failure modes it tolerates. The
upstream publish contract (when ``tool_completed`` is emitted) is
covered in ``test_tool_manager_publish.py``.

Architectural goal
------------------

Before Phase 17, all this logic lived in ``ToolManager`` itself —
that violated OCP because adding a new content kind (audio, doc)
meant editing ``ToolManager``. Splitting the observer out makes the
manager closed for modification and the system open for extension:
new content kinds add a new branch *here*; new behaviours (audit
logging, telemetry) add a new subscriber alongside this one.
"""

from __future__ import annotations

import pytest

from tank_backend.connectors.tool_output_observer import ToolOutputObserver
from tank_backend.core.content import DocumentBlock, ImageBlock, TextBlock
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.tools.base import ToolResult


@pytest.fixture()
def bus_with_observer() -> tuple[Bus, list[BusMessage]]:
    """A bus with the observer attached + a captured list of
    outbound_attachment events. Each test posts a ``tool_completed``
    message and ``poll()`` s to drain it; whatever the observer
    emits in response lands in ``captured``."""
    bus = Bus()
    ToolOutputObserver(bus)
    captured: list[BusMessage] = []
    bus.subscribe("outbound_attachment", captured.append)
    return bus, captured


def _post_tool_completed(
    bus: Bus, tool_name: str, result: ToolResult | str,
) -> None:
    """Emit a ``tool_completed`` payload in the same shape
    ``ToolManager._publish_tool_completed`` produces."""
    bus.post(
        BusMessage(
            type="tool_completed",
            source=f"tool:{tool_name}",
            payload={"tool_name": tool_name, "result": result},
        )
    )


class TestImageExtraction:
    def test_image_block_emits_outbound_attachment(
        self, bus_with_observer: tuple[Bus, list[BusMessage]],
    ) -> None:
        """Happy path: a ToolResult with an ImageBlock causes the
        observer to publish exactly one ``outbound_attachment`` event
        with the image and the tool's ``display`` as caption."""
        bus, captured = bus_with_observer
        result = ToolResult(
            content=[
                TextBlock(text="Here's the image:"),
                ImageBlock(
                    source="https://example.com/cat.jpg",
                    mime_type="image/jpeg",
                ),
            ],
            display="A picture of a cat",
        )
        _post_tool_completed(bus, "echo_image", result)
        # Two-hop cascade: the post enqueues the tool_completed message;
        # poll dispatches it to the observer, which itself calls post
        # for outbound_attachment. A second drain delivers the second
        # hop.
        while bus.poll() > 0:
            pass

        assert len(captured) == 1
        msg = captured[0]
        assert msg.type == "outbound_attachment"
        # source convention matches the pre-refactor publisher so any
        # bus-log greps keep working.
        assert msg.source == "tool:echo_image"
        payload = msg.payload
        assert payload["caption"] == "A picture of a cat"
        assert len(payload["blocks"]) == 1
        assert isinstance(payload["blocks"][0], ImageBlock)
        assert payload["blocks"][0].source == "https://example.com/cat.jpg"

    def test_text_only_result_does_not_emit(
        self, bus_with_observer: tuple[Bus, list[BusMessage]],
    ) -> None:
        """Text-only ``ToolResult`` must not wake the image dispatcher.
        Otherwise every tool call (calculator, time, weather…) would
        produce an empty attachment event."""
        bus, captured = bus_with_observer
        _post_tool_completed(
            bus, "calculator",
            ToolResult(content="42", display="42"),
        )
        while bus.poll() > 0:
            pass
        assert captured == []

    def test_string_result_skipped(
        self, bus_with_observer: tuple[Bus, list[BusMessage]],
    ) -> None:
        """Legacy tools sometimes return plain strings instead of
        ``ToolResult``. The observer is shape-aware: a string can't
        carry an ImageBlock, so it skips early."""
        bus, captured = bus_with_observer
        _post_tool_completed(bus, "legacy_tool", "plain string output")
        while bus.poll() > 0:
            pass
        assert captured == []

    def test_error_result_with_no_image_skipped(
        self, bus_with_observer: tuple[Bus, list[BusMessage]],
    ) -> None:
        """Error-flagged ToolResults rarely carry images; even when
        they do (defensive — a tool returning an error image), the
        observer treats them like any other ToolResult and looks at
        the blocks. An error result with text content only should not
        emit an outbound_attachment — text has no image to render."""
        bus, captured = bus_with_observer
        _post_tool_completed(
            bus, "failing_tool",
            ToolResult(content="something broke", display="error", error=True),
        )
        while bus.poll() > 0:
            pass
        assert captured == []


class TestMixedBlocks:
    def test_text_blocks_alongside_image_only_image_emitted(
        self, bus_with_observer: tuple[Bus, list[BusMessage]],
    ) -> None:
        """Tool results commonly carry a TextBlock describing the
        image, then the ImageBlock itself. The observer takes only the
        image — the surrounding text rides on the ``caption`` field
        (sourced from ``result.display``), not as a separate block in
        the outbound payload."""
        bus, captured = bus_with_observer
        result = ToolResult(
            content=[
                TextBlock(text="Here you go:"),
                ImageBlock(
                    source="https://example.com/x.png", mime_type="image/png",
                ),
                TextBlock(text="(generated 1ms ago)"),
            ],
            display="Result",
        )
        _post_tool_completed(bus, "test_tool", result)
        while bus.poll() > 0:
            pass

        assert len(captured) == 1
        assert len(captured[0].payload["blocks"]) == 1

    def test_document_blocks_skipped_today(
        self, bus_with_observer: tuple[Bus, list[BusMessage]],
    ) -> None:
        """Phase 17 only ships image extraction. Until a future
        ToolOutputObserver branch handles documents, they're dropped
        here. The test pins the current scope so a regression doesn't
        silently start emitting half-supported events."""
        bus, captured = bus_with_observer
        result = ToolResult(
            content=[
                DocumentBlock(
                    source="https://x/a.pdf",
                    mime_type="application/pdf",
                ),
                ImageBlock(
                    source="https://x/a.png", mime_type="image/png",
                ),
            ],
            display="doc + image",
        )
        _post_tool_completed(bus, "test_tool", result)
        while bus.poll() > 0:
            pass

        # Only the image survived.
        assert len(captured) == 1
        assert len(captured[0].payload["blocks"]) == 1
        assert isinstance(captured[0].payload["blocks"][0], ImageBlock)

    def test_multiple_images_all_emitted(
        self, bus_with_observer: tuple[Bus, list[BusMessage]],
    ) -> None:
        """All image blocks ride on a single outbound_attachment
        event so the connector dispatcher can apply caption-once
        across the batch (Phase 15 contract)."""
        bus, captured = bus_with_observer
        result = ToolResult(
            content=[
                ImageBlock(source="media://s1/a.jpg", mime_type="image/jpeg"),
                ImageBlock(source="media://s1/b.jpg", mime_type="image/jpeg"),
                ImageBlock(source="media://s1/c.jpg", mime_type="image/jpeg"),
            ],
            display="Three views",
        )
        _post_tool_completed(bus, "test_tool", result)
        while bus.poll() > 0:
            pass

        assert len(captured) == 1
        assert len(captured[0].payload["blocks"]) == 3


class TestCaptionHandling:
    def test_empty_display_becomes_none_caption(
        self, bus_with_observer: tuple[Bus, list[BusMessage]],
    ) -> None:
        """An empty ``display`` becomes ``None`` on the wire so the
        connector can decide whether to render a fallback or skip the
        caption entirely. The dispatcher already handles ``None``
        gracefully — see the Phase 15 caption tests."""
        bus, captured = bus_with_observer
        result = ToolResult(
            content=[
                ImageBlock(
                    source="https://example.com/x.jpg",
                    mime_type="image/jpeg",
                ),
            ],
            display="",  # explicitly empty
        )
        _post_tool_completed(bus, "test_tool", result)
        while bus.poll() > 0:
            pass

        assert captured[0].payload["caption"] is None

    def test_display_string_becomes_caption(
        self, bus_with_observer: tuple[Bus, list[BusMessage]],
    ) -> None:
        bus, captured = bus_with_observer
        result = ToolResult(
            content=[
                ImageBlock(source="https://x/y.png", mime_type="image/png"),
            ],
            display="Look at this:",
        )
        _post_tool_completed(bus, "test_tool", result)
        while bus.poll() > 0:
            pass
        assert captured[0].payload["caption"] == "Look at this:"


class TestFailureModes:
    def test_observer_post_failure_swallowed(self) -> None:
        """A bus that raises on the *outbound* post must not break the
        observer or the upstream tool — observers should never break
        the system they're observing. The test patches the bus's
        ``post`` after subscribing so the inbound dispatch still
        reaches the observer cleanly."""
        bus = Bus()
        ToolOutputObserver(bus)

        # Patch only the post used by the observer, not the one we use
        # to inject the tool_completed message.
        original_post = bus.post

        def crashing_post(message: BusMessage) -> None:
            if message.type == "outbound_attachment":
                raise RuntimeError("synthetic")
            return original_post(message)

        bus.post = crashing_post  # type: ignore[method-assign]

        result = ToolResult(
            content=[
                ImageBlock(source="https://x/y.png", mime_type="image/png"),
            ],
            display="x",
        )
        _post_tool_completed(bus, "test_tool", result)
        # The bus's poll catches the observer's exception and logs it;
        # we just need the drain to complete without raising.
        while bus.poll() > 0:
            pass

    def test_malformed_payload_is_safe_noop(self) -> None:
        """If a future bus message lacks the expected payload shape,
        the observer must not crash. Regression guard against a future
        producer that posts a different ``tool_completed`` schema."""
        bus = Bus()
        ToolOutputObserver(bus)
        captured: list[BusMessage] = []
        bus.subscribe("outbound_attachment", captured.append)

        bus.post(BusMessage(
            type="tool_completed",
            source="tool:weird",
            payload={},  # missing both ``tool_name`` and ``result``
        ))
        while bus.poll() > 0:
            pass

        # No outbound emitted; no exception raised.
        assert captured == []
