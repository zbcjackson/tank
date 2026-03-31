"""Backup manager — snapshot files before modification."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class BackupManager:
    """Snapshots files before write/delete operations.

    Backups are stored under a timestamped directory:
    ``~/.tank/backups/2026-03-31T14:22:01/Users/alice/projects/app.py``
    """

    def __init__(
        self,
        backup_dir: str = "~/.tank/backups",
        max_age_days: int = 30,
        enabled: bool = True,
    ) -> None:
        self._backup_dir = Path(backup_dir).expanduser()
        self._max_age_days = max_age_days
        self._enabled = enabled

    async def snapshot(self, path: str) -> str | None:
        """Backup a file before modification.

        Returns:
            The backup file path, or ``None`` if backup was skipped.
        """
        if not self._enabled:
            return None

        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return None  # New file — nothing to back up

        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        # Strip leading / to create relative path under backup dir
        relative = str(resolved).lstrip("/")
        backup_path = self._backup_dir / timestamp / relative

        try:
            await asyncio.to_thread(self._do_copy, resolved, backup_path)
            logger.info("Backed up %s → %s", resolved, backup_path)
        except Exception:
            logger.warning("Backup failed for %s", resolved, exc_info=True)
            return None

        # Best-effort cleanup of old backups
        try:
            self._cleanup_old_backups()
        except Exception:
            logger.debug("Backup cleanup failed", exc_info=True)

        return str(backup_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _do_copy(src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def _cleanup_old_backups(self) -> None:
        """Remove backup directories older than ``max_age_days``."""
        if not self._backup_dir.exists():
            return

        cutoff = datetime.now() - timedelta(days=self._max_age_days)

        for entry in os.scandir(self._backup_dir):
            if not entry.is_dir():
                continue
            try:
                dir_time = datetime.strptime(entry.name, "%Y-%m-%dT%H-%M-%S")
                if dir_time < cutoff:
                    shutil.rmtree(entry.path)
                    logger.debug("Removed old backup: %s", entry.name)
            except ValueError:
                # Directory name doesn't match timestamp format — skip
                pass

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def from_dict(data: dict) -> BackupManager:
        """Create from parsed YAML ``backup:`` section."""
        if not data:
            return BackupManager()
        return BackupManager(
            backup_dir=data.get("path", "~/.tank/backups"),
            max_age_days=data.get("max_age_days", 30),
            enabled=data.get("enabled", True),
        )
