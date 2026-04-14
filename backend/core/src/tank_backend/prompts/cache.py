"""FileCache — mtime_ns + size content cache for prompt files."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

NEGATIVE_CACHE_TTL_S = 30.0  # Re-check missing files every 30s


@dataclass(frozen=True)
class _CacheEntry:
    content: str
    mtime_ns: int
    size: int


class FileCache:
    """Read-through cache for text files, invalidated by mtime_ns + size."""

    def __init__(self) -> None:
        self._positive: dict[str, _CacheEntry] = {}
        self._negative: dict[str, float] = {}  # resolved_path → monotonic timestamp

    def read(self, path: str | Path) -> str | None:
        """Read file content, returning cached version if still valid.

        Returns ``None`` if the file does not exist or cannot be read.
        """
        resolved = str(Path(path).expanduser().resolve())

        # Check positive cache
        entry = self._positive.get(resolved)
        if entry is not None:
            try:
                st = os.stat(resolved)
                if st.st_mtime_ns == entry.mtime_ns and st.st_size == entry.size:
                    return entry.content
            except FileNotFoundError:
                del self._positive[resolved]
                self._negative[resolved] = time.monotonic()
                return None

        # Check negative cache
        neg_ts = self._negative.get(resolved)
        if neg_ts is not None:
            if time.monotonic() - neg_ts < NEGATIVE_CACHE_TTL_S:
                return None
            del self._negative[resolved]

        # Read from disk
        try:
            st = os.stat(resolved)
            content = Path(resolved).read_text(encoding="utf-8")
            self._positive[resolved] = _CacheEntry(
                content=content,
                mtime_ns=st.st_mtime_ns,
                size=st.st_size,
            )
            logger.debug("Cache loaded: %s (%d bytes)", resolved, st.st_size)
            return content
        except FileNotFoundError:
            self._negative[resolved] = time.monotonic()
            return None
        except Exception:
            logger.warning("Failed to read %s", resolved, exc_info=True)
            return None

    def invalidate(self, path: str | Path | None = None) -> None:
        """Force re-read on next access.  ``None`` clears everything."""
        if path is None:
            self._positive.clear()
            self._negative.clear()
            return
        resolved = str(Path(path).expanduser().resolve())
        self._positive.pop(resolved, None)
        self._negative.pop(resolved, None)
