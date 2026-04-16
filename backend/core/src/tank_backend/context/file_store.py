"""FileSessionStore — file-based session persistence with index."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from .session import SessionData, SessionSummary, session_filename
from .store import SessionStore

logger = logging.getLogger(__name__)

_INDEX_FILENAME = "index.json"
_PREVIEW_MAX_LEN = 100


def _extract_preview(messages: list[dict]) -> str:
    """Extract first user message content as preview (truncated)."""
    for msg in messages:
        if msg.get("role") == "user":
            text = msg.get("content", "")
            if len(text) > _PREVIEW_MAX_LEN:
                return text[:_PREVIEW_MAX_LEN] + "…"
            return text
    return ""


class FileSessionStore(SessionStore):
    """Persist sessions as individual JSON files with an index for O(1) lookup.

    Filename convention: ``YYYYMMDD_HHMMSS.json`` (derived from session start time).
    Index file: ``index.json`` maps session ID → filename + metadata.
    """

    def __init__(self, directory: str | Path = "~/.tank/sessions") -> None:
        self._dir = Path(directory).expanduser().resolve()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, dict] = self._load_index()

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _index_path(self) -> Path:
        return self._dir / _INDEX_FILENAME

    def _load_index(self) -> dict[str, dict]:
        path = self._index_path()
        if path.exists():
            try:
                index = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("Corrupt index file, rebuilding", exc_info=True)
                return self._rebuild_index()
        else:
            index = {}

        # Reconcile: detect session files not in the index
        indexed_files = {e["file"] for e in index.values()}
        needs_save = False
        for p in self._dir.glob("*.json"):
            if p.name == _INDEX_FILENAME or p.name in indexed_files:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                sid = data["id"]
                index[sid] = {
                    "file": p.name,
                    "start": data["start_time"],
                    "n": len(data.get("messages", [])),
                    "preview": _extract_preview(data.get("messages", [])),
                }
                needs_save = True
                logger.info("Indexed orphan session file: %s (id=%s)", p.name, sid)
            except Exception:
                logger.warning("Skipping unreadable file %s", p.name)
        if needs_save:
            self._index = index
            self._save_index()
        return index

    def _save_index(self) -> None:
        path = self._index_path()
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(self._index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.rename(path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def _rebuild_index(self) -> dict[str, dict]:
        """Rebuild index by scanning all session files."""
        index: dict[str, dict] = {}
        for path in self._dir.glob("*.json"):
            if path.name == _INDEX_FILENAME:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sid = data["id"]
                index[sid] = {
                    "file": path.name,
                    "start": data["start_time"],
                    "n": len(data.get("messages", [])),
                    "preview": _extract_preview(data.get("messages", [])),
                }
            except Exception:
                logger.warning("Skipping corrupt file %s", path)
        self._index = index
        self._save_index()
        return index

    # ------------------------------------------------------------------
    # SessionStore interface
    # ------------------------------------------------------------------

    def save(self, session: SessionData) -> None:
        """Atomic write session file + update index."""
        fname = session_filename(session.start_time)
        path = self._dir / fname
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.rename(path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        self._index[session.id] = {
            "file": fname,
            "start": session.start_time.isoformat(),
            "n": len(session.messages),
            "preview": _extract_preview(session.messages),
        }
        self._save_index()

    def load(self, session_id: str) -> SessionData | None:
        """O(1) lookup via index."""
        entry = self._index.get(session_id)
        if entry is None:
            return None
        path = self._dir / entry["file"]
        if not path.exists():
            del self._index[session_id]
            self._save_index()
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SessionData.from_dict(data)
        except Exception:
            logger.warning("Failed to read session file %s", path, exc_info=True)
            return None

    def list_sessions(self) -> list[SessionSummary]:
        """Build from index (no file scanning)."""
        results: list[SessionSummary] = []
        for sid, entry in self._index.items():
            results.append(
                SessionSummary(
                    id=sid,
                    start_time=datetime.fromisoformat(entry["start"]),
                    message_count=entry["n"],
                    preview=entry.get("preview", ""),
                )
            )
        results.sort(key=lambda s: s.start_time, reverse=True)
        return results

    def delete(self, session_id: str) -> None:
        """Delete session file and remove from index."""
        entry = self._index.pop(session_id, None)
        if entry:
            (self._dir / entry["file"]).unlink(missing_ok=True)
            self._save_index()

    def find_latest(self) -> SessionData | None:
        """Load the most recent session via index."""
        if not self._index:
            return None
        latest_id = max(self._index, key=lambda k: self._index[k]["start"])
        return self.load(latest_id)
