"""Tests for Checkpointer — SQLite conversation persistence."""

import pytest

from tank_backend.persistence.checkpointer import Checkpointer


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_sessions.db")


@pytest.fixture
def checkpointer(db_path):
    cp = Checkpointer(db_path)
    yield cp
    cp.close()


def test_save_and_load(checkpointer):
    history = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    checkpointer.save("session-1", history)
    loaded = checkpointer.load("session-1")
    assert loaded == history


def test_load_nonexistent_returns_none(checkpointer):
    assert checkpointer.load("nonexistent") is None


def test_save_overwrites_existing(checkpointer):
    checkpointer.save("s1", [{"role": "user", "content": "first"}])
    checkpointer.save("s1", [{"role": "user", "content": "second"}])
    loaded = checkpointer.load("s1")
    assert len(loaded) == 1
    assert loaded[0]["content"] == "second"


def test_delete_session(checkpointer):
    checkpointer.save("s1", [{"role": "user", "content": "hello"}])
    checkpointer.delete("s1")
    assert checkpointer.load("s1") is None


def test_list_sessions(checkpointer):
    checkpointer.save("a", [{"role": "user", "content": "a"}])
    checkpointer.save("b", [{"role": "user", "content": "b"}])
    sessions = checkpointer.list_sessions()
    ids = [s["session_id"] for s in sessions]
    assert "a" in ids
    assert "b" in ids
    assert all("updated_at" in s for s in sessions)


def test_empty_history(checkpointer):
    checkpointer.save("empty", [])
    loaded = checkpointer.load("empty")
    assert loaded == []


def test_close_and_reopen(db_path):
    cp1 = Checkpointer(db_path)
    cp1.save("s1", [{"role": "user", "content": "persisted"}])
    cp1.close()

    cp2 = Checkpointer(db_path)
    loaded = cp2.load("s1")
    cp2.close()
    assert loaded == [{"role": "user", "content": "persisted"}]
