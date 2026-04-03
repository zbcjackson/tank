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
    from ..pipeline.bus import Bus, BusMessage

logger = logging.getLogger(__name__)


class AuditLogger:
    """Logs policy decisions to a JSONL file via Bus subscription.

    Each line is a JSON object with:
    - ``timestamp`` (ISO 8601 UTC)
    - ``category`` (``"file"`` or ``"network"``)
    - ``operation`` / ``host``
    - ``level`` (``"allow"`` / ``"require_approval"`` / ``"deny"``)
    - ``reason`` (policy reason string)

    Call ``subscribe(bus)`` to wire up — the logger then receives all
    ``file_access_decision`` and ``network_access_decision`` messages
    automatically.
    """

    def __init__(
        self,
        log_path: str = "~/.tank/audit.jsonl",
        enabled: bool = True,
    ) -> None:
        self._enabled = enabled
        self._log_path = Path(log_path).expanduser() if enabled else None

    def subscribe(self, bus: Bus) -> None:
        """Subscribe to policy decision messages on the Bus."""
        if not self._enabled:
            return
        bus.subscribe("file_access_decision", self._on_file_decision)
        bus.subscribe("network_access_decision", self._on_network_decision)

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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_line(self, entry: dict) -> None:
        if not self._enabled or self._log_path is None:
            return
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("Audit log write failed", exc_info=True)

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
