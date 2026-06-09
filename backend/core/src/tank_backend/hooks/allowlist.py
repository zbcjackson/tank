"""Hook consent/allowlist — first-use approval for shell hooks.

Before a hook script runs for the first time, the user must approve it.
Approved hooks are persisted to ``~/.tank/hook-allowlist.json`` so the
approval survives across sessions.

Design (modeled on Hermes ``shell-hooks-allowlist.json``):
- Each hook is identified by ``(event, command)`` pair
- First execution checks the allowlist; if absent, the hook is skipped
  and a warning is logged (fail-safe: never blocks the main flow)
- ``grant()`` adds a hook to the allowlist (called by setup/admin flow)
- ``revoke()`` removes it
- Non-TTY / headless callers can set ``auto_accept=True`` to skip consent
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_ALLOWLIST_PATH = "~/.tank/hook-allowlist.json"


@dataclass(frozen=True)
class HookIdentity:
    """Unique identity of a hook for allowlist purposes."""

    event: str
    command: str

    @property
    def key(self) -> str:
        """Stable key for JSON persistence."""
        return f"{self.event}:{self.command}"

    @property
    def fingerprint(self) -> str:
        """Short hash for display."""
        return hashlib.sha256(self.key.encode()).hexdigest()[:8]


class HookAllowlist:
    """Persistent allowlist for approved hook scripts.

    Loads from disk on first access, writes back on grant/revoke.
    Thread-safe for single-process use (no file locking).
    """

    def __init__(
        self,
        path: str | Path | None = None,
        auto_accept: bool = False,
    ) -> None:
        self._path = Path(os.path.expanduser(path or _DEFAULT_ALLOWLIST_PATH))
        self._auto_accept = auto_accept
        self._entries: set[str] | None = None  # Lazy-loaded

    def _load(self) -> set[str]:
        """Load the allowlist from disk."""
        if self._entries is not None:
            return self._entries

        if not self._path.exists():
            self._entries = set()
            return self._entries

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._entries = set(data)
            elif isinstance(data, dict) and "allowed" in data:
                self._entries = set(data["allowed"])
            else:
                self._entries = set()
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load hook allowlist from %s: %s", self._path, e)
            self._entries = set()

        return self._entries

    def _save(self) -> None:
        """Persist the allowlist to disk."""
        entries = self._load()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "allowed": sorted(entries),
                "_note": "Hook scripts approved for execution. Remove entries to revoke.",
            }
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("Failed to save hook allowlist to %s: %s", self._path, e)

    def is_allowed(self, hook: HookIdentity) -> bool:
        """Check if a hook has been approved.

        Returns True if:
        - auto_accept is enabled (headless/trusted mode), OR
        - the hook's key is in the persisted allowlist
        """
        if self._auto_accept:
            return True
        return hook.key in self._load()

    def grant(self, hook: HookIdentity) -> None:
        """Approve a hook for execution. Persists to disk."""
        entries = self._load()
        if hook.key not in entries:
            entries.add(hook.key)
            self._save()
            logger.info("Hook approved: %s", hook.key)

    def revoke(self, hook: HookIdentity) -> bool:
        """Remove approval for a hook. Returns True if it was present."""
        entries = self._load()
        if hook.key in entries:
            entries.discard(hook.key)
            self._save()
            logger.info("Hook revoked: %s", hook.key)
            return True
        return False

    def list_all(self) -> list[str]:
        """Return all approved hook keys."""
        return sorted(self._load())

    def grant_all(self, hooks: list[HookIdentity]) -> None:
        """Approve multiple hooks at once."""
        entries = self._load()
        changed = False
        for hook in hooks:
            if hook.key not in entries:
                entries.add(hook.key)
                changed = True
        if changed:
            self._save()
