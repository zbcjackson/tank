"""Outer recovery owner for exclusive, controlled Calculator pilots.

Baseline files contain private clipboard/application state. Keep them local;
only result.json is suitable for benchmark evidence. This is not a batch runner
or model authorization mechanism. The supplied launcher retains its own gates.
"""
from __future__ import annotations

import base64
import contextlib
import importlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .desktop_cleanup import MacOSInputCleanup
from .ime import _request


def _appkit() -> Any:
    return importlib.import_module("AppKit")


def _clipboard(kit: Any) -> list[list[list[str]]]:
    return [
        [[str(kind), base64.b64encode(bytes(item.dataForType_(kind))).decode()]
         for kind in item.types() if item.dataForType_(kind) is not None]
        for item in (kit.NSPasteboard.generalPasteboard().pasteboardItems() or [])
    ]


def capture_desktop() -> dict[str, Any]:
    """Capture before the child can change anything; reject held user inputs."""
    kit = _appkit()
    quartz = importlib.import_module("Quartz")
    keys, buttons = MacOSInputCleanup._state()
    if keys or buttons:
        raise RuntimeError("Desktop inputs already held; launcher not started")
    source = _request("current")
    if source is None:
        raise RuntimeError("Cannot capture input source; launcher not started")
    workspace = kit.NSWorkspace.sharedWorkspace()
    front = workspace.frontmostApplication()
    if front is None or front.bundleIdentifier() == "com.apple.loginwindow":
        raise RuntimeError("Return to the interactive desktop before the controlled pilot")
    mouse = quartz.CGEventGetLocation(quartz.CGEventCreate(None))
    apps = [
        {"pid": int(app.processIdentifier()), "bundle": str(app.bundleIdentifier()),
         "launched": float(app.launchDate().timeIntervalSince1970()),
         "hidden": bool(app.isHidden())}
        for app in workspace.runningApplications()
        if (app.activationPolicy() == kit.NSApplicationActivationPolicyRegular
            or (front is not None and app.processIdentifier() == front.processIdentifier()))
        and app.launchDate() is not None
    ]
    # The pilot resets/quits Calculator; never destroy an existing user session.
    if any(app["bundle"] == "com.apple.calculator" for app in apps):
        raise RuntimeError("Close Calculator before the controlled pilot")
    return {"apps": apps, "front_pid": int(front.processIdentifier()) if front else None,
            "mouse": [float(mouse.x), float(mouse.y)], "clipboard": _clipboard(kit),
            "input_source": source}


def restore_desktop(saved: dict[str, Any]) -> dict[str, Any]:
    """Try every recovery stage independently and verify actual restored state."""
    kit = _appkit()
    quartz = importlib.import_module("Quartz")
    workspace = kit.NSWorkspace.sharedWorkspace()
    results: dict[str, Any] = {}

    def stage(name: str, action: Any) -> None:
        try:
            results[name] = bool(action())
        except Exception as exc:
            results[name] = False
            results[name + "_error"] = type(exc).__name__

    def inputs() -> bool:
        report = MacOSInputCleanup()._release()
        time.sleep(0.1)
        keys, buttons = MacOSInputCleanup._state()
        return not keys and not buttons and not report["errors"]

    def calculator() -> bool:
        for app in workspace.runningApplications():
            if app.bundleIdentifier() == "com.apple.calculator":
                app.terminate()
        for _ in range(20):
            if not any(a.bundleIdentifier() == "com.apple.calculator"
                       for a in workspace.runningApplications()):
                return True
            time.sleep(0.1)
        return False

    def applications() -> bool:
        ok = True
        for original in saved["apps"]:
            app = kit.NSRunningApplication.runningApplicationWithProcessIdentifier_(original["pid"])
            if (app is None or app.launchDate() is None
                    or float(app.launchDate().timeIntervalSince1970()) != original["launched"]
                    or str(app.bundleIdentifier()) != original["bundle"]):
                ok = False
                continue
            if bool(app.isHidden()) != original["hidden"]:
                app.hide() if original["hidden"] else app.unhide()
            ok = bool(app.isHidden()) == original["hidden"] and ok
        return ok

    def clipboard() -> bool:
        items = []
        for values in saved["clipboard"]:
            item = kit.NSPasteboardItem.alloc().init()
            for kind, encoded in values:
                item.setData_forType_(base64.b64decode(encoded), kind)
            items.append(item)
        board = kit.NSPasteboard.generalPasteboard()
        board.clearContents()
        if items:
            board.writeObjects_(items)
        return _clipboard(kit) == saved["clipboard"]

    def cursor() -> bool:
        quartz.CGWarpMouseCursorPosition(tuple(saved["mouse"]))
        point = quartz.CGEventGetLocation(quartz.CGEventCreate(None))
        return abs(point.x - saved["mouse"][0]) <= 1 and abs(point.y - saved["mouse"][1]) <= 1

    def front() -> bool:
        pid = saved["front_pid"]
        if pid is None:
            return True
        app = kit.NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        original = next((a for a in saved["apps"] if a["pid"] == pid), None)
        if (app is None or original is None or app.launchDate() is None
                or float(app.launchDate().timeIntervalSince1970()) != original["launched"]):
            return False
        app.activateWithOptions_(kit.NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.3)
        current = workspace.frontmostApplication()
        return current is not None and int(current.processIdentifier()) == pid

    stage("inputs_released", inputs)
    stage("calculator_closed", calculator)
    stage("applications_restored", applications)
    stage("clipboard_restored", clipboard)
    stage("cursor_restored", cursor)
    stage("front_restored", front)
    stage("input_source_restored",
          lambda: _request("restore", saved["input_source"]) == saved["input_source"])
    results["confirmed"] = all(value is True for value in results.values())
    return results


def _write_private(path: Path, value: dict[str, Any]) -> None:
    with open(path, "x", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


# Child cannot execute the launcher before its PID and recovery baseline are durable.
_CHILD = (
    "import os,sys; "
    "ready=sys.stdin.buffer.read(1); "
    "sys.exit(125) if ready!=b'g' else os.execvp(sys.argv[1],sys.argv[1:])"
)


def supervise(command: list[str], directory: Path, *, timeout: float) -> dict[str, Any]:
    """Wait outside the launcher; recover after success, SIGTRAP or timeout."""
    if not command or timeout <= 0:
        raise ValueError("A command and positive timeout are required")
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    baseline = capture_desktop()
    _write_private(directory / "baseline.json", baseline)
    result: dict[str, Any] = {"child_returncode": None, "timed_out": False}
    child: subprocess.Popen[bytes] | None = None
    try:
        child = subprocess.Popen([sys.executable, "-c", _CHILD, *command],
                                 stdin=subprocess.PIPE, start_new_session=True)
        _write_private(directory / "child.json", {"pid": child.pid})
        assert child.stdin is not None
        child.stdin.write(b"g")
        child.stdin.close()
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            result["timed_out"] = True
    finally:
        if child is not None:
            # Reap the launcher before touching the desktop. Also stop descendants
            # that inherited its process group; never target unrelated user apps.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
            result["child_returncode"] = child.returncode
        try:
            result["recovery"] = restore_desktop(baseline)
        except Exception as exc:
            result["recovery"] = {"confirmed": False, "error": type(exc).__name__}
        _write_private(directory / "result.json", result)
    return result
