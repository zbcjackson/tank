"""Unit tests for :class:`ConnectorManager` dispatch + registration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tank_backend.channels.store import ChannelStore
from tank_backend.connectors.base import Attachment, Identity
from tank_backend.connectors.exceptions import DuplicateConnectorError
from tank_backend.connectors.fake import FakeConnector
from tank_backend.connectors.identity_store import ConnectorIdentityStore
from tank_backend.connectors.manager import ConnectorManager
from tank_backend.connectors.session_mapper import SessionMapper
from tank_backend.context.conversation import ConversationData
from tank_backend.context.store import ConversationStore
from tank_backend.persistence import Base, Database


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
    """Stand-in for Assistant — records process_input calls, exposes a bus."""

    def __init__(self) -> None:
        from tank_backend.pipeline.bus import Bus
        self._bus = Bus()
        self.inputs: list[dict] = []

    def process_input(self, text, user="Guest", *, attachments=None) -> None:
        self.inputs.append({"text": text, "user": user, "attachments": attachments})


class _FakeConnectionManager:
    """Stand-in for ConnectionManager that hands out _FakeAssistant instances."""

    def __init__(self) -> None:
        self.assistants: dict[str, _FakeAssistant] = {}
        self.modality_calls: list[tuple[bool, bool]] = []

    async def get_or_create_assistant(
        self,
        session_id: str,
        *,
        wants_audio_input: bool = True,
        wants_audio_output: bool = True,
    ) -> tuple[_FakeAssistant, bool]:
        self.modality_calls.append((wants_audio_input, wants_audio_output))
        if session_id in self.assistants:
            return self.assistants[session_id], False
        assistant = _FakeAssistant()
        self.assistants[session_id] = assistant
        return assistant, True


@pytest.fixture()
def manager(tmp_path: Path) -> ConnectorManager:
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    identity_store = ConnectorIdentityStore(db)
    channel_store = ChannelStore(db)
    conv_store = _MemoryConvStore()
    session_mapper = SessionMapper(identity_store, channel_store, conv_store)
    connection_manager = _FakeConnectionManager()
    # AppContext with neither MediaStore nor capabilities — matches a
    # minimal dev config. Individual tests override via
    # ``_with_app_context`` when they need image plumbing.
    app_context = MagicMock(name="AppContext")
    app_context.media_store = None
    app_context.llm_capabilities = None
    return ConnectorManager(
        connection_manager=connection_manager,  # type: ignore[arg-type]
        session_mapper=session_mapper,
        app_context=app_context,
    )


class TestRegistration:
    def test_register_installs_message_handler(
        self, manager: ConnectorManager,
    ) -> None:
        fake = FakeConnector("my-fake")
        assert fake._on_message is None  # noqa: SLF001
        manager.register(fake)
        assert fake._on_message is not None  # noqa: SLF001

    def test_register_is_discoverable_by_name(
        self, manager: ConnectorManager,
    ) -> None:
        fake = FakeConnector("my-fake")
        manager.register(fake)
        assert manager.get("my-fake") is fake
        assert list(manager.iter_connectors()) == [fake]

    def test_duplicate_instance_name_rejected(
        self, manager: ConnectorManager,
    ) -> None:
        manager.register(FakeConnector("dup"))
        with pytest.raises(DuplicateConnectorError):
            manager.register(FakeConnector("dup"))


class TestLifecycle:
    async def test_start_all_and_stop_all(
        self, manager: ConnectorManager,
    ) -> None:
        fake_a = FakeConnector("a")
        fake_b = FakeConnector("b")
        manager.register(fake_a)
        manager.register(fake_b)

        await manager.start_all()
        assert fake_a.connected
        assert fake_b.connected

        await manager.stop_all()
        assert not fake_a.connected
        assert not fake_b.connected

    async def test_start_failure_does_not_abort_others(
        self, manager: ConnectorManager,
    ) -> None:
        failing = FakeConnector("bad")

        async def _fail_start() -> None:
            raise RuntimeError("synthetic")

        failing.start = _fail_start  # type: ignore[assignment, method-assign]
        healthy = FakeConnector("good")
        manager.register(failing)
        manager.register(healthy)

        await manager.start_all()

        # Healthy connector still started.
        assert healthy.connected


class TestInboundDispatch:
    async def test_inbound_requests_text_only_session(
        self, manager: ConnectorManager,
    ) -> None:
        """Connector dispatch must ask ConnectionManager for a text-only
        Assistant so the audio pipeline never runs on these sessions
        (no VAD/ASR on silence, no TTS chunks dropped by Playback)."""
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-1"), text="hello",
        )

        cm = manager._conn_mgr  # noqa: SLF001
        assert cm.modality_calls == [(False, False)]

    async def test_text_message_reaches_assistant(
        self, manager: ConnectorManager,
    ) -> None:
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(
            platform="fake", external_id="user-1", display_name="Alice",
        )
        await fake.inject_inbound(identity, text="hello tank")

        # The fake connection manager created an Assistant for this session.
        cm = manager._conn_mgr  # noqa: SLF001
        assert len(cm.assistants) == 1
        assistant = next(iter(cm.assistants.values()))
        assert len(assistant.inputs) == 1
        assert assistant.inputs[0]["text"] == "hello tank"
        assert assistant.inputs[0]["user"] == "Alice"
        assert assistant.inputs[0]["attachments"] is None

    async def test_same_identity_reuses_assistant(
        self, manager: ConnectorManager,
    ) -> None:
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(identity, text="first")
        await fake.inject_inbound(identity, text="second")

        cm = manager._conn_mgr  # noqa: SLF001
        assert len(cm.assistants) == 1
        assistant = next(iter(cm.assistants.values()))
        assert [inp["text"] for inp in assistant.inputs] == ["first", "second"]

    async def test_different_identities_get_different_assistants(
        self, manager: ConnectorManager,
    ) -> None:
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-1"), text="a",
        )
        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-2"), text="b",
        )

        cm = manager._conn_mgr  # noqa: SLF001
        assert len(cm.assistants) == 2

    async def test_image_url_attachment_becomes_content_block(
        self, manager: ConnectorManager,
    ) -> None:
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(
            identity,
            text="look at this",
            attachments=(
                Attachment(kind="image", data="https://example.com/x.png", mime_type="image/png"),
            ),
        )

        assistant = next(iter(manager._conn_mgr.assistants.values()))  # noqa: SLF001
        blocks = assistant.inputs[0]["attachments"]
        assert blocks is not None
        assert len(blocks) == 1
        assert blocks[0].type == "image"
        assert blocks[0].source == "https://example.com/x.png"

    async def test_unsupported_attachment_dropped(
        self, manager: ConnectorManager,
    ) -> None:
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(
            identity,
            text="voice memo",
            attachments=(
                Attachment(kind="audio", data=b"\x00\x01", mime_type="audio/ogg"),
            ),
        )

        assistant = next(iter(manager._conn_mgr.assistants.values()))  # noqa: SLF001
        # Audio is not yet supported end-to-end in Phase 2 — dropped silently.
        assert assistant.inputs[0]["attachments"] is None

    async def test_session_mapper_failure_does_not_raise(
        self, manager: ConnectorManager,
    ) -> None:
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        # Poison the mapper to force failure
        manager._session_mapper = MagicMock()  # noqa: SLF001
        manager._session_mapper.resolve = MagicMock(  # noqa: SLF001
            side_effect=RuntimeError("synthetic")
        )

        # Must not propagate — framework swallows and logs.
        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-1"), text="hi",
        )


# ── Image plumbing (Phase 4) ───────────────────────────────────────────


class _FakeMediaStore:
    """In-memory stand-in for :class:`MediaStore` — records puts, replays
    bytes on get. Mirrors the real ``async`` API."""

    def __init__(self, *, fail_put: bool = False) -> None:
        self._store: dict[str, tuple[bytes, str]] = {}
        self._fail_put = fail_put
        self.puts: list[tuple[int, str, str]] = []  # (size, mime, session_id)

    async def put(
        self, data: bytes, mime_type: str, *, session_id: str,
    ):
        if self._fail_put:
            raise RuntimeError("synthetic store failure")
        self.puts.append((len(data), mime_type, session_id))
        uri = f"media://{session_id}/{hash(data) & 0xFFFF:04x}.bin"
        self._store[uri] = (data, mime_type)

        class _Stored:
            def __init__(self, uri, mime, size):
                self.media_uri = uri
                self.mime_type = mime
                self.size = size

        return _Stored(uri, mime_type, len(data))

    async def get(self, media_uri: str, *, session_id: str | None = None):
        return self._store[media_uri]


def _manager_with_media(tmp_path: Path, *, supports_image: bool,
                        media_store: _FakeMediaStore | None = None) -> ConnectorManager:
    """Build a ConnectorManager wired to a fake MediaStore + capabilities."""
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    identity_store = ConnectorIdentityStore(db)
    channel_store = ChannelStore(db)
    conv_store = _MemoryConvStore()
    session_mapper = SessionMapper(identity_store, channel_store, conv_store)
    connection_manager = _FakeConnectionManager()

    caps = MagicMock(name="ModelCapabilities")
    caps.input_modalities = frozenset(
        {"text", "image"} if supports_image else {"text"},
    )
    app_context = MagicMock(name="AppContext")
    app_context.media_store = media_store or _FakeMediaStore()
    app_context.llm_capabilities = caps

    return ConnectorManager(
        connection_manager=connection_manager,  # type: ignore[arg-type]
        session_mapper=session_mapper,
        app_context=app_context,
    )


class TestInboundImages:
    async def test_bytes_image_stored_in_media_store_and_becomes_media_uri(
        self, tmp_path: Path,
    ) -> None:
        media = _FakeMediaStore()
        manager = _manager_with_media(
            tmp_path, supports_image=True, media_store=media,
        )
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(
            identity,
            text="what is this?",
            attachments=(
                Attachment(kind="image", data=b"\xff\xd8\xff" + b"\x00" * 100,
                           mime_type="image/jpeg"),
            ),
        )

        assert len(media.puts) == 1
        size, mime, session_id = media.puts[0]
        assert mime == "image/jpeg"
        assert size == 103
        assert session_id  # non-empty

        assistant = next(iter(manager._conn_mgr.assistants.values()))  # noqa: SLF001
        blocks = assistant.inputs[0]["attachments"]
        assert blocks is not None
        assert len(blocks) == 1
        assert blocks[0].type == "image"
        assert blocks[0].source.startswith("media://")
        assert blocks[0].mime_type == "image/jpeg"
        # The caption is the text on the MessageEvent
        assert assistant.inputs[0]["text"] == "what is this?"

    async def test_url_image_bypasses_media_store(
        self, tmp_path: Path,
    ) -> None:
        media = _FakeMediaStore()
        manager = _manager_with_media(
            tmp_path, supports_image=True, media_store=media,
        )
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-1"),
            attachments=(
                Attachment(kind="image", data="https://example.com/x.png",
                           mime_type="image/png"),
            ),
        )

        # URL path — no MediaStore interaction expected.
        assert media.puts == []
        assistant = next(iter(manager._conn_mgr.assistants.values()))  # noqa: SLF001
        blocks = assistant.inputs[0]["attachments"]
        assert blocks[0].source == "https://example.com/x.png"

    async def test_text_only_llm_rejects_image_with_polite_reply(
        self, tmp_path: Path,
    ) -> None:
        media = _FakeMediaStore()
        manager = _manager_with_media(
            tmp_path, supports_image=False, media_store=media,
        )
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-1"),
            text="",
            attachments=(
                Attachment(kind="image", data=b"\xff\xd8\xff",
                           mime_type="image/jpeg"),
            ),
        )

        # Polite reply was sent through the connector.
        sends = fake.sends()
        assert len(sends) == 1
        assert "not images" in sends[0].text.lower() or \
               "text only" in sends[0].text.lower() or \
               "text but not" in sends[0].text.lower()

        # Nothing reached MediaStore; no ImageBlock passed to Assistant.
        assert media.puts == []
        assistant = next(iter(manager._conn_mgr.assistants.values()))  # noqa: SLF001
        # text="" — the no-op Attachment path produced no blocks;
        # process_input was still called so the text (empty) flows.
        assert assistant.inputs[0]["attachments"] is None

    async def test_oversize_image_rejected_with_reply(
        self, tmp_path: Path,
    ) -> None:
        media = _FakeMediaStore()
        manager = _manager_with_media(
            tmp_path, supports_image=True, media_store=media,
        )
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        # 26 MB — just above the 25 MB cap.
        oversized = b"\x00" * (26 * 1024 * 1024)
        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-1"),
            attachments=(
                Attachment(kind="image", data=oversized, mime_type="image/jpeg"),
            ),
        )

        sends = fake.sends()
        assert len(sends) == 1
        assert "too large" in sends[0].text.lower()
        assert media.puts == []

    async def test_media_store_failure_replies_with_error(
        self, tmp_path: Path,
    ) -> None:
        media = _FakeMediaStore(fail_put=True)
        manager = _manager_with_media(
            tmp_path, supports_image=True, media_store=media,
        )
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        await fake.inject_inbound(
            Identity(platform="fake", external_id="user-1"),
            attachments=(
                Attachment(kind="image", data=b"\xff\xd8\xff",
                           mime_type="image/jpeg"),
            ),
        )

        sends = fake.sends()
        assert len(sends) == 1
        assert "couldn't save" in sends[0].text.lower() or \
               "try again" in sends[0].text.lower()


class TestOutboundImageDispatcher:
    async def test_outbound_attachment_event_sends_photo(
        self, tmp_path: Path,
    ) -> None:
        from tank_backend.core.content import ImageBlock
        from tank_backend.pipeline.bus import BusMessage

        media = _FakeMediaStore()
        # Pre-populate a media URI so .get() resolves.
        stored = await media.put(
            b"\xff\xd8\xffPHOTO", "image/jpeg", session_id="s1",
        )
        manager = _manager_with_media(
            tmp_path, supports_image=True, media_store=media,
        )
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        # Inbound first to wire up the outbound dispatcher.
        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(identity, text="hi")

        assistant = next(iter(manager._conn_mgr.assistants.values()))  # noqa: SLF001
        bus = assistant._bus  # noqa: SLF001

        # Emit an outbound_attachment event with an ImageBlock.
        bus.post(BusMessage(
            type="outbound_attachment",
            source="assistant",
            payload={
                "msg_id": "m1",
                "blocks": [ImageBlock(source=stored.media_uri, mime_type="image/jpeg")],
            },
        ))
        bus.poll()

        # Let the scheduled coroutine run.
        import asyncio
        for _ in range(20):
            if any(r.kind == "send" and r.attachments for r in fake.outbox):
                break
            await asyncio.sleep(0.01)

        sends_with_images = [
            r for r in fake.outbox
            if r.kind == "send" and r.attachments
        ]
        assert len(sends_with_images) == 1
        att = sends_with_images[0].attachments[0]
        assert att.kind == "image"
        assert att.data == b"\xff\xd8\xffPHOTO"
        assert att.mime_type == "image/jpeg"

    async def test_outbound_image_dropped_when_connector_lacks_support(
        self, tmp_path: Path,
    ) -> None:
        from tank_backend.connectors.base import ConnectorCapabilities
        from tank_backend.core.content import ImageBlock
        from tank_backend.pipeline.bus import BusMessage

        media = _FakeMediaStore()
        stored = await media.put(b"X", "image/jpeg", session_id="s1")
        manager = _manager_with_media(
            tmp_path, supports_image=True, media_store=media,
        )

        # Text-only connector — images must not go out.
        text_only_caps = ConnectorCapabilities(
            supports_edits=True,
            supports_images_out=False,
        )
        fake = FakeConnector("text-only", capabilities=text_only_caps)
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(identity, text="hi")

        assistant = next(iter(manager._conn_mgr.assistants.values()))  # noqa: SLF001
        assistant._bus.post(BusMessage(  # noqa: SLF001
            type="outbound_attachment",
            source="assistant",
            payload={
                "msg_id": None,
                "blocks": [ImageBlock(source=stored.media_uri, mime_type="image/jpeg")],
            },
        ))
        assistant._bus.poll()  # noqa: SLF001

        import asyncio
        await asyncio.sleep(0.05)

        sends_with_images = [
            r for r in fake.outbox
            if r.kind == "send" and r.attachments
        ]
        assert sends_with_images == []

    async def test_outbound_url_image_passes_through_without_media_store(
        self, tmp_path: Path,
    ) -> None:
        from tank_backend.core.content import ImageBlock
        from tank_backend.pipeline.bus import BusMessage

        media = _FakeMediaStore()
        manager = _manager_with_media(
            tmp_path, supports_image=True, media_store=media,
        )
        fake = FakeConnector("t")
        manager.register(fake)
        await manager.start_all()

        identity = Identity(platform="fake", external_id="user-1")
        await fake.inject_inbound(identity, text="hi")

        assistant = next(iter(manager._conn_mgr.assistants.values()))  # noqa: SLF001
        assistant._bus.post(BusMessage(  # noqa: SLF001
            type="outbound_attachment",
            source="assistant",
            payload={
                "msg_id": None,
                "blocks": [ImageBlock(source="https://example.com/cat.png",
                                      mime_type="image/png")],
            },
        ))
        assistant._bus.poll()  # noqa: SLF001

        import asyncio
        for _ in range(20):
            if any(r.kind == "send" and r.attachments for r in fake.outbox):
                break
            await asyncio.sleep(0.01)

        sends_with_images = [
            r for r in fake.outbox
            if r.kind == "send" and r.attachments
        ]
        assert len(sends_with_images) == 1
        att = sends_with_images[0].attachments[0]
        # URL path: data is the URL string; MediaStore was not involved
        # for resolution on this outbound.
        assert att.data == "https://example.com/cat.png"
