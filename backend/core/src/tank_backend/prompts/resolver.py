"""AgentsFileResolver — discovers AGENTS.md files for workspace paths."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..pipeline.bus import BusMessage

logger = logging.getLogger(__name__)

AGENTS_FILENAME = "AGENTS.md"


class AgentsFileResolver:
    """Discovers AGENTS.md files by walking ancestor directories.

    Subscribes to ``file_access_decision`` Bus messages to lazily discover
    workspace rules when tools access paths.
    """

    def __init__(self, bus: Any = None) -> None:
        # dir_path → list of AGENTS.md absolute paths (root-first)
        self._chain_cache: dict[str, list[str]] = {}
        # All discovered AGENTS.md absolute paths
        self._discovered: set[str] = set()
        # Flag: new AGENTS.md found since last reset
        self._new_discovery = False

        if bus is not None:
            bus.subscribe("file_access_decision", self._on_file_access)

    @property
    def has_new_discovery(self) -> bool:
        """True when a previously-unseen AGENTS.md was found since last reset."""
        return self._new_discovery

    def reset_discovery_flag(self) -> None:
        """Clear the new-discovery flag (called after prompt rebuild)."""
        self._new_discovery = False

    @property
    def all_discovered(self) -> frozenset[str]:
        """All AGENTS.md absolute paths discovered so far."""
        return frozenset(self._discovered)

    def resolve_chain(self, path: str) -> list[str]:
        """Return ordered list of AGENTS.md paths from root to leaf for *path*.

        Walks from the given path (or its parent if it's a file) upward to
        the filesystem root, collecting every ``AGENTS.md`` found.
        Returns root-first order (general → specific).
        """
        p = Path(path).expanduser().resolve()
        if p.is_file():
            p = p.parent
        dir_key = str(p)

        cached = self._chain_cache.get(dir_key)
        if cached is not None:
            return list(cached)

        chain: list[str] = []
        current = p
        while True:
            candidate = current / AGENTS_FILENAME
            if candidate.is_file():
                chain.append(str(candidate))
            parent = current.parent
            if parent == current:
                break
            current = parent

        # Reverse so root comes first
        chain.reverse()
        self._chain_cache[dir_key] = chain

        # Track new discoveries
        for agents_path in chain:
            if agents_path not in self._discovered:
                self._discovered.add(agents_path)
                self._new_discovery = True
                logger.info("Discovered workspace AGENTS.md: %s", agents_path)

        return list(chain)

    def _on_file_access(self, message: BusMessage) -> None:
        """Handle ``file_access_decision`` Bus messages — discover AGENTS.md lazily."""
        payload = message.payload
        if not isinstance(payload, dict):
            return
        accessed_path = payload.get("path")
        if not accessed_path:
            return
        # Only trigger discovery for allowed accesses (not denials)
        level = payload.get("level", "")
        if level == "deny":
            return
        self.resolve_chain(accessed_path)

    def invalidate_cache(self) -> None:
        """Clear the chain cache (e.g., when AGENTS.md files change on disk)."""
        self._chain_cache.clear()
