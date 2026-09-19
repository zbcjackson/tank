"""Local macOS Calculator result validation through Accessibility, without an LLM."""

from __future__ import annotations

import argparse
import subprocess
import unicodedata

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
    passed = reset_calculator() if args.reset else validate_calculator()
    print("Calculator validation passed" if passed else "Calculator validation failed")
    raise SystemExit(0 if passed else 1)
