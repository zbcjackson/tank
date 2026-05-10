"""Unit tests for :class:`SessionMapper` and slug derivation."""

from __future__ import annotations

from pathlib import Path

import pytest

from tank_backend.channels.store import ChannelStore
from tank_backend.connectors.base import Identity
from tank_backend.connectors.identity_store import ConnectorIdentityStore
from tank_backend.connectors.session_mapper import SessionMapper, derive_slug
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


@pytest.fixture()
def mapper(tmp_path: Path) -> SessionMapper:
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    identity_store = ConnectorIdentityStore(db)
    channel_store = ChannelStore(db)
    conversation_store = _MemoryConvStore()
    return SessionMapper(identity_store, channel_store, conversation_store)


class TestDeriveSlug:
    def test_basic_platform_external(self) -> None:
        assert derive_slug(Identity(platform="telegram", external_id="12345")) == "telegram-12345"

    def test_lowercases(self) -> None:
        assert derive_slug(Identity(platform="TG", external_id="ABC")) == "tg-abc"

    def test_strips_special_chars(self) -> None:
        slug = derive_slug(Identity(platform="slack", external_id="C#01!"))
        assert slug == "slack-c-01"

    def test_truncates_over_50_chars(self) -> None:
        long_id = "x" * 100
        slug = derive_slug(Identity(platform="p", external_id=long_id))
        assert len(slug) <= 50
        assert slug.startswith("p-")

    def test_pads_short_slug_to_minimum(self) -> None:
        slug = derive_slug(Identity(platform="", external_id=""))
        assert len(slug) >= 3


class TestSessionMapperResolve:
    def test_first_resolve_creates_channel_and_session(
        self, mapper: SessionMapper,
    ) -> None:
        ident = Identity(platform="telegram", external_id="chat-1", display_name="Alice")
        session_id = mapper.resolve(ident)

        assert session_id
        # Channel must exist
        slug = derive_slug(ident)
        assert mapper._channel_store.get(slug) is not None  # noqa: SLF001

    def test_second_resolve_returns_same_session(
        self, mapper: SessionMapper,
    ) -> None:
        ident = Identity(platform="telegram", external_id="chat-1")
        first = mapper.resolve(ident)
        second = mapper.resolve(ident)
        assert first == second

    def test_different_identity_gets_different_session(
        self, mapper: SessionMapper,
    ) -> None:
        a = mapper.resolve(Identity(platform="telegram", external_id="chat-1"))
        b = mapper.resolve(Identity(platform="telegram", external_id="chat-2"))
        assert a != b

    def test_same_external_id_across_platforms_isolated(
        self, mapper: SessionMapper,
    ) -> None:
        a = mapper.resolve(Identity(platform="telegram", external_id="12345"))
        b = mapper.resolve(Identity(platform="slack", external_id="12345"))
        assert a != b

    def test_display_name_used_as_channel_name(
        self, mapper: SessionMapper,
    ) -> None:
        ident = Identity(
            platform="telegram", external_id="chat-1", display_name="Team Alpha",
        )
        mapper.resolve(ident)
        channel = mapper._channel_store.get(derive_slug(ident))  # noqa: SLF001
        assert channel is not None
        assert channel.name == "Team Alpha"
