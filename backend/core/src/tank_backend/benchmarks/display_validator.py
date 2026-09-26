"""Multi-display benchmark validator: a window must sit on a non-main display.

Complements ``calc_validator`` for the multi-display task: strict scoring
needs both the business result (7×8=56 on Calculator) AND proof that the
window actually lives on a secondary display — otherwise a task solved
entirely on the main display would pass without exercising cross-display
coordinates.

Fail-closed: unreadable topology or missing Quartz is a validation error,
never a pass. Run from the benchmark suite via a ``shell`` validator:

    python -m tank_backend.benchmarks.display_validator --calculator-on-secondary
"""

from __future__ import annotations

import sys


def _load_quartz():
    import Quartz

    return Quartz


def _active_displays(quartz) -> tuple[tuple[int, ...], ...]:
    err, ids, count = quartz.CGGetActiveDisplayList(16, None, None)
    if err or not count:
        raise RuntimeError(f"CGGetActiveDisplayList failed: err={err} count={count}")
    entries = []
    for display in tuple(ids)[: int(count)]:
        bounds = quartz.CGDisplayBounds(display)
        mode = quartz.CGDisplayCopyDisplayMode(display)
        entries.append((
            int(display),
            int(bounds[0][0]), int(bounds[0][1]),
            int(bounds[1][0]), int(bounds[1][1]),
            int(quartz.CGDisplayModeGetPixelWidth(mode)),
            int(quartz.CGDisplayModeGetPixelHeight(mode)),
        ))
    if not any((e[1], e[2]) == (0, 0) for e in entries):
        raise RuntimeError("No display at origin (0,0)")
    return tuple(sorted(entries))


def _owner_windows(quartz, owner_name: str) -> list[tuple[int, int, int, int, int]]:
    """On-screen windows of ``owner_name``: (window_id, x, y, w, h), global."""
    windows = quartz.CGWindowListCopyWindowInfo(
        quartz.kCGWindowListOptionOnScreenOnly, 0
    )
    found = []
    for window in windows or []:
        if window.get("kCGWindowOwnerName") != owner_name:
            continue
        if window.get("kCGWindowLayer", 0) != 0:
            continue  # Skip shadows/overlays.
        rect = window["kCGWindowBounds"]
        w, h = int(rect["Width"]), int(rect["Height"])
        if w <= 0 or h <= 0:
            continue
        found.append((
            int(window["kCGWindowNumber"]),
            int(rect["X"]), int(rect["Y"]), w, h,
        ))
    return found


def calculator_on_secondary() -> tuple[bool, str]:
    quartz = _load_quartz()
    displays = _active_displays(quartz)
    if len(displays) < 2:
        return False, f"only {len(displays)} display(s); task needs a secondary display"
    windows = _owner_windows(quartz, "Calculator")
    if not windows:
        return False, "no on-screen Calculator window"
    for entry in displays:
        if (entry[1], entry[2]) == (0, 0):
            continue  # Main display: not what we want.
        ox, oy, w, h = entry[1:5]
        for _window_id, x, y, win_w, win_h in windows:
            if ox <= x and oy <= y and x + win_w <= ox + w and y + win_h <= oy + h:
                return True, f"Calculator window wholly on display {entry[0]}"
    return False, "no Calculator window wholly inside a non-main display"


def main() -> int:
    if sys.platform != "darwin":
        print("display_validator: macOS only", file=sys.stderr)
        return 2
    if "--calculator-on-secondary" not in sys.argv[1:]:
        print("usage: display_validator --calculator-on-secondary", file=sys.stderr)
        return 2
    try:
        ok, detail = calculator_on_secondary()
    except Exception as e:  # fail closed on any unreadable state
        print(f"display_validator: unreadable state: {e}", file=sys.stderr)
        return 2
    print(f"display_validator: {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
