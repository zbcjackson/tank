"""Audit logger — structured append-only log for file and network operations.

Subscribes to policy decision messages on the Bus and writes them to a JSONL file.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config.models import AuditConfig
    from ..pipeline.bus import Bus, BusMessage

logger = logging.getLogger(__name__)


class AuditLogger:
    """Logs policy decisions to a JSONL file via Bus subscription.

    Each line is a JSON object with:
    - ``timestamp`` (ISO 8601 UTC)
    - ``category`` (``"file"`` / ``"network"`` / ``"connector"``)
    - ``operation`` / ``target``
    - ``decision`` (``"allow"`` / ``"require_approval"`` / ``"deny"``)
    - ``reason`` (policy reason string)

    Call ``subscribe(bus)`` to wire up — the logger then receives
    ``file_access_decision``, ``network_access_decision``, and
    ``connector_access_decision`` messages automatically.
    """

    def __init__(self, config: AuditConfig) -> None:
        self._enabled = config.enabled
        self._log_path = Path(config.log_path).expanduser() if config.enabled else None
        # Size-based rotation: when the live log reaches ``max_bytes``,
        # we rename ``.jsonl`` → ``.jsonl.1`` (shifting older backups up
        # by one) before the next write. ``max_bytes=0`` preserves the
        # pre-Phase-8 unbounded behaviour.
        self._max_bytes = config.max_bytes
        self._backup_count = max(0, config.backup_count)

    def subscribe(self, bus: Bus) -> None:
        """Subscribe to policy decision messages on the Bus."""
        if not self._enabled:
            return
        bus.subscribe("file_access_decision", self._on_file_decision)
        bus.subscribe("network_access_decision", self._on_network_decision)
        bus.subscribe("connector_access_decision", self._on_connector_decision)

    # ------------------------------------------------------------------
    # Bus handlers (sync — called from Bus.poll())
    # ------------------------------------------------------------------

    def _on_file_decision(self, message: BusMessage) -> None:
        payload = message.payload
        self._write_line({
            "category": "file",
            "operation": payload.get("operation", ""),
            "target": payload.get("path", ""),
            "decision": payload.get("level", ""),
            "reason": payload.get("reason", ""),
        })

    def _on_network_decision(self, message: BusMessage) -> None:
        payload = message.payload
        self._write_line({
            "category": "network",
            "operation": "connect",
            "target": payload.get("host", ""),
            "decision": payload.get("level", ""),
            "reason": payload.get("reason", ""),
        })

    def _on_connector_decision(self, message: BusMessage) -> None:
        """Record a connector allowlist decision.

        :class:`ConnectorAllowlistPolicy` posts messages with a
        :class:`PolicyVerdict` in ``payload["verdict"]`` — different
        shape from the flat dicts file/network policies post. Unpack
        here to keep the audit log's flat schema consistent.
        """
        verdict = message.payload.get("verdict")
        if verdict is None:
            return
        ctx = getattr(verdict, "context", {}) or {}
        self._write_line({
            "category": "connector",
            "operation": "inbound",
            "target": ctx.get("external_id", ""),
            "decision": verdict.level.value,
            "reason": verdict.reason,
            "connector": ctx.get("connector", ""),
            "platform": ctx.get("platform", ""),
            "display_name": ctx.get("display_name", ""),
            "matched_pattern": ctx.get("matched_pattern"),
        })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_line(self, entry: dict) -> None:
        if not self._enabled or self._log_path is None:
            return
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._maybe_rotate()
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("Audit log write failed", exc_info=True)

    def _maybe_rotate(self) -> None:
        """Rotate the log file if ``max_bytes`` is set and exceeded.

        Rotation shifts existing backups up by one (``.jsonl.1`` →
        ``.jsonl.2``, …) and drops anything past ``backup_count``, then
        moves the live log to ``.jsonl.1``. Called from :meth:`_write_line`
        before each append, so the next write starts a fresh live file.

        Thread-safe assumption: Bus dispatch is single-threaded
        (``Bus.poll()`` runs on the app thread), so concurrent
        ``_write_line`` calls don't exist in practice. External
        tail/truncate processes can still race with us — rotation is
        best-effort, not exclusive.
        """
        if self._log_path is None or self._max_bytes <= 0:
            return
        try:
            size = self._log_path.stat().st_size
        except FileNotFoundError:
            return
        except OSError:
            logger.debug("Audit log stat failed; skipping rotation", exc_info=True)
            return
        if size < self._max_bytes:
            return

        # Shift backups up by one, working from the oldest so nothing
        # clobbers a younger backup.
        for i in range(self._backup_count - 1, 0, -1):
            src = self._log_path.with_suffix(f".jsonl.{i}")
            dst = self._log_path.with_suffix(f".jsonl.{i + 1}")
            if src.exists():
                try:
                    src.replace(dst)
                except OSError:
                    logger.debug(
                        "Audit log rotation: rename %s → %s failed",
                        src, dst, exc_info=True,
                    )
                    return

        # Move the live log to ``.jsonl.1``. If backup_count is 0, just
        # truncate by unlinking (no backups retained).
        first_backup = self._log_path.with_suffix(".jsonl.1")
        try:
            if self._backup_count == 0:
                self._log_path.unlink()
            else:
                self._log_path.replace(first_backup)
        except OSError:
            logger.debug(
                "Audit log rotation: live rename failed", exc_info=True,
            )
