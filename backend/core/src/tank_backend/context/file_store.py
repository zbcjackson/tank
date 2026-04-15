"""FileSessionStore — file-based session persistence."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from .session import SessionData, SessionSummary, session_filename
from .store import SessionStore

logger = logging.getLogger(__name__)


class FileSessionStore(SessionStore):
    """Persist sessions as individual JSON files in a directory.

    Filename convention: ``YYYYMMDD_HHMMSS.json`` (derived from session start time).
    """

    def __init__(self, directory: str | Path = "~/.tank/sessions") -> None:
        self._dir = Path(directory).expanduser().resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, session: SessionData) -> None:
        """Atomic write: .tmp → rename."""
        path = self._dir / session_filename(session.start_time)
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

    def load(self, session_id: str) -> SessionData | None:
        """Scan files to find matching session ID."""
        for path in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("id") == session_id:
                    return SessionData.from_dict(data)
            except Exception:
                logger.warning("Failed to read session file %s", path, exc_info=True)
        return None

    def list_sessions(self) -> list[SessionSummary]:
        """List all sessions, most recent first (sorted by filename)."""
        results: list[SessionSummary] = []
        for path in sorted(self._dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                results.append(
                    SessionSummary(
                        id=data["id"],
                        start_time=datetime.fromisoformat(data["start_time"]),
                        message_count=len(data.get("messages", [])),
                    )
                )
            except Exception:
                logger.warning("Failed to read session file %s", path, exc_info=True)
        return results

    def delete(self, session_id: str) -> None:
        """Delete session file by scanning for matching ID."""
        for path in self._dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("id") == session_id:
                    path.unlink()
                    return
            except Exception:
                logger.warning("Failed to read session file %s", path, exc_info=True)

    def find_latest(self) -> SessionData | None:
        """Load the most recent session (by filename = timestamp)."""
        files = sorted(self._dir.glob("*.json"), reverse=True)
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return SessionData.from_dict(data)
            except Exception:
                logger.warning("Failed to read session file %s", path, exc_info=True)
        return None
