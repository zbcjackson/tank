"""Integration tests for the Channels feature.

Tests the seams between ChannelStore, ConversationStore, DeliveryManager,
and the REST API — verifying end-to-end flows that unit tests cannot catch.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tank_backend.channels.store import ChannelStore
from tank_backend.context.conversation import ConversationData
from tank_backend.context.store import ConversationStore
from tank_backend.jobs.delivery import DeliveryManager
from tank_backend.jobs.models import JobDefinition
from tank_backend.persistence import Base, Database

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _InMemoryConversationStore(ConversationStore):
    """Simple in-memory ConversationStore for integration tests."""

    def __init__(self) -> None:
        self._data: dict[str, ConversationData] = {}

    def save(self, conversation: ConversationData) -> None:
        self._data[conversation.id] = conversation

    def load(self, conversation_id: str) -> ConversationData | None:
        return self._data.get(conversation_id)

    def list_conversations(self) -> list:
        return []

    def delete(self, conversation_id: str) -> None:
        self._data.pop(conversation_id, None)

    def find_latest(self) -> ConversationData | None:
        return None

    def close(self) -> None:
        pass


def _make_job(**overrides) -> JobDefinition:
    defaults = {
        "name": "test_job",
        "prompt": "Say hello",
        "schedule": "*/1 * * * *",
    }
    defaults.update(overrides)
    return JobDefinition.from_dict(defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def channel_store(tmp_path):
    db = Database(f"sqlite+pysqlite:///{tmp_path}/tank.db")
    Base.metadata.create_all(db.engine)
    store = ChannelStore(db)
    yield store
    store.close()
    db.dispose()


@pytest.fixture()
def conversation_store():
    return _InMemoryConversationStore()


@pytest.fixture()
def delivery(tmp_path):
    return DeliveryManager(output_dir=tmp_path / "output")


@pytest.fixture()
def delivery_with_channels(tmp_path, channel_store, conversation_store):
    return DeliveryManager(
        output_dir=tmp_path / "output",
        channel_store=channel_store,
        conversation_store=conversation_store,
    )


# ---------------------------------------------------------------------------
# 1. Job → channel delivery (end-to-end)
# ---------------------------------------------------------------------------


class TestJobChannelDelivery:
    """Job with channels config → execute → deliver → channel has messages."""

    async def test_job_delivers_to_channel(
        self, delivery_with_channels, channel_store, conversation_store,
    ):
        job = _make_job(delivery={"channels": ("daily-report",), "log_output": False})
        dm = delivery_with_channels

        await dm.deliver(job, "run_001", "Hello from the job!")

        channel = channel_store.get("daily-report")
        assert channel is not None
        assert channel.auto_created is True

        conv = conversation_store.load(channel.conversation_id)
        assert conv is not None
        # ConversationData.new() adds a system prompt + delivery adds system + assistant = 3
        assert len(conv.messages) == 3
        assert conv.messages[1]["role"] == "system"
        assert "test_job" in conv.messages[1]["content"]
        assert conv.messages[2]["role"] == "assistant"
        assert conv.messages[2]["content"] == "Hello from the job!"

    async def test_job_delivers_to_existing_channel(
        self, delivery_with_channels, channel_store, conversation_store,
    ):
        """Second delivery appends to the same channel — no duplicate channel."""
        # Pre-create the channel
        channel_store.create(
            "daily-report",
            name="Daily Report",
            conversation_store=conversation_store,
        )
        original_channel = channel_store.get("daily-report")
        assert original_channel is not None
        original_conv_id = original_channel.conversation_id

        job = _make_job(delivery={"channels": ("daily-report",), "log_output": False})
        dm = delivery_with_channels

        await dm.deliver(job, "run_001", "First delivery")
        await dm.deliver(job, "run_002", "Second delivery")

        # Still just one channel
        channel = channel_store.get("daily-report")
        assert channel is not None
        assert channel.conversation_id == original_conv_id

        # Should have: system prompt + 2×(system + assistant) = 5 messages
        conv = conversation_store.load(channel.conversation_id)
        assert conv is not None
        assert len(conv.messages) == 5  # 1 initial + 2×2 delivery
        assert any("First delivery" in m["content"] for m in conv.messages)
        assert any("Second delivery" in m["content"] for m in conv.messages)

    async def test_job_without_channels_backward_compat(
        self, delivery, tmp_path,
    ):
        """Job without channels should still save file log if log_output=True."""
        job = _make_job(delivery={"channels": (), "log_output": True})

        output_path = await delivery.deliver(job, "run_001", "Legacy output")
        assert output_path != ""
        assert Path(output_path).exists()
        content = Path(output_path).read_text()
        assert "Legacy output" in content

    async def test_job_without_channels_no_log(
        self, delivery, tmp_path,
    ):
        """Job without channels and log_output=False produces no output."""
        job = _make_job(delivery={"channels": (), "log_output": False})
        output_path = await delivery.deliver(job, "run_001", "No output")
        assert output_path == ""

    async def test_job_delivers_to_multiple_channels(
        self, delivery_with_channels, channel_store, conversation_store,
    ):
        """Delivery to multiple channels creates messages in each."""
        job = _make_job(
            delivery={"channels": ("ch-a", "ch-b"), "log_output": False},
        )
        await delivery_with_channels.deliver(job, "run_001", "Multi delivery")

        for slug in ("ch-a", "ch-b"):
            channel = channel_store.get(slug)
            assert channel is not None
            conv = conversation_store.load(channel.conversation_id)
            assert conv is not None
            assert any(
                m["content"] == "Multi delivery"
                for m in conv.messages
                if m["role"] == "assistant"
            )

    async def test_delivery_metadata_in_messages(
        self, delivery_with_channels, channel_store, conversation_store,
    ):
        """System messages include job name and run ID."""
        job = _make_job(name="news_cron", delivery={"channels": ("news",), "log_output": False})
        await delivery_with_channels.deliver(job, "run_abc", "News result")

        channel = channel_store.get("news")
        conv = conversation_store.load(channel.conversation_id)
        system_msgs = [m for m in conv.messages if m["role"] == "system"]
        assert any("news_cron" in m["content"] and "run_abc" in m["content"] for m in system_msgs)


# ---------------------------------------------------------------------------
# 2. Channel created via REST API, then cron delivers
# ---------------------------------------------------------------------------


class TestChannelAPIThenDelivery:
    """Cross-entry-point consistency: API creates channel, cron delivers to it."""

    async def test_api_create_then_cron_deliver(
        self, channel_store, conversation_store, tmp_path,
    ):
        """Channel created via store, then delivery appends to same channel."""
        channel_store.create(
            "my-channel",
            name="My Channel",
            conversation_store=conversation_store,
        )

        dm = DeliveryManager(
            output_dir=tmp_path / "output",
            channel_store=channel_store,
            conversation_store=conversation_store,
        )
        job = _make_job(delivery={"channels": ("my-channel",), "log_output": False})
        await dm.deliver(job, "run_001", "Cron result")

        channel = channel_store.get("my-channel")
        conv = conversation_store.load(channel.conversation_id)
        # system prompt + delivery (system + assistant) = 3
        assert len(conv.messages) == 3


# ---------------------------------------------------------------------------
# 3. Delete channel → subsequent delivery auto-creates
# ---------------------------------------------------------------------------


class TestChannelDeleteAndRecreate:
    """Deleting a channel and re-delivering auto-creates a fresh one."""

    async def test_delete_then_redeliver(
        self, channel_store, conversation_store, tmp_path,
    ):
        channel_store.create(
            "temp-channel",
            name="Temp",
            conversation_store=conversation_store,
        )
        original = channel_store.get("temp-channel")
        original_conv_id = original.conversation_id

        channel_store.delete("temp-channel", conversation_store=conversation_store)
        assert channel_store.get("temp-channel") is None
        assert conversation_store.load(original_conv_id) is None

        dm = DeliveryManager(
            output_dir=tmp_path / "output",
            channel_store=channel_store,
            conversation_store=conversation_store,
        )
        job = _make_job(delivery={"channels": ("temp-channel",), "log_output": False})
        await dm.deliver(job, "run_001", "Recreated")

        new_channel = channel_store.get("temp-channel")
        assert new_channel is not None
        assert new_channel.conversation_id != original_conv_id
        assert new_channel.auto_created is True

        conv = conversation_store.load(new_channel.conversation_id)
        assert conv is not None
        assert any(m["content"] == "Recreated" for m in conv.messages)


# ---------------------------------------------------------------------------
# 4. Promote conversation → list channels → verify
# ---------------------------------------------------------------------------


class TestPromoteConversation:
    """Promote an existing conversation into a channel."""

    def test_promote_then_list(
        self, channel_store, conversation_store,
    ):
        # Create a conversation manually
        conv = ConversationData.new(system_prompt="You are helpful.")
        conv.messages.append({"role": "user", "content": "Hello"})
        conv.messages.append({"role": "assistant", "content": "Hi!"})
        conversation_store.save(conv)

        # Promote to channel
        channel = channel_store.promote_conversation(
            conversation_id=conv.id,
            slug="promoted-chat",
            name="Promoted Chat",
        )
        assert channel.slug == "promoted-chat"
        assert channel.conversation_id == conv.id
        assert channel.auto_created is False

        # List channels should include it
        channels = channel_store.list_channels(conversation_store)
        slugs = [c.slug for c in channels]
        assert "promoted-chat" in slugs

        # Messages should still be there
        loaded = conversation_store.load(conv.id)
        assert len(loaded.messages) == 3  # system + user + assistant

    def test_promote_duplicate_slug_fails(
        self, channel_store, conversation_store,
    ):
        conv = ConversationData.new(system_prompt="")
        conversation_store.save(conv)

        channel_store.create(
            "taken-slug", name="Taken", conversation_store=conversation_store,
        )

        with pytest.raises(ValueError, match="already exists"):
            channel_store.promote_conversation(
                conversation_id=conv.id,
                slug="taken-slug",
                name="Duplicate",
            )


# ---------------------------------------------------------------------------
# 5. Concurrent delivery to same channel (SQLite WAL)
# ---------------------------------------------------------------------------


class TestConcurrentDelivery:
    """SQLite WAL handles concurrent writes to the same channel."""

    async def test_concurrent_deliveries(
        self, channel_store, conversation_store, tmp_path,
    ):
        dm = DeliveryManager(
            output_dir=tmp_path / "output",
            channel_store=channel_store,
            conversation_store=conversation_store,
        )
        job = _make_job(delivery={"channels": ("shared-channel",), "log_output": False})

        # Run 5 deliveries concurrently
        tasks = [
            dm.deliver(job, f"run_{i:03d}", f"Concurrent message {i}")
            for i in range(5)
        ]
        await asyncio.gather(*tasks)

        channel = channel_store.get("shared-channel")
        assert channel is not None

        conv = conversation_store.load(channel.conversation_id)
        assert conv is not None
        # System prompt + 5 deliveries × 2 messages = 11
        assert len(conv.messages) == 11

        # All messages should be present
        assistant_msgs = [m for m in conv.messages if m["role"] == "assistant"]
        contents = {m["content"] for m in assistant_msgs}
        assert len(contents) == 5
        for i in range(5):
            assert f"Concurrent message {i}" in contents


# ---------------------------------------------------------------------------
# 6. Full flow: job runner → delivery → channel has messages
# ---------------------------------------------------------------------------


class TestJobRunnerEndToEnd:
    """Full AutonomousRunner flow with channel delivery."""

    async def test_runner_executes_and_delivers_to_channel(
        self, channel_store, conversation_store, tmp_path,
    ):
        from tank_backend.jobs.runner import AutonomousRunner

        dm = DeliveryManager(
            output_dir=tmp_path / "output",
            channel_store=channel_store,
            conversation_store=conversation_store,
        )
        runner = AutonomousRunner(
            app_config=MagicMock(),
            job_store=MagicMock(),
            delivery=dm,
        )

        job = _make_job(delivery={"channels": ("e2e-channel",), "log_output": True})

        with patch.object(runner, "_run_agent", return_value="E2E result"):
            result = await runner.execute(job)

        assert result.status == "succeeded"

        channel = channel_store.get("e2e-channel")
        assert channel is not None

        conv = conversation_store.load(channel.conversation_id)
        assert conv is not None
        assert any(m["content"] == "E2E result" for m in conv.messages)


# ---------------------------------------------------------------------------
# 7. ContextManager channel-aware prepare_turn + no-op compact
# ---------------------------------------------------------------------------


class TestChannelContextManager:
    """ContextManager uses non-destructive context for channel conversations."""

    @staticmethod
    def _make_app_config():
        cfg = MagicMock()
        cfg.memory.enabled = False
        cfg.preferences.enabled = False
        cfg.get_llm_profile.side_effect = KeyError("no profile")
        return cfg

    async def test_prepare_turn_returns_derived_context(
        self, channel_store, conversation_store, tmp_path,
    ):
        """For channel conversations, prepare_turn returns derived context,
        not the raw (potentially huge) message list."""
        from tank_backend.config.models import ContextConfig
        from tank_backend.context.manager import ContextManager
        from tank_backend.context.resolver import ConversationResolver

        # Create a channel with many messages
        channel = channel_store.create(
            "big-channel", name="Big Channel",
            conversation_store=conversation_store,
        )
        conv = conversation_store.load(channel.conversation_id)
        for i in range(20):
            conv.messages.append({"role": "user", "content": f"Message {i}"})
            conv.messages.append({"role": "assistant", "content": f"Reply {i}"})
        conversation_store.save(conv)

        resolver = ConversationResolver(
            conversation_store=conversation_store,
            channel_store=channel_store,
        )
        config = ContextConfig(
            max_history_tokens=500,
            keep_recent_messages=4,
        )
        ctx = ContextManager(
            app_config=self._make_app_config(),
            resolver=resolver,
            config=config,
        )

        # Resume the channel conversation via resolver
        resolved = resolver.resume(channel.conversation_id, "You are helpful.")
        assert resolved is not None
        ctx.set_conversation(resolved)

        # prepare_turn should return derived (compacted) context, not all 41+ messages
        messages = await ctx.prepare_turn("test-user", "New question")
        assert len(messages) < len(conv.messages)

        # Full history should still be preserved (user message was appended)
        full = conversation_store.load(channel.conversation_id)
        assert len(full.messages) > len(messages)
        assert full.messages[-1]["content"] == "New question"

    async def test_compact_is_noop_for_channels(
        self, channel_store, conversation_store, tmp_path,
    ):
        """compact() should not modify channel conversation history."""
        from tank_backend.config.models import ContextConfig
        from tank_backend.context.manager import ContextManager
        from tank_backend.context.resolver import ConversationResolver

        channel = channel_store.create(
            "preserved", name="Preserved",
            conversation_store=conversation_store,
        )
        conv = conversation_store.load(channel.conversation_id)
        for i in range(30):
            conv.messages.append({"role": "user", "content": f"Msg {i}"})
            conv.messages.append({"role": "assistant", "content": f"Reply {i}"})
        conversation_store.save(conv)
        original_count = len(conv.messages)

        resolver = ConversationResolver(
            conversation_store=conversation_store,
            channel_store=channel_store,
        )
        config = ContextConfig(
            max_history_tokens=200,
            keep_recent_messages=4,
        )
        ctx = ContextManager(
            app_config=self._make_app_config(),
            resolver=resolver,
            config=config,
        )
        resolved = resolver.resume(channel.conversation_id, "You are helpful.")
        ctx.set_conversation(resolved)

        # compact should be a no-op
        await ctx.compact()

        # Messages unchanged
        reloaded = conversation_store.load(channel.conversation_id)
        assert len(reloaded.messages) == original_count

    async def test_regular_conversation_unaffected(
        self, channel_store, conversation_store, tmp_path,
    ):
        """Regular (non-channel) conversations still use normal prepare_turn."""
        from tank_backend.config.models import ContextConfig
        from tank_backend.context.manager import ContextManager
        from tank_backend.context.resolver import ConversationResolver

        # Create a regular conversation (not a channel)
        conv = ConversationData.new(system_prompt="You are helpful.")
        conv.messages.append({"role": "user", "content": "Hello"})
        conv.messages.append({"role": "assistant", "content": "Hi!"})
        conversation_store.save(conv)

        resolver = ConversationResolver(
            conversation_store=conversation_store,
            channel_store=channel_store,
        )
        config = ContextConfig(max_history_tokens=100000)
        ctx = ContextManager(
            app_config=self._make_app_config(),
            resolver=resolver,
            config=config,
        )
        resolved = resolver.resume(conv.id, "You are helpful.")
        ctx.set_conversation(resolved)

        messages = await ctx.prepare_turn("test-user", "Question")
        # Regular: returns all messages (system + user + assistant + new user)
        assert len(messages) == 4
        assert messages[-1]["content"] == "Question"
