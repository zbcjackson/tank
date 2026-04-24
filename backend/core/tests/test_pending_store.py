"""Tests for PendingToolCallStore."""

from __future__ import annotations

import threading
import time

from tank_backend.agents.approval import PendingToolCall, PendingToolCallStore


def _make_pending(approval_id: str = "a1", tool_name: str = "run_command") -> PendingToolCall:
    return PendingToolCall(
        approval_id=approval_id,
        tool_name=tool_name,
        tool_args={"command": "ls"},
        tool_call_id="call_123",
        arguments_raw='{"command": "ls"}',
        description="ls",
        session_id="s1",
        created_at=time.time(),
    )


class TestPendingToolCallStore:
    def test_park_and_get_oldest(self):
        store = PendingToolCallStore()
        p = _make_pending("a1")
        store.park(p)
        assert store.get_oldest_pending() is p

    def test_get_oldest_returns_none_when_empty(self):
        store = PendingToolCallStore()
        assert store.get_oldest_pending() is None

    def test_oldest_first_ordering(self):
        store = PendingToolCallStore()
        p1 = _make_pending("a1")
        p2 = _make_pending("a2")
        store.park(p1)
        store.park(p2)
        assert store.get_oldest_pending() is p1

    def test_consume_removes_matching_id(self):
        store = PendingToolCallStore()
        p1 = _make_pending("a1")
        p2 = _make_pending("a2")
        store.park(p1)
        store.park(p2)

        consumed = store.consume("a1")
        assert consumed is p1
        assert store.get_oldest_pending() is p2

    def test_consume_returns_none_for_unknown_id(self):
        store = PendingToolCallStore()
        store.park(_make_pending("a1"))
        assert store.consume("nonexistent") is None

    def test_list_pending_returns_snapshot(self):
        store = PendingToolCallStore()
        p1 = _make_pending("a1")
        p2 = _make_pending("a2")
        store.park(p1)
        store.park(p2)

        pending = store.list_pending()
        assert len(pending) == 2
        assert pending[0] is p1
        assert pending[1] is p2

    def test_clear_all(self):
        store = PendingToolCallStore()
        store.park(_make_pending("a1"))
        store.park(_make_pending("a2"))
        store.clear_all()
        assert store.get_oldest_pending() is None
        assert store.list_pending() == []

    def test_thread_safety(self):
        """Concurrent park + consume should not corrupt state."""
        store = PendingToolCallStore()
        errors: list[Exception] = []

        def park_many():
            try:
                for i in range(100):
                    store.park(_make_pending(f"park_{i}"))
            except Exception as e:
                errors.append(e)

        def consume_many():
            try:
                for i in range(100):
                    store.consume(f"park_{i}")
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=park_many)
        t2 = threading.Thread(target=consume_many)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == []


class TestPendingToolCallSerialization:
    def test_roundtrip(self):
        p = _make_pending("a1", "run_command")
        d = p.to_dict()
        restored = PendingToolCall.from_dict(d)
        assert restored.approval_id == p.approval_id
        assert restored.tool_name == p.tool_name
        assert restored.tool_args == p.tool_args
        assert restored.tool_call_id == p.tool_call_id
        assert restored.arguments_raw == p.arguments_raw
        assert restored.description == p.description
        assert restored.session_id == p.session_id
        assert restored.created_at == p.created_at

    def test_from_dict_missing_optional_fields(self):
        """from_dict should handle dicts from older persisted data."""
        minimal = {"approval_id": "x", "tool_name": "foo"}
        p = PendingToolCall.from_dict(minimal)
        assert p.approval_id == "x"
        assert p.tool_name == "foo"
        assert p.tool_args == {}
        assert p.tool_call_id == ""

    def test_store_to_list_and_restore(self):
        store = PendingToolCallStore()
        store.park(_make_pending("a1"))
        store.park(_make_pending("a2"))

        serialized = store.to_list()
        assert len(serialized) == 2
        assert serialized[0]["approval_id"] == "a1"
        assert serialized[1]["approval_id"] == "a2"

        new_store = PendingToolCallStore()
        new_store.restore(serialized)
        assert new_store.get_oldest_pending().approval_id == "a1"
        assert len(new_store.list_pending()) == 2

    def test_restore_replaces_existing(self):
        store = PendingToolCallStore()
        store.park(_make_pending("old"))
        store.restore([_make_pending("new").to_dict()])
        assert len(store.list_pending()) == 1
        assert store.get_oldest_pending().approval_id == "new"

    def test_to_list_empty_store(self):
        store = PendingToolCallStore()
        assert store.to_list() == []

    def test_restore_empty_list(self):
        store = PendingToolCallStore()
        store.park(_make_pending("a1"))
        store.restore([])
        assert store.get_oldest_pending() is None
