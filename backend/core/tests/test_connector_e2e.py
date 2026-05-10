"""End-to-end test: inbound FakeConnector → Assistant → Bus → StreamConsumer → outbox.

Exercises the full Phase 2 dispatch path without network or LLM:
- FakeConnector.inject_inbound() simulates a platform message arriving.
- ConnectorManager routes it through SessionMapper → FakeConnectionManager →
  _FakeAssistant (which exposes a real Bus).
- We simulate a Brain streaming reply by posting ui_message events onto that Bus.
- The StreamConsumer the manager attached during inbound dispatch picks those
  up, calls FakeConnector.send() / .edit() based on the configured
  capabilities, and the result lands in FakeConnector.outbox.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tank_backend.channels.store import ChannelStore
from tank_backend.connectors.base import Attachment, ConnectorCapabilities, Identity
from tank_backend.connectors.fake import FakeConnector
from tank_backend.connectors.identity_store import ConnectorIdentityStore
from tank_backend.connectors.manager import ConnectorManager
from tank_backend.connectors.session_mapper import SessionMapper, derive_slug
from tank_backend.context.conversation import ConversationData
from tank_backend.context.store import ConversationStore
from tank_backend.core.events import DisplayMessage, UpdateType
from tank_backend.persistence import Base, Database
from tank_backend.pipeline.bus import Bus, BusMessage


class _MemoryConvStore(ConversationStore):
    def __init__(self) -> None:
        self._data: dict[str, ConversationData] = {}

    def save(self, conversation: ConversationData) -> None:
        self._data[conversation.id] = conversation

    def load(self, conversation_id: str) -> ConversationData | None:
        return self._data.get(conversation_id)

    def list_conversations(self):
        return []

    def delete(self, conversation_id: str) -> None:
        self._data.pop(conversation_id, None)

    def find_latest(self) -> ConversationData | None:
        return None


class _FakeAssistant:
    """Thin Assistant stand-in with a real :class:`Bus`."""

    def __init__(self) -> None:
        self._bus = Bus()
        self.inputs: list[dict] = []

    def process_input(self, text, user="Guest", *, attachments=None) -> None:
        self.inputs.append({"text": text, "user": user, "attachments": attachments})

    def emit_stream(self, msg_id: str, deltas: list[str]) -> None:
        """Simulate a Brain token stream. Posts each delta as an
        ``is_final=False`` ui_message, then a final ``is_final=True``
        message to close out.
        """
        for delta in deltas:
            self._bus.post(BusMessage(
                type="ui_message",
                source="brain",
                payload=DisplayMessage(
                    speaker="Brain",
                    text=delta,
                    is_user=False,
                    is_final=False,
                    msg_id=msg_id,
                    update_type=UpdateType.TEXT,
                ),
            ))
        self._bus.post(BusMessage(
            type="ui_message",
            source="brain",
            payload=DisplayMessage(
                speaker="Brain",
                text="",
                is_user=False,
                is_final=True,
                msg_id=msg_id,
                update_type=UpdateType.TEXT,
            ),
        ))
        self._bus.poll()


class _FakeConnectionManager:
    def __init__(self) -> None:
        self.assistants: dict[str, _FakeAssistant] = {}

    async def get_or_create_assistant(
        self,
        session_id: str,
        *,
        wants_audio_input: bool = True,
        wants_audio_output: bool = True,
    ) -> tuple[_FakeAssistant, bool]:
        if session_id in self.assistants:
            return self.assistants[session_id], False
        assistant = _FakeAssistant()
        self.assistants[session_id] = assistant
        return assistant, True


async def _wait_for_outbox(fake: FakeConnector, n: int, timeout: float = 1.0) -> None:
    """Drain the event loop until the outbox has at least ``n`` entries."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while len(fake.outbox) < n:
        if loop.time() > deadline:
            raise AssertionError(
                f"Timed out waiting for {n} outbox entries "
                f"(have {len(fake.outbox)}: {fake.outbox})"
            )
        await asyncio.sleep(0.01)


@pytest.fixture()
def e2e(tmp_path: Path):
    """Spin up the Phase 2 stack against an ephemeral SQLite DB."""
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)

    identity_store = ConnectorIdentityStore(db)
    channel_store = ChannelStore(db)
    conv_store = _MemoryConvStore()
    session_mapper = SessionMapper(identity_store, channel_store, conv_store)
    connection_manager = _FakeConnectionManager()
    manager = ConnectorManager(
        connection_manager=connection_manager,  # type: ignore[arg-type]
        session_mapper=session_mapper,
    )
    return manager, connection_manager, channel_store, identity_store


