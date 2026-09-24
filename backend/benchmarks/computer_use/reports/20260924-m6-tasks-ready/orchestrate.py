"""M6 item-3/4 live orchestrator: run every task serially under supervision.

For each task: start the supervised launcher (--live), wait for ready.json,
verify the controlled fixture programmatically (only allowed apps may be
visible, backdrop present), release `go`, and wait for completion. Any error
aborts the remaining schedule. The user authorized the full completion batch;
each task still passes through its own initial-state gate before any image is
sent.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path("/Users/zbcjackson/src/tank/backend")
LAUNCHER = (BACKEND / "benchmarks/computer_use/reports/20260924-m6-tasks-ready"
            / "launcher.py")
TASK_APPS = {
    "open-settings": ["System Settings"],
    "browser-navigate": ["Safari"], "local-form": ["Safari"],
    "typing-fidelity": ["Safari"], "links-history": ["Safari"],
    "small-text-code": ["Safari"],
    "file-ops": ["Finder"], "multi-select-copy": ["Finder"], "drag-file": ["Finder"],
    "terminal-write": ["Terminal"],
    "settings-toggle": ["System Settings"],
    "editor-save": ["TextEdit"], "window-copy": ["TextEdit", "Safari"],
    "long-history": ["TextEdit"],
}


def verify_fixture(out: Path, allowed: list[str]) -> str:
    """Programmatic initial review; returns a failure reason or empty."""
    import AppKit
    import Quartz

    workspace = AppKit.NSWorkspace.sharedWorkspace()
    visible = [str(a.localizedName()) for a in workspace.runningApplications()
               if a.activationPolicy() == AppKit.NSApplicationActivationPolicyRegular
               and not a.isHidden() and str(a.localizedName()) not in allowed]
    if visible:
        return f"non-allowed apps visible: {visible}"
    info = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    owners = {str(w.get("kCGWindowOwnerName")) for w in (info or [])}
    unexpected = [o for o in owners if o not in
                  set(allowed) | {"Dock", "Control Center", "Window Server",
                                  "Bartender 6", "Finder", "System UI Server",
                                  "System Settings", "Wallpaper", "python",
                                  "Shortcuts Events", "Spotlight", "Notification Centre"}]
    if unexpected:
        return f"unexpected window owners on screen: {unexpected}"
    if not (out / "initial.png").exists():
        return "initial.png missing"
    return ""


def run_task(task: str) -> bool:
    stamp = time.strftime("%H%M%S")
    out = Path(f"/tmp/tank-m6-{task}-20260925-live")
    state = Path(f"/tmp/tank-m6-{task}-recovery")
    if out.exists() or state.exists():
        print(f"[{task}] output/state exists; refusing replay", flush=True)
        return False
    proc = subprocess.Popen(
        [sys.executable, "scripts/supervise_computer_pilot.py",
         "--state-dir", str(state), "--timeout", "3600", "--",
         "python", str(LAUNCHER), "--task", task, "--live"],
        cwd=BACKEND, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 120
        while time.time() < deadline:
            if (out / "ready.json").exists():
                break
            if proc.poll() is not None:
                print(f"[{task}] launcher exited before ready", flush=True)
                return False
            time.sleep(1)
        else:
            print(f"[{task}] ready timeout", flush=True)
            return False
        allowed = TASK_APPS[task]
        reason = verify_fixture(out, allowed)
        if reason:
            print(f"[{task}] fixture review FAILED: {reason}", flush=True)
            return False
        (out / "go").touch()
        print(f"[{task}] go released {stamp}; allowed={allowed}", flush=True)
        rc = proc.wait(timeout=3600)
        print(f"[{task}] finished rc={rc}", flush=True)
        return rc == 0
    finally:
        if proc.poll() is None:
            proc.kill()


def main() -> int:
    tasks = sys.argv[1:]
    order = [t for t in tasks]
    results = {}
    for task in order:
        ok = run_task(task)
        results[task] = ok
        if not ok:
            print(f"ABORT remaining after {task}: {results}", flush=True)
            return 1
    print(json.dumps(results), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
