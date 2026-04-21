"""PreferenceStore — file-backed per-user learned preferences."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


def _slugify(user: str) -> str:
    """Convert user name to filesystem-safe slug."""
    if not user or user == "Unknown":
        return "_default"
    return re.sub(r"[^a-z0-9_]", "_", user.lower()).strip("_") or "_default"


def _similarity(a: str, b: str) -> float:
    """Token overlap ratio between two strings (0.0–1.0)."""
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    return len(intersection) / min(len(tokens_a), len(tokens_b))


_ENTRY_RE = re.compile(r"^-\s+(.+?)(?:\s+\[.+\])?\s*$")


class PreferenceStore:
    """Manages per-user learned preferences on disk.

    File layout::

        {base_dir}/users/{slug}/preferences.md

    Each entry is a markdown bullet with metadata suffix::

        - Prefers weather in Celsius [explicit, 2026-04-21]
    """

    def __init__(self, base_dir: Path, max_entries: int = 20) -> None:
        self._base_dir = base_dir
        self._max_entries = max_entries

    def _prefs_path(self, user: str) -> Path:
        slug = _slugify(user)
        return self._base_dir / "users" / slug / "preferences.md"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_if_new(self, user: str, text: str, source: str = "inferred") -> bool:
        """Add a preference if not semantically duplicate. Returns True if added."""
        text = text.strip()
        if not text:
            return False

        entries = self._load_entries(user)

        # Dedup: reject if >60% token overlap with any existing entry
        for existing in entries:
            if _similarity(existing, text) > 0.6:
                logger.debug("Preference duplicate skipped: %s", text)
                return False

        # Cap at max_entries — drop oldest
        if len(entries) >= self._max_entries:
            entries.pop(0)

        entries.append(text)
        self._save_entries(user, entries, source)
        logger.info("Preference added for %s: %s [%s]", user, text, source)
        return True

    def remove(self, user: str, substring: str) -> bool:
        """Remove the first entry matching substring. Returns True if removed."""
        substring_lower = substring.lower()
        entries = self._load_entries(user)
        for i, entry in enumerate(entries):
            if substring_lower in entry.lower():
                entries.pop(i)
                self._save_entries(user, entries)
                logger.info("Preference removed for %s: %s", user, entry)
                return True
        return False

    def list_for_user(self, user: str) -> list[str]:
        """Return all preference texts for a user."""
        return self._load_entries(user)

    def render_for_user(self, user: str) -> str:
        """Render preferences as a bullet list for system prompt injection."""
        entries = self._load_entries(user)
        if not entries:
            return ""
        return "\n".join(f"- {e}" for e in entries)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _load_entries(self, user: str) -> list[str]:
        """Load preference entries from disk. Returns list of preference texts."""
        path = self._prefs_path(user)
        if not path.exists():
            return []

        entries: list[str] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                m = _ENTRY_RE.match(line)
                if m:
                    entries.append(m.group(1).strip())
        except Exception:
            logger.warning("Failed to read preferences: %s", path, exc_info=True)
        return entries

    def _save_entries(
        self, user: str, entries: list[str], source: str = ""
    ) -> None:
        """Write entries to disk with metadata suffix."""
        path = self._prefs_path(user)
        path.parent.mkdir(parents=True, exist_ok=True)

        today = date.today().isoformat()
        lines: list[str] = []
        for entry in entries:
            suffix = f" [{source}, {today}]" if source else ""
            lines.append(f"- {entry}{suffix}")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
