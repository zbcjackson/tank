"""Pin the macOS input source to an ASCII layout for benchmark trials.

The computer-use agent types via the frontmost app's CURRENT input
source — with a Chinese IME active, ASCII punctuation like ``-`` and
``.`` gets eaten or converted (observed: ``~/bench-work/terminal.txt``
typed as ``~/benchwork/terminaltxt``). Input-source stickiness is
per-app, so pinning once at suite start doesn't cover apps launched
later; we pin before every trial and restore the user's source at the
end of the run.
"""

from __future__ import annotations

import importlib
import logging
import sys

logger = logging.getLogger(__name__)

_US_LAYOUT = "com.apple.keylayout.US"


def _select_input_source(source_id: str) -> bool:
    """Select a keyboard input source by ID via the Carbon TIS API."""
    Quartz = importlib.import_module("Quartz")  # pyobjc (macOS only)
    props = {Quartz.kTISPropertyInputSourceID: source_id}
    sources = Quartz.TISCreateInputSourceList(props, False) or []
    if not sources:
        return False
    return bool(Quartz.TISSelectInputSource(sources[0]))


def current_input_source_id() -> str | None:
    """ID of the currently selected input source (macOS only)."""
    if sys.platform != "darwin":
        return None
    try:
        Quartz = importlib.import_module("Quartz")
        src = Quartz.TISCopyCurrentKeyboardInputSource()
        return str(Quartz.TISGetInputSourceProperty(src, Quartz.kTISPropertyInputSourceID))
    except Exception:  # noqa: BLE001 — pinning is best-effort
        logger.warning("could not read current input source", exc_info=True)
        return None


def pin_ascii_input_source() -> bool:
    """Switch the keyboard to the U.S. layout (no-op off macOS).

    Returns True when the pin succeeded. Best-effort: a failure logs a
    warning and the trial proceeds — typing fidelity may degrade, which
    the trace will show.
    """
    if sys.platform != "darwin":
        return False
    try:
        return _select_input_source(_US_LAYOUT)
    except Exception:  # noqa: BLE001 — pinning is best-effort
        logger.warning("could not pin ASCII input source", exc_info=True)
        return False


def restore_input_source(source_id: str | None) -> bool:
    """Restore a previously captured input source (best-effort)."""
    if sys.platform != "darwin" or not source_id:
        return False
    try:
        return _select_input_source(source_id)
    except Exception:  # noqa: BLE001
        logger.warning("could not restore input source %s", source_id, exc_info=True)
        return False
