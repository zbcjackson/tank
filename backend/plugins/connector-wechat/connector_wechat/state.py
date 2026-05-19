"""Disk-backed state for the WeChat connector.

Persists sync cursor, context tokens, and typing ticket cache to
``~/.tank/wechat/<instance>/``. All writes are atomic (write-to-temp +
rename) to avoid corruption on crash.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("WeChatState")

_TYPING_TICKET_TTL_S = 600.0  # 10 minutes


class WeChatState:
    """Manages persistent state for one WeChat connector instance."""

    def __init__(self, state_dir: Path) -> None:
        self._dir = state_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._context_tokens: dict[str, str] = self._load_json("context_tokens.json")
        self._typing_tickets: dict[str, tuple[str, float]] = {}  # peer → (ticket, timestamp)
        self._cursor: str | None = self._load_text("cursor.txt")

    # ── Sync cursor ────────────────────────────────────────────────

    @property
    def sync_cursor(self) -> str | None:
        return self._cursor

    def save_cursor(self, cursor: str) -> None:
        self._cursor = cursor
        self._write_text("cursor.txt", cursor)

    # ── Context tokens (per peer) ──────────────────────────────────

    def get_context_token(self, peer_id: str) -> str | None:
        return self._context_tokens.get(peer_id)

    def save_context_token(self, peer_id: str, token: str) -> None:
        self._context_tokens[peer_id] = token
        self._write_json("context_tokens.json", self._context_tokens)

    # ── Typing tickets (in-memory with TTL) ────────────────────────

    def get_typing_ticket(self, peer_id: str) -> str | None:
        entry = self._typing_tickets.get(peer_id)
        if entry is None:
            return None
        ticket, ts = entry
        if time.monotonic() - ts > _TYPING_TICKET_TTL_S:
            del self._typing_tickets[peer_id]
            return None
        return ticket

    def save_typing_ticket(self, peer_id: str, ticket: str) -> None:
        self._typing_tickets[peer_id] = (ticket, time.monotonic())

    # ── Credentials ────────────────────────────────────────────────

    def save_credentials(self, account_id: str, token: str) -> None:
        self._write_json("credentials.json", {"account_id": account_id, "token": token})

    def load_credentials(self) -> tuple[str, str] | None:
        data = self._load_json("credentials.json")
        if data and "account_id" in data and "token" in data:
            return data["account_id"], data["token"]
        return None

    # ── Internal helpers ───────────────────────────────────────────

    def _load_json(self, filename: str) -> dict:
        path = self._dir / filename
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load %s: %s", path, e)
            return {}

    def _write_json(self, filename: str, data: dict) -> None:
        path = self._dir / filename
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError as e:
            logger.warning("Failed to write %s: %s", path, e)

    def _load_text(self, filename: str) -> str | None:
        path = self._dir / filename
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8").strip()
            return text or None
        except OSError as e:
            logger.warning("Failed to load %s: %s", path, e)
            return None

    def _write_text(self, filename: str, text: str) -> None:
        path = self._dir / filename
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
        except OSError as e:
            logger.warning("Failed to write %s: %s", path, e)
