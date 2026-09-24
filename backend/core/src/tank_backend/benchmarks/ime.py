"""Pin benchmark input sources through a bounded, main-thread native helper.

Carbon can abort the process on a queue assertion. Keep all native input-source
operations out of the benchmark process so its desktop restoration still runs.
The helper's exit status is checked; SIGTRAP cannot bypass the caller's finally.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
_REPIN_AFTER_LAUNCH_S = 0.8
_HELPER = Path(__file__).with_name("_ime_native.py")
_HELPER_TIMEOUT_S = 5.0
_saved_source_id: str | None = None


def _request(operation: str, source_id: str | None = None) -> str | None:
    if sys.platform != "darwin":
        return None
    request = {"operation": operation}
    if source_id is not None:
        request["source_id"] = source_id
    try:
        result = subprocess.run(
            [sys.executable, str(_HELPER)], input=json.dumps(request),
            capture_output=True, text=True, timeout=_HELPER_TIMEOUT_S, check=False,
        )
        if result.returncode != 0:
            logger.warning("IME %s helper exited %d", operation, result.returncode)
            return None
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            return None
        actual = payload.get("source_id")
        if not isinstance(actual, str) or not actual:
            return None
        return actual
    except (OSError, subprocess.TimeoutExpired, ValueError):
        logger.warning("IME %s helper failed", operation, exc_info=True)
        return None


def pin_ascii_input_source() -> bool:
    """Best-effort English pin; helper failure never kills the trial process."""
    actual = _request("pin")
    if actual is None:
        return False
    if "keylayout" not in actual:
        logger.warning("IME pin reported success but source is %s", actual)
    else:
        logger.info("IME pinned; active source: %s", actual)
    return True


def save_current_input_source() -> bool:
    """Keep the original serializable ID until restoration succeeds."""
    global _saved_source_id
    if sys.platform != "darwin":
        return False
    if _saved_source_id is None:
        _saved_source_id = _request("current")
    return _saved_source_id is not None


def restore_saved_input_source() -> bool:
    """Retain the baseline on helper failure so recovery can be retried."""
    global _saved_source_id
    if sys.platform != "darwin" or _saved_source_id is None:
        return False
    if _request("restore", _saved_source_id) != _saved_source_id:
        return False
    _saved_source_id = None
    return True
