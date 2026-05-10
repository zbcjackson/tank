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

    async def get_or_create_assistant(
        self, session_id: str,
    ) -> tuple[_FakeAssistant, bool]:
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
    return ConnectorManager(
        connection_manager=connection_manager,  # type: ignore[arg-type]
        session_mapper=session_mapper,
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
