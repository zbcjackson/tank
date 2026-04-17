"""Tests for context.conversation — data model and helpers."""

import os
import re
from datetime import datetime, timezone

from tank_backend.context.conversation import (
    ConversationData,
    ConversationSummary,
    conversation_filename,
    generate_conversation_id,
)


class TestGenerateConversationId:
    def test_returns_hex_string(self):
        cid = generate_conversation_id()
        assert re.fullmatch(r"[0-9a-f]{32}", cid)

    def test_unique_each_call(self):
        ids = {generate_conversation_id() for _ in range(100)}
        assert len(ids) == 100


class TestConversationFilename:
    def test_format(self):
        dt = datetime(2026, 4, 14, 17, 34, 40, tzinfo=timezone.utc)
        assert conversation_filename(dt) == "20260414_173440.json"

    def test_zero_padded(self):
        dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        assert conversation_filename(dt) == "20260102_030405.json"


class TestConversationData:
    def test_new_creates_with_system_prompt(self):
        conversation = ConversationData.new("You are helpful.")
        assert conversation.messages == [{"role": "system", "content": "You are helpful."}]
        assert conversation.pid == os.getpid()
        assert conversation.id  # non-empty
        assert conversation.start_time.tzinfo is not None

    def test_to_dict_from_dict_roundtrip(self):
        original = ConversationData.new("test prompt")
        data = original.to_dict()
        restored = ConversationData.from_dict(data)
        assert restored.id == original.id
        assert restored.start_time == original.start_time
        assert restored.pid == original.pid
        assert restored.messages == original.messages

    def test_to_dict_format(self):
        conversation = ConversationData.new("prompt")
        d = conversation.to_dict()
        assert isinstance(d["id"], str)
        assert isinstance(d["start_time"], str)
        assert isinstance(d["pid"], int)
        assert isinstance(d["messages"], list)


class TestConversationSummary:
    def test_frozen(self):
        summary = ConversationSummary(
            id="abc", start_time=datetime.now(timezone.utc), message_count=5
        )
        assert summary.id == "abc"
        assert summary.message_count == 5
