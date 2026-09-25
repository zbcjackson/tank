"""M7 batch 2: measure real AX candidate coverage for benchmark apps.

Read-only enumeration plus brief app launch/quit of apps we start ourselves.
No model requests, no screenshot upload, no pointer/keyboard input.

Apps already running (Chromium browsers, Finder) are only enumerated in their
current windows and never quit or repositioned. Results are written after each
app so a cleanup hiccup cannot lose collected evidence. Graceful quit falls
back to killall only for apps this script launched (TextEdit needs Cmd+W
first; its AppleEvents are intermittently unresponsive).
"""

from __future__ import annotations

import json
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

import AppKit

from tank_backend.tools import computer_ax
from tank_backend.tools import computer_use_macos as macos
from tank_backend.tools.computer_frame import _geometry

OUT = Path(__file__).parent
RESULT_PATH = OUT / "enumeration.json"

LAUNCH_APPS = ["Calculator", "TextEdit", "Terminal", "System Settings", "Safari"]
# Running apps whose layer-0 windows are enumerated without launch.
OBSERVE_ONLY_OWNERS = {"Arc", "Poe", "Finder"}


def frontmost() -> AppKit.NSRunningApplication:
    return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()


def onscreen_windows() -> list[dict[str, Any]]:
    quartz = macos._load_quartz()
    return list(quartz.CGWindowListCopyWindowInfo(
        quartz.kCGWindowListOptionOnScreenOnly, 0) or [])


def wait_window(owner: str, timeout: float = 12.0) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for window in onscreen_windows():
            if window.get("kCGWindowOwnerName") == owner and window.get("kCGWindowLayer") == 0:
                size = window["kCGWindowBounds"]
                if int(size["Width"]) > 50 and int(size["Height"]) > 50:
                    return dict(window)
        time.sleep(0.3)
    return None


def running_pids() -> dict[str, int]:
    apps: dict[str, int] = {}
    for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
        if app.localizedName():
            apps[app.localizedName()] = app.processIdentifier()
    return apps


def running(name: str) -> bool:
    return any(a.localizedName() == name for a in
               AppKit.NSWorkspace.sharedWorkspace().runningApplications())


def stop_app(name: str) -> list[str]:
    """Best-effort quit for apps this script launched; returns actions taken."""
    actions: list[str] = []
    if not running(name):
        return actions
    if name == "TextEdit":
        # Untitled window: Cmd+W closes without a save dialog.
        subprocess.run(
            ["osascript", "-e", f'tell application "{name}" to activate',
             "-e", "delay 0.4",
             "-e", 'tell application "System Events" to keystroke "w" using command down'],
            capture_output=True, timeout=30)
        time.sleep(1.0)
        actions.append("cmd+w")
    try:
        subprocess.run(["osascript", "-e", f'tell application "{name}" to quit'],
                       capture_output=True, timeout=8)
        time.sleep(1.0)
        if running(name):
            actions.append("quit-returned-but-still-running")
        else:
            actions.append("quit")
            return actions
    except subprocess.TimeoutExpired:
        actions.append("quit-timeout")
    subprocess.run(["killall", name], capture_output=True, timeout=10)
    time.sleep(0.8)
    actions.append(f"killall:{'still' if running(name) else 'gone'}")
    return actions


def summarize(window: dict[str, Any], owner_was_running_before: bool) -> dict[str, Any]:
    wid = int(window["kCGWindowNumber"])
    rect = window["kCGWindowBounds"]
    geometry = _geometry()
    started = time.monotonic()
    try:
        candidates, truncated = computer_ax.ax_window_candidates(wid, geometry)
        error = None
    except (RuntimeError, ValueError) as exc:
        candidates, truncated, error = [], False, str(exc)
    elapsed = round(time.monotonic() - started, 3)
    titles = Counter(c.title for c in candidates if c.title)
    roles = Counter(c.role for c in candidates)
    framed = sum(1 for c in candidates if c.frame is not None)
    pressable = sum(1 for c in candidates if "AXPress" in c.actions)
    same_name = {title: count for title, count in titles.items() if count > 1}
    return {
        "window_id": wid,
        "owner": window.get("kCGWindowOwnerName"),
        "owner_pid": int(window["kCGWindowOwnerPID"]),
        "owner_was_running_before": owner_was_running_before,
        "bounds": [int(rect[k]) for k in ("X", "Y", "Width", "Height")],
        "enumeration_seconds": elapsed,
        "candidate_count": len(candidates),
        "truncated": truncated,
        "enumeration_error": error,
        "same_title_groups": same_name,
        "roles": dict(roles.most_common()),
        "with_frame": framed,
        "pressable": pressable,
        "listing_head": computer_ax.format_candidates(candidates).splitlines()[:12],
    }


def save(results: list[dict[str, Any]]) -> None:
    RESULT_PATH.write_text(
        json.dumps({"started_at": time.time(), "apps": results},
                   ensure_ascii=False, indent=2))


def main() -> None:
    results: list[dict[str, Any]] = []
    original = frontmost()
    was_running = running_pids()
    try:
        for name in LAUNCH_APPS:
            launched = name not in was_running
            subprocess.run(["open", "-a", name], capture_output=True, timeout=30)
            window = wait_window(name)
            entry: dict[str, Any] = {"app": name, "launched_by_us": launched}
            if window is None:
                entry["error"] = "no on-screen window appeared"
            else:
                entry.update(summarize(window, not launched))
            results.append(entry)
            save(results)
            if launched:
                entry["cleanup"] = stop_app(name)
                save(results)
        for window in onscreen_windows():
            owner = window.get("kCGWindowOwnerName")
            if owner in OBSERVE_ONLY_OWNERS and window.get("kCGWindowLayer") == 0:
                size = window["kCGWindowBounds"]
                if int(size["Width"]) > 50 and int(size["Height"]) > 50:
                    results.append({
                        "app": owner, "launched_by_us": False,
                        **summarize(window, True),
                    })
                    save(results)
    finally:
        original.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.3)
        save(results)
    for entry in results:
        print(json.dumps({k: entry.get(k) for k in (
            "app", "launched_by_us", "candidate_count", "truncated",
            "enumeration_error", "same_title_groups", "pressable", "with_frame",
            "enumeration_seconds", "cleanup")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
