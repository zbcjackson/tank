"""Tests for Channel data models and ChannelStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from tank_backend.channels.models import (
    ChannelData,
    _humanize_slug,
    slugify,
    validate_slug,
)
from tank_backend.channels.store import ChannelStore
from tank_backend.context.conversation import ConversationData
from tank_backend.context.store import ConversationStore

# ── Fixtures ──────────────────────────────────────────────────────────


class _MemoryConvStore(ConversationStore):
    """In-memory ConversationStore for tests."""

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
def conv_store() -> _MemoryConvStore:
    return _MemoryConvStore()


@pytest.fixture()
def channel_store(tmp_path: Path) -> ChannelStore:
    return ChannelStore(tmp_path / "test_channels.db")


# ── Slug validation ───────────────────────────────────────────────────


class TestValidateSlug:
    def test_valid_ascii(self):
        assert validate_slug("daily-report") == "daily-report"

    def test_valid_chinese(self):
        assert validate_slug("每日新闻") == "每日新闻"

    def test_valid_mixed(self):
        assert validate_slug("报告-2024") == "报告-2024"

    def test_valid_underscore(self):
        assert validate_slug("my_channel") == "my_channel"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_slug("")

    def test_rejects_too_short(self):
        with pytest.raises(ValueError):
            validate_slug("ab")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError):
            validate_slug("daily report")

    def test_rejects_leading_hyphen(self):
        with pytest.raises(ValueError):
            validate_slug("-daily")

    def test_rejects_trailing_hyphen(self):
        with pytest.raises(ValueError):
            validate_slug("daily-")

    def test_rejects_special_chars(self):
        with pytest.raises(ValueError):
            validate_slug("daily@report")


class TestSlugify:
    def test_simple_name(self):
        assert slugify("Daily Report") == "daily-report"

    def test_chinese_name(self):
        result = slugify("每日新闻")
        assert "每日新闻" in result

    def test_strips_special_chars(self):
        assert slugify("My Channel #1!") == "my-channel-1"

    def test_short_name_gets_padded(self):
        result = slugify("AB")
        assert len(result) >= 3


class TestHumanizeSlug:
    def test_hyphenated(self):
        assert _humanize_slug("daily-report") == "Daily Report"

    def test_underscored(self):
        assert _humanize_slug("my_channel") == "My Channel"

    def test_chinese(self):
        # Chinese characters have no hyphens/underscores to split on
        assert _humanize_slug("每日新闻") == "每日新闻"


# ── ChannelData ───────────────────────────────────────────────────────


class TestChannelData:
    def test_to_dict_roundtrip(self):
        channel = ChannelData(
            slug="test",
            name="Test Channel",
            conversation_id="abc123",
            description="A test channel",
            auto_created=True,
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
        )
        data = channel.to_dict()
        restored = ChannelData.from_dict(data)
        assert restored == channel

    def test_frozen(self):
        channel = ChannelData(slug="x", name="X", conversation_id="abc")
        with pytest.raises(AttributeError):
            channel.slug = "y"  # type: ignore[misc]


# ── ChannelStore CRUD ─────────────────────────────────────────────────


class TestChannelStoreCreate:
    def test_creates_channel_and_conversation(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.create("test", "Test Channel", conv_store)
        assert channel.slug == "test"
        assert channel.name == "Test Channel"
        assert channel.conversation_id != ""

        # Conversation was created
        conv = conv_store.load(channel.conversation_id)
        assert conv is not None
        assert len(conv.messages) == 1  # system prompt

    def test_rejects_duplicate_slug(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel_store.create("test", "First", conv_store)
        with pytest.raises(ValueError, match="already exists"):
            channel_store.create("test", "Second", conv_store)

    def test_rejects_invalid_slug(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        with pytest.raises(ValueError):
            channel_store.create("bad slug", "Test", conv_store)


class TestChannelStoreGet:
    def test_get_existing(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        created = channel_store.create("test", "Test", conv_store)
        fetched = channel_store.get("test")
        assert fetched is not None
        assert fetched.slug == created.slug
        assert fetched.conversation_id == created.conversation_id

    def test_get_nonexistent(self, channel_store: ChannelStore):
        assert channel_store.get("nope") is None


class TestChannelStoreGetOrCreate:
    def test_returns_existing(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        created = channel_store.create("test", "Original", conv_store)
        fetched = channel_store.get_or_create("test", conversation_store=conv_store)
        assert fetched.conversation_id == created.conversation_id

    def test_auto_creates(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.get_or_create("auto-test", conversation_store=conv_store)
        assert channel.slug == "auto-test"
        assert channel.auto_created is True
        assert conv_store.load(channel.conversation_id) is not None

    def test_auto_creates_with_name(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.get_or_create(
            "custom", name="Custom Name", conversation_store=conv_store,
        )
        assert channel.name == "Custom Name"

    def test_auto_creates_humanized_name(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.get_or_create("daily-report", conversation_store=conv_store)
        assert channel.name == "Daily Report"

    def test_raises_without_store(self, channel_store: ChannelStore):
        with pytest.raises(ValueError, match="no conversation_store"):
            channel_store.get_or_create("new-channel")


class TestChannelStoreList:
    def test_lists_channels(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel_store.create("alpha", "Alpha", conv_store)
        channel_store.create("beta", "Beta", conv_store)
        summaries = channel_store.list_channels(conv_store)
        assert len(summaries) == 2
        slugs = {s.slug for s in summaries}
        assert slugs == {"alpha", "beta"}

    def test_includes_message_count(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.create("test", "Test", conv_store)
        conv = conv_store.load(channel.conversation_id)
        assert conv is not None
        conv.messages.append({"role": "user", "content": "hello"})
        conv_store.save(conv)

        summaries = channel_store.list_channels(conv_store)
        assert summaries[0].message_count == 2  # system prompt + user message

    def test_empty_list(self, channel_store: ChannelStore):
        assert channel_store.list_channels() == []


class TestChannelStoreUpdate:
    def test_updates_name_and_description(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel_store.create("test", "Old Name", conv_store, description="Old desc")
        updated = channel_store.update("test", name="New Name", description="New desc")
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.description == "New desc"

    def test_returns_none_for_nonexistent(self, channel_store: ChannelStore):
        assert channel_store.update("nope", name="X") is None

    def test_preserves_unchanged_fields(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel_store.create("test", "Name", conv_store, description="Desc")
        updated = channel_store.update("test", name="New Name")
        assert updated is not None
        assert updated.description == "Desc"  # unchanged


class TestChannelStoreDelete:
    def test_deletes_channel(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel_store.create("test", "Test", conv_store)
        assert channel_store.delete("test", conv_store) is True
        assert channel_store.get("test") is None

    def test_deletes_underlying_conversation(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.create("test", "Test", conv_store)
        conv_id = channel.conversation_id
        channel_store.delete("test", conv_store)
        assert conv_store.load(conv_id) is None

    def test_returns_false_for_nonexistent(self, channel_store: ChannelStore):
        assert channel_store.delete("nope") is False


class TestChannelStorePromote:
    def test_promotes_conversation(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        conv = ConversationData.new("system prompt")
        conv_store.save(conv)

        channel = channel_store.promote_conversation(
            conversation_id=conv.id,
            slug="promoted",
            name="Promoted Channel",
            conversation_store=conv_store,
        )
        assert channel.slug == "promoted"
        assert channel.conversation_id == conv.id

    def test_rejects_duplicate_slug(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel_store.create("existing", "Existing", conv_store)
        conv = ConversationData.new("system")
        conv_store.save(conv)
        with pytest.raises(ValueError, match="already exists"):
            channel_store.promote_conversation(conv.id, "existing", "Name", conv_store)

    def test_rejects_nonexistent_conversation(self, channel_store: ChannelStore):
        with pytest.raises(ValueError, match="not found"):
            channel_store.promote_conversation(
                "fake-id", "slug", "Name",
                conversation_store=_MemoryConvStore(),
            )
