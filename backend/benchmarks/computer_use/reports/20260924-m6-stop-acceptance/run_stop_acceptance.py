"""M6 item 5: stop/cleanup acceptance on the real dispatch path.

Five scenarios cancel a live SubAgentDriver run mid-flight — planner request
wait, split-mode locate wait, key hold, computer_batch, and drag. For each we
verify, after the cancelled run *returns*: >=10s with zero input events on a
Quartz session tap (the join semantics must finish any in-flight native
action before returning), no held keys or mouse buttons, and the desktop
resource is usable again (a follow-up run completes). The batch scenario also
checks that members scheduled after the cancel never execute.

The LLM endpoint is a local loopback mock: real screenshots stay on this
machine, zero external requests, zero model calls. Real input actions are
confined to a blank TextEdit document.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import Quartz

from tank_backend.benchmarks.driver import SubAgentDriver
from tank_backend.benchmarks.trace import TraceSink

OUT = Path(__file__).resolve().parent
BACKEND = OUT.parents[3]
FREEZE = BACKEND / "benchmarks/computer_use/reports/20260924-m6-calc-runtime"
PORT = 8931
QUIET_SECONDS = 10.0

results: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Local mock LLM: scripted SSE / JSON responses with deliberate delays.
# ---------------------------------------------------------------------------
SCRIPT: dict = {"planner": [], "locator": []}


def sse(chunks: list[dict]) -> bytes:
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks).encode() + b"data: [DONE]\n\n"


def planner_tool_call(name: str, arguments: dict, call_id: str) -> list[dict]:
    return [
        {"id": call_id, "object": "chat.completion.chunk", "created": 1,
         "model": "mock", "choices": [{"index": 0, "delta": {"tool_calls": [{
             "index": 0, "id": call_id, "type": "function",
             "function": {"name": name, "arguments": json.dumps(arguments)}}]},
             "finish_reason": None}]},
        {"id": call_id, "object": "chat.completion.chunk", "created": 1,
         "model": "mock", "choices": [{"index": 0, "delta": {},
                                       "finish_reason": "tool_calls"}],
         "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
    ]


def planner_text(text: str) -> list[dict]:
    return [
        {"id": "t", "object": "chat.completion.chunk", "created": 1, "model": "mock",
         "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]},
        {"id": "t", "object": "chat.completion.chunk", "created": 1, "model": "mock",
         "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
    ]


def scripted_handler(script_key: str, fallback_key: str | None = None):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            key = "locator" if not body.get("stream") else "planner"
            queue = SCRIPT[key] if SCRIPT[key] else (
                SCRIPT[fallback_key] if fallback_key and SCRIPT[fallback_key] else [])
            if not queue:
                self.send_response(500)
                self.end_headers()
                return
            delay, payload, kind = queue.pop(0)
            time.sleep(delay)
            if body.get("stream"):
                content = sse(payload)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
            else:
                content = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args: object) -> None:
            return
    return Handler


def start_mock(handler) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ---------------------------------------------------------------------------
# Quartz session tap: every real input event with a timestamp.
# ---------------------------------------------------------------------------
TAP_EVENTS: list[tuple[float, str]] = []
_tap_lock = threading.Lock()

MASK = ((1 << int(Quartz.kCGEventLeftMouseDown))
        | (1 << int(Quartz.kCGEventLeftMouseUp))
        | (1 << int(Quartz.kCGEventLeftMouseDragged))
        | (1 << int(Quartz.kCGEventKeyDown))
        | (1 << int(Quartz.kCGEventKeyUp))
        | (1 << int(Quartz.kCGEventScrollWheel)))


def _tap_callback(proxy, event_type, event, refcon) -> int:
    with _tap_lock:
        TAP_EVENTS.append((time.time(), str(int(event_type))))
    return event


def start_tap() -> None:
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault, MASK, _tap_callback, None,
    )
    if tap is None:
        raise RuntimeError("Event tap creation failed (Accessibility?)")

    def run_loop() -> None:
        loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(
            loop, Quartz.CFMachPortCreateRunLoopSource(None, tap, 0),
            Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        Quartz.CFRunLoopRun()

    threading.Thread(target=run_loop, daemon=True).start()


def events_since(ts: float) -> list[tuple[float, str]]:
    with _tap_lock:
        return [e for e in TAP_EVENTS if e[0] >= ts]


def input_state() -> tuple[list[int], list[int]]:
    state = Quartz.kCGEventSourceStateCombinedSessionState
    return ([k for k in range(128) if Quartz.CGEventSourceKeyState(state, k)],
            [b for b in range(3) if Quartz.CGEventSourceButtonState(state, b)])


# ---------------------------------------------------------------------------
# Driver plumbing: freeze configs with the endpoint pointed at the mock.
# ---------------------------------------------------------------------------
def make_config(variant: str, name: str) -> Path:
    import yaml

    target = OUT / f"cfg-{name}"
    raw = yaml.safe_load((FREEZE / "runtime" / variant / "config.yaml").read_text())
    for profile in raw.get("llm", {}).values():
        profile["base_url"] = f"http://127.0.0.1:{PORT}/v1"
        profile["api_key"] = "local-mock"
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.yaml").write_text(yaml.safe_dump(raw))
    agents = target / "agents"
    if not agents.exists():
        agents.symlink_to((FREEZE / "runtime" / variant / "agents").resolve())
    return target / "config.yaml"


async def cancelled_run(config: Path, instruction: str, trace_dir: Path,
                        cancel_after: float) -> tuple[object | None, object | None, float]:
    """Run a driver, cancel it mid-flight, and report when it actually returned."""
    trace = TraceSink(trace_dir)
    driver = SubAgentDriver.create("computer_use", config, input_cleanup=True)
    task = asyncio.create_task(driver.run(
        instruction, trace, timeout_s=90, max_steps=10))
    await asyncio.sleep(cancel_after)
    cancelled_at = time.time()
    task.cancel()
    result, error = None, None
    try:
        result = await task
    except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
        error = exc
    returned_at = time.time()
    trace.close()
    return result, error, cancelled_at, returned_at


def observe_quiet(since: float) -> dict:
    """A full QUIET_SECONDS with zero input events after the run returned."""
    deadline = time.time() + QUIET_SECONDS
    while time.time() < deadline:
        time.sleep(0.2)
    after = events_since(since)
    return {"events": len(after), "detail": after[:10]}


async def reuse_check(variant: str, name: str) -> bool:
    SCRIPT["planner"] = [(0.0, planner_text("reuse-ok"), "sse")]
    SCRIPT["locator"] = []
    config = make_config(variant, f"{name}-reuse")
    trace = TraceSink(OUT / f"trace-{name}-reuse")
    driver = SubAgentDriver.create("computer_use", config, input_cleanup=True)
    try:
        result = await driver.run("finish", trace, timeout_s=30, max_steps=4)
        return result.final_text == "reuse-ok" and result.error is None
    finally:
        trace.close()


# ---------------------------------------------------------------------------
# TextEdit sandbox for real (harmless) input actions.
# ---------------------------------------------------------------------------
def run_osascript(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["osascript", "-e", script], capture_output=True, timeout=20)


def textedit_setup() -> dict:
    was_running = subprocess.run(
        ["pgrep", "-x", "TextEdit"], capture_output=True).returncode == 0
    run_osascript('tell application "TextEdit" to activate')
    time.sleep(0.8)
    run_osascript('tell application "TextEdit" to make new document')
    time.sleep(0.5)
    info = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    for entry in info or []:
        if entry.get("kCGWindowOwnerName") == "TextEdit" and entry.get("kCGWindowLayer") == 0:
            b = entry.get("kCGWindowBounds") or {}
            return {"was_running": was_running,
                    "bounds": (int(b["X"]), int(b["Y"]), int(b["Width"]), int(b["Height"]))}
    raise RuntimeError("No TextEdit window found")


def textedit_text() -> str:
    proc = run_osascript('tell application "TextEdit" to get text of front document')
    return proc.stdout.decode().rstrip("\n")


async def scenario(name: str, variant: str, planner_script: list,
                   instruction: str, cancel_after: float,
                   content_check: tuple[str, bool] | None = None) -> None:
    SCRIPT["planner"] = list(planner_script)
    SCRIPT["locator"] = []
    before_text = textedit_text()
    result, error, cancelled_at, returned_at = await cancelled_run(
        make_config(variant, name), instruction, OUT / f"trace-{name}", cancel_after)
    quiet = observe_quiet(returned_at)
    keys, buttons = input_state()
    reuse = await reuse_check(variant, name)
    entry = {
        "returned_after_cancel_s": round(returned_at - cancelled_at, 3),
        "error_type": type(error).__name__ if error else None,
        "held_keys": keys, "held_buttons": buttons, "quiet": quiet, "reuse_ok": reuse,
    }
    if content_check:
        marker, must_absent = content_check
        present = marker in textedit_text() and marker not in before_text
        entry["marker_present"] = present
        entry["marker_absent_ok"] = (not present) if must_absent else present
    results[name] = entry
    print(json.dumps({name: entry}), flush=True)


async def locate_wait_scenario() -> None:
    """Split mode: planner observes, then the locate request stalls; cancel it."""
    SCRIPT["planner"] = [
        (0.0, planner_tool_call("screenshot", {}, "c1"), "sse"),
        (0.0, planner_tool_call("locate", {"target": "any visible text"}, "c2"), "sse"),
    ]
    SCRIPT["locator"] = [(25.0, {}, "json")]
    result, error, cancelled_at, returned_at = await cancelled_run(
        make_config("c", "locate-wait"), "find the text",
        OUT / "trace-locate-wait", cancel_after=6.0)
    quiet = observe_quiet(returned_at)
    keys, buttons = input_state()
    reuse = await reuse_check("c", "locate-wait")
    results["locate-wait"] = {
        "returned_after_cancel_s": round(returned_at - cancelled_at, 3),
        "error_type": type(error).__name__ if error else None,
        "held_keys": keys, "held_buttons": buttons, "quiet": quiet, "reuse_ok": reuse,
    }
    print(json.dumps({"locate-wait": results["locate-wait"]}), flush=True)


async def main() -> None:
    started = time.time()
    mock = start_mock(scripted_handler("planner", "locator"))
    start_tap()
    time.sleep(0.3)
    textedit = textedit_setup()
    x, y, w, h = textedit["bounds"]
    print(f"TextEdit bounds: {textedit['bounds']}", flush=True)

    # 1. Planner request in flight (25s delay); cancel at 2s. No dispatch at all.
    await scenario(
        "planner-wait", "a",
        [(25.0, planner_text("late"), "sse")], "wait then finish", cancel_after=2.0,
    )
    # 2. Split locate request in flight; cancel mid-locate.
    await locate_wait_scenario()
    # 3. Key hold in progress (6s); cancel at 1.5s. Join must finish + release.
    await scenario(
        "key-hold", "a",
        [(0.0, planner_tool_call("hold_key", {"keys": "shift", "duration_s": 6}, "h1"), "sse")],
        "hold the key", cancel_after=1.5,
    )
    # 4. Batch in progress; members after the cancel must never run.
    await scenario(
        "batch", "a",
        [(0.0, planner_tool_call("computer_batch", {"actions": [
            {"action": "type_text", "text": "M6STOP-"},
            {"action": "key_press", "keys": "enter"},
            {"action": "wait", "seconds": 5},
            {"action": "type_text", "text": "AFTERCANCEL"},
        ], "screenshot": False}, "b1"), "sse")],
        "run the batch", cancel_after=1.2, content_check=("AFTERCANCEL", True),
    )
    # 5. Drag in progress; the button must not stay down after return.
    await scenario(
        "drag", "a",
        [(0.0, planner_tool_call("drag", {
            "x1": x + 80, "y1": y + 120,
            "x2": x + min(900, w - 80), "y2": y + 120}, "d1"), "sse")],
        "drag", cancel_after=0.4,
    )

    textedit_teardown(textedit)
    mock.shutdown()
    summary = {
        "started_at": started, "finished_at": time.time(),
        "quiet_required_s": QUIET_SECONDS, "scenarios": results,
        "external_requests": 0, "endpoint": f"http://127.0.0.1:{PORT}/v1 (loopback mock)",
        "textedit_bounds": textedit["bounds"],
    }
    (OUT / "results.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    all_ok = True
    for name, r in results.items():
        bad = (r.get("held_keys") or r.get("held_buttons")
               or r["quiet"]["events"] or not r["reuse_ok"]
               or not r.get("marker_absent_ok", True))
        all_ok &= not bad
        print(f"{name}: {'PASS' if not bad else 'FAIL'} "
              f"(keys={r['held_keys']} buttons={r['held_buttons']} "
              f"events={r['quiet']['events']} reuse={r['reuse_ok']})", flush=True)
    print("SUMMARY:", "ALL PASS" if all_ok else "FAILURES PRESENT", flush=True)


def textedit_teardown(state: dict) -> None:
    run_osascript('tell application "TextEdit" to close front document saving no')
    if not state["was_running"]:
        run_osascript('tell application "TextEdit" to quit')


if __name__ == "__main__":
    asyncio.run(main())
