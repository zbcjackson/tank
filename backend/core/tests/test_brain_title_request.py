"""Tests for Brain._maybe_request_title — first-turn bus emission."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from brain_test_helpers import make_brain

from tank_backend.context.conversation import ConversationData
from tank_backend.pipeline.bus import Bus, BusMessage


def _conv(messages: list[dict], title: str | None = None) -> ConversationData:
    return ConversationData(
        id="conv-id",
        start_time=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
        pid=1,
        messages=messages,
        title=title,
    )


def _collect_title_events(bus: Bus) -> list[BusMessage]:
    captured: list[BusMessage] = []
    bus.subscribe("conversation_title_needed", captured.append)
    return captured


@pytest.fixture
def brain_with_bus():
    bus = Bus()
    brain = make_brain(bus=bus)
    return brain, bus


class TestMaybeRequestTitle:
    def test_first_assistant_turn_posts_event(self, brain_with_bus):
        brain, bus = brain_with_bus
        events = _collect_title_events(bus)
        brain._context = MagicMock()
        brain._context.conversation = _conv([
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "Plan a trip"},
            {"role": "assistant", "content": "Sure!"},
        ])

        brain._maybe_request_title()
        bus.poll()

        assert len(events) == 1
        assert events[0].payload["conversation_id"] == "conv-id"

    def test_skips_when_title_already_set(self, brain_with_bus):
        brain, bus = brain_with_bus
        events = _collect_title_events(bus)
        brain._context = MagicMock()
        brain._context.conversation = _conv(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            title="Existing",
        )

        brain._maybe_request_title()
        bus.poll()

        assert events == []

    def test_fires_for_continued_conversation_without_title(self, brain_with_bus):
        brain, bus = brain_with_bus
        events = _collect_title_events(bus)
        brain._context = MagicMock()
        brain._context.conversation = _conv([
            {"role": "system", "content": "x"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "ok"},
        ])

        brain._maybe_request_title()
        bus.poll()

        assert len(events) == 1
        assert events[0].payload["conversation_id"] == "conv-id"

    def test_fires_only_once_per_session(self, brain_with_bus):
        brain, bus = brain_with_bus
        events = _collect_title_events(bus)
        brain._context = MagicMock()
        brain._context.conversation = _conv([
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ])

        brain._maybe_request_title()
        brain._maybe_request_title()
        bus.poll()

        assert len(events) == 1

    def test_skips_when_no_assistant_reply_yet(self, brain_with_bus):
        brain, bus = brain_with_bus
        events = _collect_title_events(bus)
        brain._context = MagicMock()
        brain._context.conversation = _conv([
            {"role": "system", "content": "x"},
            {"role": "user", "content": "hello"},
        ])

        brain._maybe_request_title()
        bus.poll()

        assert events == []

    def test_skips_when_no_conversation(self, brain_with_bus):
        brain, bus = brain_with_bus
        events = _collect_title_events(bus)
        brain._context = MagicMock()
        brain._context.conversation = None

        brain._maybe_request_title()
        bus.poll()

        assert events == []
