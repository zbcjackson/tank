"""Tests for channel read tracking and unread counts."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from tank_backend.channels.store import ChannelStore
from tank_backend.context.conversation import ConversationData
from tank_backend.context.store import ConversationStore


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
    from tank_backend.persistence import Base, Database
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    return ChannelStore(db)


class TestMarkRead:
    def test_marks_channel_as_read(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.create("test", "Test", conv_store)
        conv = conv_store.load(channel.conversation_id)
        assert conv is not None
        conv.messages.append({"role": "user", "content": "hello"})
        conv.messages.append({"role": "assistant", "content": "hi"})
        conv_store.save(conv)

        channel_store.mark_read("test", conv_store)

        summaries = channel_store.list_channels(conv_store)
        assert summaries[0].unread_count == 0

    def test_unread_count_after_new_messages(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.create("test", "Test", conv_store)
        conv = conv_store.load(channel.conversation_id)
        assert conv is not None

        # Mark read at current state (1 message: system prompt)
        channel_store.mark_read("test", conv_store)

        # Add new messages after marking read
        conv.messages.append({"role": "user", "content": "hello"})
        conv.messages.append({"role": "assistant", "content": "hi"})
        conv_store.save(conv)

        summaries = channel_store.list_channels(conv_store)
        assert summaries[0].unread_count == 2

    def test_unread_count_without_read_state(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.create("test", "Test", conv_store)
        conv = conv_store.load(channel.conversation_id)
        assert conv is not None
        conv.messages.append({"role": "user", "content": "hello"})
        conv_store.save(conv)

        # Never marked read — all messages are unread
        summaries = channel_store.list_channels(conv_store)
        assert summaries[0].unread_count == 2  # system prompt + user msg

    def test_mark_read_nonexistent_channel(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        # Should not raise
        channel_store.mark_read("nonexistent", conv_store)

    def test_mark_read_updates_on_repeated_calls(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel = channel_store.create("test", "Test", conv_store)
        conv = conv_store.load(channel.conversation_id)
        assert conv is not None

        channel_store.mark_read("test", conv_store)
        assert channel_store.list_channels(conv_store)[0].unread_count == 0

        conv.messages.append({"role": "user", "content": "msg1"})
        conv_store.save(conv)
        assert channel_store.list_channels(conv_store)[0].unread_count == 1

        channel_store.mark_read("test", conv_store)
        assert channel_store.list_channels(conv_store)[0].unread_count == 0

    def test_read_state_deleted_with_channel(
        self, channel_store: ChannelStore, conv_store: _MemoryConvStore,
    ):
        channel_store.create("test", "Test", conv_store)
        channel_store.mark_read("test", conv_store)
        channel_store.delete("test", conv_store)

        # Recreate — should have no read state
        channel_store.create("test", "Test 2", conv_store)
        summaries = channel_store.list_channels(conv_store)
        # System prompt is unread since no read state exists
        assert summaries[0].unread_count == 1


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_senders(self):
        from tank_backend.api.manager import ConnectionManager

        ctx = MagicMock()
        mgr = ConnectionManager(app_context=ctx)

        send1 = AsyncMock()
        send2 = AsyncMock()
        mgr.register_sender("s1", send1)
        mgr.register_sender("s2", send2)

        count = await mgr.broadcast('{"type": "test"}')

        assert count == 2
        send1.assert_called_once_with('{"type": "test"}')
        send2.assert_called_once_with('{"type": "test"}')

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_senders(self):
        from tank_backend.api.manager import ConnectionManager

        ctx = MagicMock()
        mgr = ConnectionManager(app_context=ctx)

        good_send = AsyncMock()
        bad_send = AsyncMock(side_effect=RuntimeError("connection closed"))
        mgr.register_sender("good", good_send)
        mgr.register_sender("bad", bad_send)

        count = await mgr.broadcast('{"msg": "hello"}')

        assert count == 1
        # Dead sender removed
        assert "bad" not in mgr._senders

    @pytest.mark.asyncio
    async def test_broadcast_empty_senders(self):
        from tank_backend.api.manager import ConnectionManager

        ctx = MagicMock()
        mgr = ConnectionManager(app_context=ctx)

        count = await mgr.broadcast('{"msg": "hello"}')
        assert count == 0

    def test_register_and_unregister_sender(self):
        from tank_backend.api.manager import ConnectionManager

        ctx = MagicMock()
        mgr = ConnectionManager(app_context=ctx)

        send_fn = AsyncMock()
        mgr.register_sender("s1", send_fn)
        assert "s1" in mgr._senders

        mgr.unregister_sender("s1")
        assert "s1" not in mgr._senders

    def test_unregister_nonexistent_sender(self):
        from tank_backend.api.manager import ConnectionManager

        ctx = MagicMock()
        mgr = ConnectionManager(app_context=ctx)

        # Should not raise
        mgr.unregister_sender("nonexistent")


class TestDeliveryNotification:
    @pytest.mark.asyncio
    async def test_notify_channels_broadcasts(self, tmp_path: Path):
        from tank_backend.jobs.delivery import DeliveryManager
        from tank_backend.jobs.models import DeliveryConfig, JobDefinition

        conv_store = _MemoryConvStore()
        from tank_backend.persistence import Base, Database
        db = Database(f"sqlite+pysqlite:///{tmp_path}/broadcast.db")
        Base.metadata.create_all(db.engine)
        tmp_store = ChannelStore(db)
        tmp_store.create("news", "News", conv_store)

        mgr = AsyncMock()
        mgr.broadcast = AsyncMock(return_value=1)

        delivery = DeliveryManager(
            channel_store=tmp_store,
            conversation_store=conv_store,
        )
        delivery.set_connection_manager(mgr)

        job = JobDefinition(
            id="j1",
            name="test-job",
            prompt="do something",
            schedule="* * * * *",
            delivery=DeliveryConfig(channels=("news",)),
        )

        await delivery.deliver(job, "run-001", "Job output text")

        mgr.broadcast.assert_called_once()
        call_json = mgr.broadcast.call_args[0][0]
        import json
        msg = json.loads(call_json)
        assert msg["type"] == "channel_notification"
        assert msg["metadata"]["channel_slug"] == "news"
        assert msg["metadata"]["job_name"] == "test-job"
        assert any(
            m["role"] == "assistant" and m["content"] == "Job output text"
            for m in msg["metadata"]["messages"]
        )

    @pytest.mark.asyncio
    async def test_deliver_without_connection_manager(self, tmp_path: Path):
        """Delivery works even without a connection manager (no broadcast)."""
        from tank_backend.jobs.delivery import DeliveryManager
        from tank_backend.jobs.models import DeliveryConfig, JobDefinition

        conv_store = _MemoryConvStore()
        from tank_backend.persistence import Base, Database
        db = Database(f"sqlite+pysqlite:///{tmp_path}/no_mgr.db")
        Base.metadata.create_all(db.engine)
        tmp_store = ChannelStore(db)
        tmp_store.create("news", "News", conv_store)

        delivery = DeliveryManager(
            channel_store=tmp_store,
            conversation_store=conv_store,
        )

        job = JobDefinition(
            id="j1",
            name="test-job",
            prompt="do something",
            schedule="* * * * *",
            delivery=DeliveryConfig(channels=("news",), log_output=False),
        )

        # Should not raise
        result = await delivery.deliver(job, "run-001", "output")
        assert result == ""

        # Messages were still delivered to the channel
        channel = tmp_store.get("news")
        assert channel is not None
        conv = conv_store.load(channel.conversation_id)
        assert conv is not None
        assert any(m["content"] == "output" for m in conv.messages)
