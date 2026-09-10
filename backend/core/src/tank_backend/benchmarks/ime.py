"""Pin the macOS input source to an ASCII layout for benchmark trials.

The computer-use agent types via the frontmost app's CURRENT input
source — with a Chinese IME active, ASCII punctuation like ``-`` and
``.`` gets eaten or converted (observed: ``~/bench-work/terminal.txt``
typed as ``~/benchwork/terminaltxt``). Input-source stickiness is
per-app, so we pin before every trial AND re-pin after each app launch
(the driver wraps launch_app), then restore the user's source at the
end of the run.

Implementation note: the TIS API lives in Carbon/HIToolbox and is NOT
reliably exposed through pyobjc's ``Quartz`` umbrella, so this talks
to the Carbon framework directly via ctypes.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import sys

logger = logging.getLogger(__name__)

_REPIN_AFTER_LAUNCH_S = 0.8

_carbon: ctypes.CDLL | None = None
_core_foundation: ctypes.CDLL | None = None

# Handle to the input source captured before the run (CF object we own
# under the Create rule; released after restore).
_saved_source: int | None = None


def _load_frameworks() -> tuple[ctypes.CDLL, ctypes.CDLL] | None:
    global _carbon, _core_foundation
    if sys.platform != "darwin":
        return None
    try:
        if _carbon is None:
            _carbon = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Carbon"))
            _core_foundation = ctypes.cdll.LoadLibrary(
                ctypes.util.find_library("CoreFoundation")
            )
        assert _core_foundation is not None
        return _carbon, _core_foundation
    except OSError:
        logger.warning("could not load Carbon/CoreFoundation for IME pinning")
        return None


def _cf_string(text: str, cf: ctypes.CDLL) -> int:
    """Create a CFString (caller owns; release with _cf_release)."""
    k_cf_string_encoding_utf8 = 0x08000100
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32,
    ]
    ref = cf.CFStringCreateWithCString(None, text.encode(), k_cf_string_encoding_utf8)
    return int(ref)


def _cf_release(handle: int, cf: ctypes.CDLL) -> None:
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cf.CFRelease(ctypes.c_void_p(handle))


def _select_english_source() -> bool:
    """Switch the current context to its English input source."""
    frameworks = _load_frameworks()
    if frameworks is None:
        return False
    carbon, cf = frameworks
    lang = _cf_string("en", cf)
    try:
        carbon.TISCopyInputSourceForLanguage.restype = ctypes.c_void_p
        carbon.TISCopyInputSourceForLanguage.argtypes = [ctypes.c_void_p]
        carbon.TISSelectInputSource.restype = ctypes.c_int
        carbon.TISSelectInputSource.argtypes = [ctypes.c_void_p]
        source = carbon.TISCopyInputSourceForLanguage(ctypes.c_void_p(lang))
        if not source:
            logger.warning("no English input source available to pin")
            return False
        try:
            status = carbon.TISSelectInputSource(ctypes.c_void_p(source))
            if status != 0:
                logger.warning("TISSelectInputSource failed: OSStatus %s", status)
                return False
            return True
        finally:
            _cf_release(int(source), cf)
    finally:
        _cf_release(lang, cf)


def pin_ascii_input_source() -> bool:
    """Switch the keyboard to an English/ASCII layout (no-op off macOS).

    Best-effort: failures log a warning and the trial proceeds — typing
    fidelity may degrade, which the trace will show.
    """
    if sys.platform != "darwin":
        return False
    try:
        return _select_english_source()
    except Exception:  # noqa: BLE001 — pinning must never kill a trial
        logger.warning("could not pin ASCII input source", exc_info=True)
        return False


def save_current_input_source() -> bool:
    """Capture the current input source for later restore (macOS only)."""
    global _saved_source
    if sys.platform != "darwin":
        return False
    frameworks = _load_frameworks()
    if frameworks is None:
        return False
    carbon, cf = frameworks
    carbon.TISCopyCurrentKeyboardInputSource.restype = ctypes.c_void_p
    carbon.TISCopyCurrentKeyboardInputSource.argtypes = []
    source = carbon.TISCopyCurrentKeyboardInputSource()
    if not source:
        return False
    _saved_source = int(source)  # Create rule: we own this reference
    return True


def restore_saved_input_source() -> bool:
    """Restore the source captured by save_current_input_source()."""
    global _saved_source
    if sys.platform != "darwin" or _saved_source is None:
        return False
    frameworks = _load_frameworks()
    if frameworks is None:
        return False
    carbon, cf = frameworks
    carbon.TISSelectInputSource.restype = ctypes.c_int
    carbon.TISSelectInputSource.argtypes = [ctypes.c_void_p]
    status = carbon.TISSelectInputSource(ctypes.c_void_p(_saved_source))
    _cf_release(_saved_source, cf)
    _saved_source = None
    return status == 0