class TestPhase2E2E:
    """Full-stack: inbound message → dispatch → streaming reply → outbox."""

    async def test_inbound_creates_channel_and_identity(self, e2e) -> None:
        manager, _, channel_store, identity_store = e2e
        fake = FakeConnector("e2e")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(
            platform="fake", external_id="user-1", display_name="Alice",
        )
        await fake.inject_inbound(identity, text="hi")

        # Channel auto-created with the derived slug.
        slug = derive_slug(identity)
        channel = channel_store.get(slug)
        assert channel is not None
        assert channel.name == "Alice"

        # Identity mapped to that conversation.
        record = identity_store.get("fake", "user-1")
        assert record is not None
        assert record.session_id == channel.conversation_id

    async def test_streaming_reply_lands_in_outbox(self, e2e) -> None:
        manager, conn_mgr, _, _ = e2e
        fake = FakeConnector("e2e")  # supports_edits=True, no rate limit
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(identity, text="hello")

        # Assistant was created; the manager attached a StreamConsumer
        # to its Bus during the inbound dispatch.
        assistant = next(iter(conn_mgr.assistants.values()))

        # Simulate Brain streaming back three tokens.
        assistant.emit_stream("m1", ["Hel", "lo ", "world"])

        await _wait_for_outbox(fake, 1)
        # Give subsequent edits a moment to materialize.
        await asyncio.sleep(0.05)

        sends = fake.sends()
        edits = fake.edits()
        assert len(sends) == 1, f"expected 1 send, got {sends}"
        # Last emission should carry the complete concatenated text.
        last_text = (sends + edits)[-1].text
        assert last_text == "Hello world"

    async def test_same_identity_reuses_session_across_messages(
        self, e2e,
    ) -> None:
        manager, conn_mgr, _, _ = e2e
        fake = FakeConnector("e2e")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(identity, text="first")
        await fake.inject_inbound(identity, text="second")

        assert len(conn_mgr.assistants) == 1
        assistant = next(iter(conn_mgr.assistants.values()))
        assert [inp["text"] for inp in assistant.inputs] == ["first", "second"]

    async def test_different_identities_isolated(self, e2e) -> None:
        manager, conn_mgr, _, _ = e2e
        fake = FakeConnector("e2e")
        manager.register(fake)
        await manager.start_all()

        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-1"), text="a",
        )
        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-2"), text="b",
        )

        assert len(conn_mgr.assistants) == 2

    async def test_image_url_attachment_flows_to_assistant(self, e2e) -> None:
        manager, conn_mgr, _, _ = e2e
        fake = FakeConnector("e2e")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(
            identity,
            text="look at this",
            attachments=(Attachment(
                kind="image",
                data="https://example.com/cat.png",
                mime_type="image/png",
            ),),
        )

        assistant = next(iter(conn_mgr.assistants.values()))
        blocks = assistant.inputs[0]["attachments"]
        assert blocks is not None and len(blocks) == 1
        assert blocks[0].type == "image"
        assert blocks[0].source == "https://example.com/cat.png"

    async def test_final_only_transport_buffers_until_completion(
        self, e2e,
    ) -> None:
        """Platform without edit support (e.g. WeChat) sends once at end."""
        manager, conn_mgr, _, _ = e2e
        caps = ConnectorCapabilities(
            supports_edits=False, max_message_length=4000,
        )
        fake = FakeConnector("no-edits", capabilities=caps)
        manager.register(fake)
        await manager.start_all()

        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-1"), text="hi",
        )
        assistant = next(iter(conn_mgr.assistants.values()))
        assistant.emit_stream("m1", ["part1 ", "part2 ", "part3"])

        await _wait_for_outbox(fake, 1)
        await asyncio.sleep(0.05)

        # Exactly one send, no edits.
        assert len(fake.sends()) == 1
        assert fake.edits() == []
        assert fake.sends()[0].text == "part1 part2 part3"

    async def test_stop_all_is_idempotent_and_leaves_no_running_connectors(
        self, e2e,
    ) -> None:
        manager, _, _, _ = e2e
        fake = FakeConnector("e2e")
        manager.register(fake)
        await manager.start_all()
        assert fake.connected

        await manager.stop_all()
        assert not fake.connected

        await manager.stop_all()  # second call is safe
        assert not fake.connected

    async def test_stream_consumer_unsubscribed_survives_repeat_stream(
        self, e2e,
    ) -> None:
        """After two separate stream sessions, both reach the outbox."""
        manager, conn_mgr, _, _ = e2e
        fake = FakeConnector("e2e")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(identity, text="first")
        assistant = next(iter(conn_mgr.assistants.values()))
        assistant.emit_stream("m1", ["hello"])

        await _wait_for_outbox(fake, 1)
        await asyncio.sleep(0.05)

        # Second turn on the same session.
        await fake.inject_inbound(identity, text="second")
        assistant.emit_stream("m2", ["goodbye"])

        await _wait_for_outbox(fake, 2)
        await asyncio.sleep(0.05)

        # Both replies landed as sends.
        assert [s.text for s in fake.sends()] == ["hello", "goodbye"]
