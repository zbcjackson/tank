"""A12: computer-use capability self-check (``tank-backend --check-computer-use``).

Probes only — never injects input. Every failed check carries the exact
fix that came out of the 2026-09-13 GUI-VM debugging marathon (dead CLI,
missing udev tag, wl-copy gaps, macOS accessibility), so the next
environment comes up diagnosed instead of mysterious.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str  # ok | warn | fail
    detail: str
    fix: str | None = None


@dataclass
class DoctorReport:
    platform: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        names = {c.name for c in self.checks if c.status == FAIL}
        # No working screenshot = the stack is unusable, not degraded.
        if "screenshot" in names:
            return 2
        if names:
            return 1
        return 0

    def as_dict(self) -> dict:
        return {
            "platform": self.platform,
            "exit_code": self.exit_code,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail,
                 "fix": c.fix}
                for c in self.checks
            ],
        }


def _which(binary: str) -> str | None:
    return shutil.which(binary)


def _check_display_server() -> CheckResult:
    if sys.platform == "darwin":
        return CheckResult("display_server", OK, "macOS window server")
    import os

    kind = os.environ.get("XDG_SESSION_TYPE", "unknown")
    if kind == "wayland":
        return CheckResult("display_server", OK, "wayland")
    if kind == "x11":
        return CheckResult(
            "display_server", WARN, "x11",
            "Wayland+portal is the supported path; X11 uses the pyautogui "
            "fallback (untested in benchmarks)",
        )
    return CheckResult(
        "display_server", FAIL, f"XDG_SESSION_TYPE={kind}",
        "Run inside the graphical session (not SSH/tmux without session env)",
    )


def _check_screenshot() -> CheckResult:
    started = time.monotonic()
    try:
        if sys.platform == "darwin":
            r = subprocess.run(
                ["screencapture", "-x", "/tmp/tank-doctor-shot.png"],
                capture_output=True, timeout=10,
            )
            ok = r.returncode == 0
            err = r.stderr.decode()[:120]
        else:
            from .computer_use import _capture_screenshot

            png = _capture_screenshot()
            ok = png is not None and len(png) > 100
            err = "" if ok else "portal + mss both returned nothing"
    except Exception as e:  # noqa: BLE001 — report, don't crash
        return CheckResult(
            "screenshot", FAIL, f"capture error: {e}",
            "Linux: check xdg-desktop-portal-gnome is running "
            "(systemctl --user status xdg-desktop-portal-gnome)",
        )
    elapsed = time.monotonic() - started
    if not ok:
        return CheckResult("screenshot", FAIL, err or "capture failed", None)
    grade = OK if elapsed < 1.5 else WARN
    note = "" if elapsed < 1.5 else " (slow — portal response wait >1.5s)"
    return CheckResult("screenshot", grade, f"roundtrip {elapsed:.2f}s{note}")


def _check_input_linux() -> list[CheckResult]:
    from .computer_use import _ydotool_socket

    results: list[CheckResult] = []
    socket = _ydotool_socket()
    if socket:
        results.append(CheckResult("ydotool_daemon", OK, socket))
    else:
        results.append(CheckResult(
            "ydotool_daemon", FAIL, "no socket found",
            "systemctl --user start ydotool (or: sudo ydotoold "
            "--socket-path /run/ydotool.sock --socket-perm 0666 &)",
        ))

    # udev classification: without ID_INPUT_MOUSE the compositor ignores
    # pointer motion from the virtual device (proven the hard way).
    try:
        out = subprocess.run(
            ["grep", "-B1", "-A8", "ydotoold", "/proc/bus/input/devices"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        event = None
        for token in out.replace("\t", " ").split():
            if token.startswith("event"):
                event = token
                break
        if not event:
            results.append(CheckResult(
                "udev_input_device", FAIL,
                "ydotoold virtual device not present",
                "Restart the daemon — the device is created on start",
            ))
        else:
            info = subprocess.run(
                ["udevadm", "info", f"/dev/input/{event}"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            if "ID_INPUT_MOUSE=1" in info:
                results.append(CheckResult("udev_input_device", OK, event))
            else:
                results.append(CheckResult(
                    "udev_input_device", FAIL,
                    f"{event} lacks ID_INPUT_MOUSE (pointer motion dropped)",
                    "echo 'SUBSYSTEM==\"input\", ATTRS{name}=="
                    "\"ydotoold virtual device\", ENV{ID_INPUT_MOUSE}=\"1\"' "
                    "| sudo tee /etc/udev/rules.d/80-ydotool-mouse.rules && "
                    "sudo udevadm control --reload && restart the daemon",
                ))
    except Exception as e:  # noqa: BLE001
        results.append(CheckResult("udev_input_device", WARN, str(e)[:100]))

    libinput = _which("libinput")
    if libinput is None:
        results.append(CheckResult(
            "libinput_class", WARN, "libinput-tools not installed",
            "sudo apt install libinput-tools (for classification check)",
        ))
    else:
        try:
            out = subprocess.run(
                [libinput, "list-devices"], capture_output=True,
                text=True, timeout=5,
            ).stdout
            block = ""
            for chunk in out.split("Device:"):
                if "ydotoold" in chunk:
                    block = chunk
                    break
            caps = ""
            for line in block.splitlines():
                if line.strip().startswith("Capabilities:"):
                    caps = line.split(":", 1)[1].strip()
            if "pointer" in caps:
                results.append(CheckResult("libinput_class", OK, caps))
            else:
                results.append(CheckResult(
                    "libinput_class", WARN, caps or "device not listed",
                    "Check the udev tag above; libinput follows udev",
                ))
        except Exception as e:  # noqa: BLE001
            results.append(CheckResult("libinput_class", WARN, str(e)[:100]))
    return results


def _check_clipboard_linux() -> CheckResult:
    if _which("wl-copy"):
        return CheckResult("clipboard", OK, "wl-copy")
    if _which("xclip"):
        return CheckResult(
            "clipboard", WARN, "xclip only (Wayland paste may hang)",
            "sudo apt install wl-clipboard",
        )
    return CheckResult(
        "clipboard", FAIL, "no clipboard tool",
        "sudo apt install wl-clipboard",
    )


def _check_accessibility_macos() -> CheckResult:
    r = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to keystroke ""'],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode == 0:
        return CheckResult("accessibility", OK, "AX granted")
    if "1002" in (r.stderr or "") or "not allowed" in (r.stderr or ""):
        return CheckResult(
            "accessibility", FAIL, "keystroke not allowed (1002)",
            "System Settings → Privacy & Security → Accessibility → "
            "enable the terminal app that runs Tank",
        )
    return CheckResult(
        "accessibility", WARN, (r.stderr or "?").strip()[:100]
    )


def run_doctor() -> DoctorReport:
    """Probe the computer-use stack. Read-only — no input injection."""
    report = DoctorReport(platform=sys.platform)
    report.checks.append(_check_display_server())
    report.checks.append(_check_screenshot())
    if sys.platform == "darwin":
        report.checks.append(_check_accessibility_macos())
    else:
        report.checks.extend(_check_input_linux())
        report.checks.append(_check_clipboard_linux())
    return report


def format_report(report: DoctorReport) -> str:
    icon = {OK: "✓", WARN: "⚠", FAIL: "✗"}
    lines = [f"computer-use capability report ({report.platform})"]
    for c in report.checks:
        lines.append(f"  {icon[c.status]} {c.name}: {c.detail}")
        if c.fix:
            lines.append(f"      fix: {c.fix}")
    verdict = {0: "READY", 1: "DEGRADED", 2: "UNUSABLE"}[report.exit_code]
    lines.append(f"  verdict: {verdict}")
    return "\n".join(lines)
