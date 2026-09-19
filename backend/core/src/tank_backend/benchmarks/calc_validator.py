"""Local macOS Calculator result validation through Accessibility, without an LLM."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

# Match stable AX identifiers, not translated descriptions or arbitrary text
# elsewhere in the window. Do not activate the app during validation: a hidden
# or background calculator must not pass as a visible result.
READ_DISPLAY = '''
on scanNode(e, depth)
 tell application "System Events"
  set txt to ""
  try
   set ident to value of attribute "AXIdentifier" of e
   if ident is "StandardResultView" then
    return "expression=" & (value of every static text of e as text) & linefeed
   else if ident is "StandardInputView" then
    return "result=" & (value of every static text of e as text) & linefeed
   end if
  end try
  if depth < 10 then
   try
    repeat with child in UI elements of e
     set txt to txt & my scanNode(child, depth + 1)
    end repeat
   end try
  end if
  return txt
 end tell
end scanNode
tell application "System Events"
 if not (exists process "Calculator") then error "Calculator is not running"
 tell process "Calculator"
  if not frontmost or not visible then error "Calculator is not foreground"
  if (count of windows) is not 1 then error "Expected one calculator window"
  if value of attribute "AXMinimized" of window 1 then error "Calculator is minimized"
  set win to window 1
 end tell
end tell
return scanNode(win, 0)
'''


def read_calculator() -> dict[str, str]:
    try:
        result = subprocess.run(
            ["osascript", "-e", READ_DISPLAY], capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode:
        return {}
    fields: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"expression", "result"}:
            if key in fields:
                return {}  # Ambiguous display: fail closed.
            fields[key] = "".join(c for c in value if not c.isspace()
                                  and unicodedata.category(c) != "Cf")
    return fields


def validate_calculator() -> bool:
    fields = read_calculator()
    return fields.get("expression") in {"7×8", "7*8"} and fields.get("result") == "56"


def assess_calculator(
    fields: dict[str, str], events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Supplement legacy strict scoring with isolated input-path evidence.

    Unknown is represented by None, never silently promoted to success.
    AX display evidence does not establish screenshot pixel correctness.
    """
    reset = False
    actions: list[dict[str, Any]] = []
    incomplete = False
    last_screenshot: dict[str, Any] | None = None
    started = False
    pending: set[tuple[str, str, str]] = set()
    for event in events:
        if event.get("kind") == "trial_start":
            reset, actions, incomplete = False, [], False
            last_screenshot, started = None, True
            pending.clear()
        elif not started:
            continue
        elif event.get("kind") == "screenshot":
            last_screenshot = {
                "sha256": event.get("sha256"), "file": event.get("file"),
                "captured_at": event.get("ts"), "http_serialized_at": None,
            }
        elif event.get("kind") == "http_request" and last_screenshot is not None:
            digest = last_screenshot["sha256"]
            if digest and digest in event.get("image_sha256", []):
                last_screenshot["http_serialized_at"] = event.get("ts")
        elif event.get("kind") == "setup_done":
            try:
                setup = json.loads(event.get("stdout", ""))
            except (TypeError, ValueError):
                setup = {}
            reset = isinstance(setup, dict) and setup.get("calculator_reset") is True
        elif event.get("kind") == "output" and event.get("output_type") in {
            "TOOL_EXECUTING", "TOOL_RESULT",
        }:
            meta = event.get("metadata", {})
            if not isinstance(meta, dict):
                incomplete = True
                continue
            name = meta.get("name")
            if name in {"screenshot", "launch_app", "wait"}:
                continue
            call = (str(meta.get("turn")), str(meta.get("index")), str(name))
            if event["output_type"] == "TOOL_EXECUTING":
                pending.add(call)
                continue
            pending.discard(call)
            if meta.get("status") != "success":
                incomplete = True
                continue
            try:
                args = json.loads(meta.get("arguments", ""))
                if not isinstance(args, dict):
                    raise ValueError("arguments must be an object")
                if name == "computer_batch":
                    batch = args.get("actions")
                    if not isinstance(batch, list) or not all(isinstance(a, dict) for a in batch):
                        raise ValueError("missing batch actions")
                    actions.extend(batch)
                else:
                    actions.append({**args, "action": name})
            except (TypeError, ValueError):
                incomplete = True
    incomplete = incomplete or bool(pending)
    inputs = [a for a in actions if a.get("action") not in {"wait", "mouse_move"}]
    if any(a.get("action") not in {"click", "type_text", "key_press"} for a in inputs):
        incomplete = True
    strict = fields.get("expression") in {"7×8", "7*8"} and fields.get("result") == "56"
    business: bool | None = None
    mouse: bool | None = None
    if reset and inputs and not incomplete and "result" in fields:
        # Accept paste only when the completed trace contains the expression,
        # not the answer, and no later action could replace that expression.
        pasted_expression = (
            inputs[0].get("action") == "type_text"
            and inputs[0].get("text") in ("7*8", "7×8")
            and all(a.get("action") == "key_press" and a.get("keys") in ("enter", "return")
                    for a in inputs[1:])
        )
        business = fields.get("result") == "56" and (strict or pasted_expression)
        mouse = strict and len(inputs) >= 4 and all(a.get("action") == "click" for a in inputs)
    return {
        "revision": "calc-evidence-v1", "strict_expression": strict,
        "business": business, "mouse_only": mouse, "pixels": "unknown",
        "reset_verified": reset,
        "input_trace_complete": bool(started and inputs and not incomplete),
        "display": fields,
        "last_screenshot": last_screenshot,
    }


def reset_calculator() -> bool:
    """Clear restored state before a trial, then verify that it is actually zero."""
    script = '''
tell application "Calculator" to activate
delay 0.5
tell application "System Events" to tell process "Calculator"
 if not frontmost then error "Calculator is not foreground"
 key code 53
 key code 53
end tell
delay 0.2
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and read_calculator().get("result") == "0"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if args.reset:
        passed = reset_calculator()
        print(json.dumps({"calculator_reset": passed}))
    else:
        events = []
        trial_dir = os.environ.get("BENCH_TRIAL_DIR")
        if trial_dir:
            try:
                events = [json.loads(line) for line in
                          (Path(trial_dir) / "trace.jsonl").read_text().splitlines()]
                if not all(isinstance(event, dict) for event in events):
                    events = []
            except (OSError, ValueError):
                events = []
        assessment = assess_calculator(read_calculator(), events)
        passed = assessment["strict_expression"]
        message = "Calculator validation passed" if passed else "Calculator validation failed"
        print(json.dumps({"assessment": assessment, "message": message}))
    raise SystemExit(0 if passed else 1)
