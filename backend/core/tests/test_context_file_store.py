"""Tests for context.file_store — FileSessionStore."""

import json
from datetime import datetime, timezone

import pytest

from tank_backend.context.file_store import FileSessionStore
from tank_backend.context.session import SessionData


@pytest.fixture
def store(tmp_path):
    return FileSessionStore(tmp_path)


@pytest.fixture
def sample_session():
    return SessionData(
        id="abc123",
        start_time=datetime(2026, 4, 14, 10, 30, 0, tzinfo=timezone.utc),
        pid=12345,
        messages=[
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ],
    )


class TestFileSessionStore:
    def test_save_and_load_roundtrip(self, store, sample_session):
        store.save(sample_session)
        loaded = store.load("abc123")
        assert loaded is not None
        assert loaded.id == "abc123"
        assert loaded.messages == sample_session.messages
        assert loaded.pid == 12345

    def test_load_nonexistent_returns_none(self, store):
        assert store.load("nonexistent") is None

    def test_save_overwrites_existing(self, store, sample_session):
        store.save(sample_session)
        sample_session.messages.append({"role": "assistant", "content": "Hi!"})
        store.save(sample_session)
        loaded = store.load("abc123")
        assert len(loaded.messages) == 3

    def test_delete_removes_file(self, store, sample_session):
        store.save(sample_session)
        store.delete("abc123")
        assert store.load("abc123") is None

    def test_delete_nonexistent_is_noop(self, store):
        store.delete("nonexistent")  # should not raise

    def test_list_sessions_sorted_desc(self, store):
        s1 = SessionData(
            id="first",
            start_time=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
            pid=1,
            messages=[{"role": "system", "content": "a"}],
        )
        s2 = SessionData(
            id="second",
            start_time=datetime(2026, 4, 14, 11, 0, 0, tzinfo=timezone.utc),
            pid=2,
            messages=[{"role": "system", "content": "b"}, {"role": "user", "content": "c"}],
        )
        store.save(s1)
        store.save(s2)
        sessions = store.list_sessions()
        assert len(sessions) == 2
        assert sessions[0].id == "second"  # most recent first
        assert sessions[1].id == "first"
        assert sessions[0].message_count == 2
        assert sessions[1].message_count == 1

    def test_find_latest_returns_most_recent(self, store):
        s1 = SessionData(
            id="old",
            start_time=datetime(2026, 4, 13, 10, 0, 0, tzinfo=timezone.utc),
            pid=1,
            messages=[{"role": "system", "content": "a"}],
        )
        s2 = SessionData(
            id="new",
            start_time=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
            pid=2,
            messages=[{"role": "system", "content": "b"}],
        )
        store.save(s1)
        store.save(s2)
        latest = store.find_latest()
        assert latest is not None
        assert latest.id == "new"

    def test_find_latest_returns_none_when_empty(self, store):
        assert store.find_latest() is None

    def test_directory_created_on_init(self, tmp_path):
        new_dir = tmp_path / "sub" / "sessions"
        FileSessionStore(new_dir)
        assert new_dir.exists()

    def test_file_is_valid_json(self, store, sample_session, tmp_path):
        store.save(sample_session)
        files = [f for f in tmp_path.glob("*.json") if f.name != "index.json"]
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["id"] == "abc123"

    def test_index_file_created(self, store, sample_session, tmp_path):
        store.save(sample_session)
        index_path = tmp_path / "index.json"
        assert index_path.exists()
        index = json.loads(index_path.read_text())
        assert "abc123" in index
        assert index["abc123"]["file"] == "20260414_103000.json"

    def test_index_has_preview(self, store, sample_session, tmp_path):
        store.save(sample_session)
        index = json.loads((tmp_path / "index.json").read_text())
        assert index["abc123"]["preview"] == "Hello"

    def test_load_uses_index(self, store, sample_session):
        store.save(sample_session)
        loaded = store.load("abc123")
        assert loaded is not None
        assert loaded.id == "abc123"

    def test_load_stale_index_entry(self, store, sample_session, tmp_path):
        store.save(sample_session)
        # Delete the session file but keep index
        session_file = tmp_path / "20260414_103000.json"
        session_file.unlink()
        assert store.load("abc123") is None
