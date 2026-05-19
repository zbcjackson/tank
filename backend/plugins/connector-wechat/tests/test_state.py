"""Unit tests for WeChatState."""

from __future__ import annotations

import json
import time
from pathlib import Path

from connector_wechat.state import WeChatState


def test_cursor_save_load(tmp_path: Path) -> None:
    state = WeChatState(tmp_path)
    assert state.sync_cursor is None

    state.save_cursor("abc123")
    assert state.sync_cursor == "abc123"

    # Reload from disk
    state2 = WeChatState(tmp_path)
    assert state2.sync_cursor == "abc123"


def test_context_token_save_load(tmp_path: Path) -> None:
    state = WeChatState(tmp_path)
    assert state.get_context_token("peer1") is None

    state.save_context_token("peer1", "token_a")
    assert state.get_context_token("peer1") == "token_a"

    state.save_context_token("peer2", "token_b")
    assert state.get_context_token("peer2") == "token_b"

    # Reload from disk
    state2 = WeChatState(tmp_path)
    assert state2.get_context_token("peer1") == "token_a"
    assert state2.get_context_token("peer2") == "token_b"


def test_context_token_overwrite(tmp_path: Path) -> None:
    state = WeChatState(tmp_path)
    state.save_context_token("peer1", "old")
    state.save_context_token("peer1", "new")
    assert state.get_context_token("peer1") == "new"


def test_typing_ticket_cache(tmp_path: Path) -> None:
    state = WeChatState(tmp_path)
    assert state.get_typing_ticket("peer1") is None

    state.save_typing_ticket("peer1", "ticket_x")
    assert state.get_typing_ticket("peer1") == "ticket_x"


def test_typing_ticket_expires(tmp_path: Path) -> None:
    state = WeChatState(tmp_path)
    state.save_typing_ticket("peer1", "ticket_x")

    # Simulate time passing beyond TTL (10 minutes)
    state._typing_tickets["peer1"] = ("ticket_x", time.monotonic() - 700)
    assert state.get_typing_ticket("peer1") is None


def test_credentials_save_load(tmp_path: Path) -> None:
    state = WeChatState(tmp_path)
    assert state.load_credentials() is None

    state.save_credentials("acc_123", "tok_456")
    result = state.load_credentials()
    assert result == ("acc_123", "tok_456")

    # Reload from disk
    state2 = WeChatState(tmp_path)
    assert state2.load_credentials() == ("acc_123", "tok_456")


def test_creates_state_dir(tmp_path: Path) -> None:
    new_dir = tmp_path / "nested" / "dir"
    state = WeChatState(new_dir)
    assert new_dir.exists()
    state.save_cursor("test")
    assert (new_dir / "cursor.txt").exists()


def test_handles_corrupt_json(tmp_path: Path) -> None:
    (tmp_path / "context_tokens.json").write_text("not valid json")
    state = WeChatState(tmp_path)
    assert state.get_context_token("peer1") is None


def test_handles_missing_credentials_fields(tmp_path: Path) -> None:
    (tmp_path / "credentials.json").write_text(json.dumps({"account_id": "x"}))
    state = WeChatState(tmp_path)
    assert state.load_credentials() is None
