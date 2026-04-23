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
