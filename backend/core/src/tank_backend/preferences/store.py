"""PreferenceStore — file-backed per-user learned preferences."""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from pathlib import Path

from ..users import is_guest

logger = logging.getLogger(__name__)

_STALENESS_DAYS = 90  # Entries older than this are auto-removed
_PINNED = "pinned"  # Source tier that escapes staleness sweep + cap


def _slugify(user: str) -> str:
    """Convert user name to filesystem-safe slug."""
    if is_guest(user):
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


# Matches: "- Some preference text [source, 2026-04-21]"
# Also matches old format: "- Some preference text [source]" or "- Some preference text"
_ENTRY_RE = re.compile(
    r"^-\s+(.+?)(?:\s+\[([^,\]]*?)(?:,\s*(\d{4}-\d{2}-\d{2}))?\])?\s*$"
)


class PreferenceStore:
    """Manages per-user learned preferences on disk.

    File layout::

        {base_dir}/users/{slug}/preferences.md
        {base_dir}/users/{slug}/USER.md  (optional per-user overrides)

    Each entry is a markdown bullet with metadata suffix::

        - Prefers weather in Celsius [explicit, 2026-04-21]

    Staleness: entries older than 90 days are auto-removed on load.
    """

    def __init__(self, base_dir: Path, max_entries: int = 20) -> None:
        self._base_dir = base_dir
        self._max_entries = max_entries

    def _resolve_user_dir(self, user: str) -> str:
        """Resolve user identifier to a directory name.

        Tries in order:
        1. Direct match (user_id directory exists)
        2. Legacy slug-based directory (exists or as fallback for name-based callers)
        3. Falls back to slug for new directories (preserves legacy behavior)
        """
        # Direct user_id match (e.g. "a1b2c3d4e5f6")
        direct = self._base_dir / "users" / user
        if direct.is_dir():
            return user

        # Legacy slug-based lookup
        slug = _slugify(user)

        # If slug differs from user, the caller passed a name, not a user_id.
        # Use slug for backward compatibility.
        if slug != user:
            return slug

        # user looks like a user_id (slug == user), use as-is
        return user

    def _prefs_path(self, user: str) -> Path:
        dir_name = self._resolve_user_dir(user)
        return self._base_dir / "users" / dir_name / "preferences.md"

    def user_file_path(self, user: str, filename: str) -> Path:
        """Resolve an arbitrary per-user file path under the user's dir.

        Lets other modules (e.g. the Dream consolidator's DREAMS.md
        diary) store files alongside ``preferences.md`` without
        duplicating the user-dir resolution logic.
        """
        dir_name = self._resolve_user_dir(user)
        return self._base_dir / "users" / dir_name / filename

    def _user_override_path(self, user: str) -> Path:
        dir_name = self._resolve_user_dir(user)
        return self._base_dir / "users" / dir_name / "USER.md"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_if_new(self, user: str, text: str, source: str = "inferred") -> bool:
        """Add a preference if not semantically duplicate. Returns True if added.

        ``source="pinned"`` entries skip the max-entry cap (durable tier).
        """
        if is_guest(user):
            return False
        text = text.strip()
        if not text:
            return False

        raw_entries = self._load_raw_entries(user)
        texts = [e[0] for e in raw_entries]

        # Dedup: reject if >60% token overlap with any existing entry
        for existing in texts:
            if _similarity(existing, text) > 0.6:
                logger.debug("Preference duplicate skipped: %s", text)
                return False

        # Cap at max_entries — drop oldest non-pinned entry.
        # Pinned entries are durable and never evicted by the cap.
        if source != _PINNED:
            non_pinned = [
                i for i, (_t, s, _d) in enumerate(raw_entries) if s != _PINNED
            ]
            if len(non_pinned) >= self._max_entries:
                raw_entries.pop(non_pinned[0])

        raw_entries.append((text, source, date.today().isoformat()))
        self._save_raw_entries(user, raw_entries)
        logger.info("Preference added for %s: %s [%s]", user, text, source)
        return True

    def reinforce(self, user: str, substring: str) -> bool:
        """Refresh the timestamp of an existing entry (prevents staleness decay).

        Returns True if an entry was found and reinforced.
        """
        if is_guest(user):
            return False
        substring_lower = substring.lower()
        raw_entries = self._load_raw_entries(user)
        for i, (text, source, _date) in enumerate(raw_entries):
            if substring_lower in text.lower():
                raw_entries[i] = (text, source, date.today().isoformat())
                self._save_raw_entries(user, raw_entries)
                logger.debug("Preference reinforced for %s: %s", user, text)
                return True
        return False

    def remove(self, user: str, substring: str) -> bool:
        """Remove the first entry matching substring. Returns True if removed."""
        if is_guest(user):
            return False
        substring_lower = substring.lower()
        raw_entries = self._load_raw_entries(user)
        for i, (text, _source, _date) in enumerate(raw_entries):
            if substring_lower in text.lower():
                raw_entries.pop(i)
                self._save_raw_entries(user, raw_entries)
                logger.info("Preference removed for %s: %s", user, text)
                return True
        return False

    def list_for_user(self, user: str) -> list[str]:
        """Return all preference texts for a user, pinned first.

        Pinned entries are ordered before non-pinned (learned/explicit)
        entries so the most durable facts surface first.
        """
        if is_guest(user):
            return []
        entries = self._load_raw_entries(user)
        pinned = [text for text, source, _date in entries if source == _PINNED]
        rest = [text for text, source, _date in entries if source != _PINNED]
        return pinned + rest

    def list_pinned(self, user: str) -> list[str]:
        """Return only pinned preference texts for a user."""
        if is_guest(user):
            return []
        return [
            text for text, source, _date in self._load_raw_entries(user)
            if source == _PINNED
        ]

    def render_for_user(self, user: str) -> str:
        """Render preferences for system prompt injection.

        Merge order:
        1. Per-user USER.md (explicit overrides, if exists)
        2. Learned preferences.md (pinned first, then inferred/explicit)

        Returns empty string for guest/unidentified users.
        """
        if is_guest(user):
            return ""
        parts: list[str] = []

        # Per-user USER.md override
        user_override = self._user_override_path(user)
        if user_override.exists():
            try:
                content = user_override.read_text(encoding="utf-8").strip()
                if content:
                    parts.append(content)
            except Exception:
                logger.warning("Failed to read %s", user_override, exc_info=True)

        # Learned preferences (pinned first via list_for_user ordering)
        entries = self.list_for_user(user)
        if entries:
            parts.append("\n".join(f"- {e}" for e in entries))

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _load_raw_entries(self, user: str) -> list[tuple[str, str, str]]:
        """Load entries with metadata. Auto-removes stale non-pinned entries.

        Returns list of (text, source, date_str) tuples. Bullets written by
        hand without a ``[source, date]`` suffix are treated as ``pinned``.
        """
        path = self._prefs_path(user)
        if not path.exists():
            return []

        cutoff = (date.today() - timedelta(days=_STALENESS_DAYS)).isoformat()
        entries: list[tuple[str, str, str]] = []
        stale_found = False

        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                m = _ENTRY_RE.match(line)
                if not m:
                    continue
                text = m.group(1).strip()
                raw_source = m.group(2)
                raw_date = m.group(3)

                # Hand-edited bullet with no [source, date] suffix → pinned.
                if raw_source is None and raw_date is None:
                    source = _PINNED
                else:
                    source = (raw_source or "").strip()
                date_str = raw_date or date.today().isoformat()

                # Pinned entries are durable — skip staleness sweep.
                if source != _PINNED and date_str < cutoff:
                    stale_found = True
                    logger.debug("Stale preference removed for %s: %s", user, text)
                    continue
                entries.append((text, source, date_str))
        except Exception:
            logger.warning("Failed to read preferences: %s", path, exc_info=True)
            return []

        # Persist cleanup if stale entries were removed
        if stale_found:
            self._save_raw_entries(user, entries)

        return entries

    def _save_raw_entries(
        self, user: str, entries: list[tuple[str, str, str]],
    ) -> None:
        """Write entries to disk with metadata suffix."""
        path = self._prefs_path(user)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        for text, source, date_str in entries:
            suffix = f" [{source}, {date_str}]" if source else f" [, {date_str}]"
            lines.append(f"- {text}{suffix}")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Legacy compatibility — keep old method names working
    def _load_entries(self, user: str) -> list[str]:
        """Load preference texts (staleness-filtered). Legacy wrapper."""
        return self.list_for_user(user)

    def _save_entries(
        self, user: str, entries: list[str], source: str = "",
    ) -> None:
        """Write entries to disk. Legacy wrapper."""
        today = date.today().isoformat()
        raw = [(text, source, today) for text in entries]
        self._save_raw_entries(user, raw)
