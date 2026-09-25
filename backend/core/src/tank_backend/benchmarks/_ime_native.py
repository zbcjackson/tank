"""Private main-thread Carbon helper for benchmarks.ime and the
tools.computer_use_macos ASCII-input-source query.

A native SIGTRAP here must not terminate the benchmark's desktop cleanup owner.
The wire format uses input-source IDs, never process-local CF pointers.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import json
import logging
import sys

logger = logging.getLogger(__name__)
_carbon: ctypes.CDLL | None = None
_core_foundation: ctypes.CDLL | None = None

def _load_frameworks() -> tuple[ctypes.CDLL, ctypes.CDLL] | None:
    global _carbon, _core_foundation
    if sys.platform != "darwin":
        return None
    try:
        if _carbon is None:
            carbon_path = ctypes.util.find_library("Carbon")
            cf_path = ctypes.util.find_library("CoreFoundation")
            if carbon_path is None or cf_path is None:
                return None
            _carbon = ctypes.cdll.LoadLibrary(carbon_path)
            _core_foundation = ctypes.cdll.LoadLibrary(cf_path)
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


def _current_source_id(carbon: ctypes.CDLL, cf: ctypes.CDLL) -> str | None:
    """ID of the currently selected input source, or None if unreadable."""
    try:
        prop = ctypes.c_void_p.in_dll(carbon, "kTISPropertyInputSourceID")
        carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
        carbon.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        carbon.TISCopyCurrentKeyboardInputSource.restype = ctypes.c_void_p
        carbon.TISCopyCurrentKeyboardInputSource.argtypes = []
        source = carbon.TISCopyCurrentKeyboardInputSource()
        if not source:
            return None
        try:
            cfstr = carbon.TISGetInputSourceProperty(ctypes.c_void_p(source), prop)
            if not cfstr:
                return None
            k_cf_utf8 = 0x08000100
            cf.CFStringGetCStringPtr.restype = ctypes.c_char_p
            cf.CFStringGetCStringPtr.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            direct = cf.CFStringGetCStringPtr(ctypes.c_void_p(cfstr), k_cf_utf8)
            if direct:
                return direct.decode()
            cf.CFStringGetCString.restype = ctypes.c_bool
            cf.CFStringGetCString.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32,
            ]
            buf = ctypes.create_string_buffer(256)
            if cf.CFStringGetCString(ctypes.c_void_p(cfstr), buf, 256, k_cf_utf8):
                return buf.value.decode()
        finally:
            _cf_release(int(source), cf)
    except Exception:  # noqa: BLE001 — readback is diagnostics only
        return None
    return None


def _restore_source(source_id: str, carbon: ctypes.CDLL, cf: ctypes.CDLL) -> bool:
    carbon.TISCreateInputSourceList.restype = ctypes.c_void_p
    carbon.TISCreateInputSourceList.argtypes = [ctypes.c_void_p, ctypes.c_bool]
    sources = carbon.TISCreateInputSourceList(None, False)
    if not sources:
        return False
    try:
        cf.CFArrayGetCount.restype = ctypes.c_long
        cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
        prop = ctypes.c_void_p.in_dll(carbon, "kTISPropertyInputSourceID")
        carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
        carbon.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFEqual.restype = ctypes.c_bool
        cf.CFEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        wanted = _cf_string(source_id, cf)
        try:
            for index in range(cf.CFArrayGetCount(sources)):
                source = cf.CFArrayGetValueAtIndex(sources, index)
                identifier = carbon.TISGetInputSourceProperty(source, prop)
                if identifier and cf.CFEqual(identifier, wanted):
                    carbon.TISSelectInputSource.restype = ctypes.c_int
                    carbon.TISSelectInputSource.argtypes = [ctypes.c_void_p]
                    return carbon.TISSelectInputSource(source) == 0
        finally:
            _cf_release(wanted, cf)
        return False
    finally:
        _cf_release(int(sources), cf)


def _ascii_capable(carbon: ctypes.CDLL, cf: ctypes.CDLL) -> bool:
    """Whether the current keyboard input source can type ASCII."""
    try:
        carbon.TISCopyCurrentKeyboardInputSource.restype = ctypes.c_void_p
        carbon.TISCopyCurrentKeyboardInputSource.argtypes = []
        source = carbon.TISCopyCurrentKeyboardInputSource()
        if not source:
            return False
        carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
        carbon.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cf.CFBooleanGetValue.restype = ctypes.c_bool
        cf.CFBooleanGetValue.argtypes = [ctypes.c_void_p]
        key = ctypes.c_void_p.in_dll(carbon, "kTISPropertyInputSourceIsASCIICapable")
        value = carbon.TISGetInputSourceProperty(source, key)
        return bool(value and cf.CFBooleanGetValue(value))
    finally:
        if source:
            _cf_release(int(source), cf)


def main() -> None:
    request = json.load(sys.stdin)
    frameworks = _load_frameworks()
    if frameworks is None:
        print(json.dumps({"ok": False, "source_id": None, "ascii": False}))
        return
    carbon, cf = frameworks
    operation = request["operation"]
    if operation == "current":
        ok = True
    elif operation == "pin":
        ok = _select_english_source()
    elif operation == "restore":
        ok = _restore_source(request["source_id"], carbon, cf)
    elif operation == "ascii":
        # Used by the production type_text auto mode: the same TIS query, kept
        # on this helper's main thread so a queue assertion cannot kill the
        # caller. `ok` reflects a successful read; `ascii` is the answer.
        ascii_capable = _ascii_capable(carbon, cf)
        print(json.dumps({"ok": True, "ascii": ascii_capable}))
        return
    else:
        raise ValueError("unsupported IME operation")
    actual = _current_source_id(carbon, cf)
    if operation == "restore":
        ok = ok and actual == request["source_id"]
    print(json.dumps({"ok": bool(ok and actual), "source_id": actual}))


if __name__ == "__main__":
    main()
