"""Unit tests for :class:`StreamConsumer` — edit transport and final-only."""

from __future__ import annotations

import asyncio

from tank_backend.connectors.base import ConnectorCapabilities, Identity
from tank_backend.connectors.fake import FakeConnector
from tank_backend.connectors.stream_consumer import StreamConsumer
from tank_backend.core.events import DisplayMessage, UpdateType
from tank_backend.pipeline.bus import BusMessage


def _make_token(msg_id: str, text: str, is_final: bool = False) -> BusMessage:
    return BusMessage(
        type="ui_message",
        source="brain",
        payload=DisplayMessage(
            speaker="Brain",
            text=text,
            is_user=False,
            is_final=is_final,
            msg_id=msg_id,
            update_type=UpdateType.TEXT,
        ),
    )


async def _wait_for_outbox(fake: FakeConnector, n: int, timeout: float = 1.0) -> None:
    """Drain the event loop until the outbox has at least ``n`` entries."""
    deadline = asyncio.get_event_loop().time() + timeout
    while len(fake.outbox) < n:
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(
                f"Timed out waiting for {n} outbox entries "
                f"(have {len(fake.outbox)}: {fake.outbox})"
            )
        await asyncio.sleep(0.01)


class TestEditTransport:
    async def test_first_token_triggers_send(self) -> None:
        fake = FakeConnector()  # supports_edits=True, edit_min_interval_ms=0
        identity = Identity(platform="fake", external_id="user-1")
        consumer = StreamConsumer(fake, identity, loop=asyncio.get_running_loop())

        consumer.on_ui_message(_make_token("m1", "Hello"))
        await _wait_for_outbox(fake, 1)

        sends = fake.sends()
        assert len(sends) == 1
        assert sends[0].text == "Hello"

    async def test_multiple_tokens_produce_edits(self) -> None:
        fake = FakeConnector()
        identity = Identity(platform="fake", external_id="user-1")
        consumer = StreamConsumer(fake, identity, loop=asyncio.get_running_loop())

        consumer.on_ui_message(_make_token("m1", "Hello"))
        await _wait_for_outbox(fake, 1)

        consumer.on_ui_message(_make_token("m1", " world"))
        await _wait_for_outbox(fake, 2)

        consumer.on_ui_message(_make_token("m1", "", is_final=True))
        # final may or may not trigger another edit depending on whether the
        # buffer changed; the important thing is the last-sent text matches.
        await asyncio.sleep(0.05)

        sends = fake.sends()
        edits = fake.edits()
        assert len(sends) == 1
        assert len(edits) >= 1
        last_text = (sends + edits)[-1].text
        assert last_text == "Hello world"

    async def test_user_messages_are_ignored(self) -> None:
        fake = FakeConnector()
        identity = Identity(platform="fake", external_id="user-1")
        consumer = StreamConsumer(fake, identity, loop=asyncio.get_running_loop())

        user_msg = BusMessage(
            type="ui_message",
            source="keyboard",
            payload=DisplayMessage(
                speaker="User", text="hi", is_user=True, is_final=True, msg_id="u1",
            ),
        )
        consumer.on_ui_message(user_msg)
        await asyncio.sleep(0.05)

        assert fake.outbox == []

    async def test_non_text_update_types_ignored(self) -> None:
        fake = FakeConnector()
        identity = Identity(platform="fake", external_id="user-1")
        consumer = StreamConsumer(fake, identity, loop=asyncio.get_running_loop())

        thought_msg = BusMessage(
            type="ui_message",
            source="brain",
            payload=DisplayMessage(
                speaker="Brain", text="thinking...", is_user=False,
                is_final=False, msg_id="t1", update_type=UpdateType.THOUGHT,
            ),
        )
        consumer.on_ui_message(thought_msg)
        await asyncio.sleep(0.05)

        assert fake.outbox == []

    async def test_truncates_to_max_message_length(self) -> None:
        caps = ConnectorCapabilities(
            supports_edits=True, edit_min_interval_ms=0, max_message_length=10,
        )
        fake = FakeConnector(capabilities=caps)
        identity = Identity(platform="fake", external_id="user-1")
        consumer = StreamConsumer(fake, identity, loop=asyncio.get_running_loop())

        consumer.on_ui_message(_make_token("m1", "x" * 100, is_final=True))
        await _wait_for_outbox(fake, 1)

        assert len(fake.sends()[0].text) == 10

    async def test_send_failure_logged_not_raised(self) -> None:
        fake = FakeConnector(fail_send=True)
        identity = Identity(platform="fake", external_id="user-1")
        consumer = StreamConsumer(fake, identity, loop=asyncio.get_running_loop())

        consumer.on_ui_message(_make_token("m1", "Hello", is_final=True))
        await asyncio.sleep(0.05)

        # Nothing in outbox because send failed.
        assert fake.sends() == []


class TestFinalOnlyTransport:
    async def test_no_send_during_streaming(self) -> None:
        caps = ConnectorCapabilities(supports_edits=False, max_message_length=4000)
        fake = FakeConnector(capabilities=caps)
        identity = Identity(platform="fake", external_id="user-1")
        consumer = StreamConsumer(fake, identity, loop=asyncio.get_running_loop())

        consumer.on_ui_message(_make_token("m1", "partial"))
        await asyncio.sleep(0.05)

        assert fake.outbox == []

    async def test_single_send_on_completion(self) -> None:
        caps = ConnectorCapabilities(supports_edits=False, max_message_length=4000)
        fake = FakeConnector(capabilities=caps)
        identity = Identity(platform="fake", external_id="user-1")
        consumer = StreamConsumer(fake, identity, loop=asyncio.get_running_loop())

        consumer.on_ui_message(_make_token("m1", "Hello"))
        consumer.on_ui_message(_make_token("m1", " world"))
        consumer.on_ui_message(_make_token("m1", "", is_final=True))
        await _wait_for_outbox(fake, 1)
        await asyncio.sleep(0.05)

        assert len(fake.sends()) == 1
        assert fake.sends()[0].text == "Hello world"
        assert fake.edits() == []

    async def test_empty_reply_sends_nothing(self) -> None:
        caps = ConnectorCapabilities(supports_edits=False, max_message_length=4000)
        fake = FakeConnector(capabilities=caps)
        identity = Identity(platform="fake", external_id="user-1")
        consumer = StreamConsumer(fake, identity, loop=asyncio.get_running_loop())

        consumer.on_ui_message(_make_token("m1", "", is_final=True))
        await asyncio.sleep(0.05)

        assert fake.outbox == []
