"""Tests for ``TitleGenerationObserver`` — bus → generator → ui_message."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

from tank_backend.core.events import ConversationMetadataUpdate
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.observers.title_generation import TitleGenerationObserver


async def test_observer_runs_generator_and_emits_ui_message():
    bus = Bus()
    received: list[BusMessage] = []
    bus.subscribe("ui_message", received.append)

    generator = AsyncMock()
    generator.generate.return_value = "Generated title"

    loop = asyncio.get_running_loop()
    observer = TitleGenerationObserver(bus=bus, generator=generator)
    observer.set_loop(loop)

    bus.post(BusMessage(
        type="conversation_title_needed",
        source="brain",
        payload={"conversation_id": "abc"},
        timestamp=time.time(),
    ))
    bus.poll()

    # Let the scheduled coroutine finish.
    for _ in range(20):
        await asyncio.sleep(0.01)
        if received:
            break

    bus.poll()

    generator.generate.assert_awaited_once_with("abc")
    assert len(received) == 1
    payload = received[0].payload
    assert isinstance(payload, ConversationMetadataUpdate)
    assert payload.conversation_id == "abc"
    assert payload.title == "Generated title"


async def test_observer_skips_when_generator_returns_none():
    bus = Bus()
    received: list[BusMessage] = []
    bus.subscribe("ui_message", received.append)

    generator = AsyncMock()
    generator.generate.return_value = None

    observer = TitleGenerationObserver(bus=bus, generator=generator)
    observer.set_loop(asyncio.get_running_loop())

    bus.post(BusMessage(
        type="conversation_title_needed",
        source="brain",
        payload={"conversation_id": "abc"},
        timestamp=time.time(),
    ))
    bus.poll()
    for _ in range(20):
        await asyncio.sleep(0.01)
    bus.poll()

    generator.generate.assert_awaited_once_with("abc")
    assert received == []


async def test_observer_ignores_message_with_missing_conversation_id():
    bus = Bus()
    generator = AsyncMock()

    observer = TitleGenerationObserver(bus=bus, generator=generator)
    observer.set_loop(asyncio.get_running_loop())

    bus.post(BusMessage(
        type="conversation_title_needed",
        source="brain",
        payload={},
        timestamp=time.time(),
    ))
    bus.poll()
    await asyncio.sleep(0.02)

    generator.generate.assert_not_called()


async def test_observer_no_op_without_loop():
    bus = Bus()
    generator = AsyncMock()
    TitleGenerationObserver(bus=bus, generator=generator)  # no set_loop()

    bus.post(BusMessage(
        type="conversation_title_needed",
        source="brain",
        payload={"conversation_id": "abc"},
        timestamp=time.time(),
    ))
    bus.poll()
    await asyncio.sleep(0.02)

    generator.generate.assert_not_called()
