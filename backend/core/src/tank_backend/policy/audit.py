"""Audit logger — structured append-only log for file and network operations."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditLogger:
    """Logs file/network operations to a JSONL file.

    Each line is a JSON object with:
    - ``timestamp`` (ISO 8601 UTC)
    - ``category`` (``"file"`` or ``"network"``)
    - ``operation`` (``"read"`` / ``"write"`` / ``"delete"`` / ``"connect"``)
    - ``target`` (file path or hostname)
    - ``decision`` (``"allow"`` / ``"require_approval"`` / ``"deny"``)
    - ``reason`` (policy reason string)
    - ``user`` (optional speaker/session identifier)
    """

    def __init__(
        self,
        log_path: str = "~/.tank/audit.jsonl",
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._log_path = Path(log_path).expanduser() if enabled else None

    async def log_file_op(
        self,
        operation: str,
        path: str,
        decision: str,
        reason: str,
        user: str = "",
    ) -> None:
        """Log a file operation (read/write/delete)."""
        if not self._enabled:
            return
        await self._append({
            "category": "file",
            "operation": operation,
            "target": path,
            "decision": decision,
            "reason": reason,
            "user": user,
        })

    async def log_network_op(
        self,
        host: str,
        decision: str,
        reason: str,
    ) -> None:
        """Log a network access decision."""
        if not self._enabled:
            return
        await self._append({
            "category": "network",
            "operation": "connect",
            "target": host,
            "decision": decision,
            "reason": reason,
        })

    async def _append(self, entry: dict) -> None:
        """Append a single JSON line to the audit log."""
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            await asyncio.to_thread(self._write_line, entry)
        except Exception:
            logger.debug("Audit log write failed", exc_info=True)

    def _write_line(self, entry: dict) -> None:
        assert self._log_path is not None
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def from_dict(data: dict) -> AuditLogger:
        """Create from parsed YAML ``audit:`` section."""
        if not data:
            return AuditLogger(enabled=False)
        return AuditLogger(
            log_path=data.get("log_path", "~/.tank/audit.jsonl"),
            enabled=data.get("enabled", True),
        )
