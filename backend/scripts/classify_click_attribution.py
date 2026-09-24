"""Classify every dispatched click of a core-trial batch against the measured keypad.

Reads the archived traces plus the measured button rectangles and reports, per arm,
whether a click hit one of the four needed keys, another keypad button, the window
but no button, or was refused before dispatch. This is the automated form of the
"wrong target vs misplaced point" split that the plan's M5 acceptance asks for.

From backend:
  uv run python scripts/classify_click_attribution.py \
    --truth /tmp/tank-button-truth.json trial-dir [trial-dir ...]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

# Verified button centres in the controlled frame (screen pixels).
NEEDED = {"7": (1035, 310), "8": (1101, 310), "multiply": (1233, 310), "equals": (1233, 472)}
NEEDED_RADIUS = 40
QUARTZ = re.compile(r"Quartz \((\d+), (\d+)\)")
LEGACY = re.compile(r"Clicked (?:left|right|middle) button at normalized \((\d+), (\d+)\)")
# The production click tool records only its display form, in 0..1000 units.
DISPLAY = re.compile(r"Clicked \((\d+), (\d+)\)")


def _buttons(truth_path: Path) -> list[tuple[str, int, int, int, int]]:
    truth = json.loads(truth_path.read_text())
    buttons = []
    for name, box in truth.items():
        buttons.append((name, box["x"], box["y"], box["x"] + box["w"] - 1,
                        box["y"] + box["h"] - 1))
    return buttons


def _classify(point: tuple[int, int], buttons, window) -> str:
    x, y = point
    left, top, right, bottom = window
    for name, bx, by, br, bb in buttons:
        if bx <= x <= br and by <= y <= bb:
            for needed, (nx, ny) in NEEDED.items():
                if (x - nx) ** 2 + (y - ny) ** 2 <= NEEDED_RADIUS ** 2:
                    return f"needed:{needed}"
            return "other_keypad"
    if left <= x <= right and top <= y <= bottom:
        return "in_window_miss"
    return "outside_window"


def _clicks(trace: Path, window) -> list[tuple[tuple[int, int], str]]:
    """Dispatched clicks with their screen point; refusals keep their attempted point."""
    screen = (1920, 1080)
    out = []
    for line in trace.read_text().splitlines():
        record = json.loads(line)
        content = str(record.get("content") or "")
        if record.get("kind") == "desktop_dispatch" and record.get("name") == "click":
            continue
        match = QUARTZ.search(content)
        if match:
            out.append(((int(match.group(1)), int(match.group(2))), "dispatched"))
            continue
        match = LEGACY.search(content)
        if match:
            nx, ny = int(match.group(1)), int(match.group(2))
            out.append(((round(nx * screen[0] / 1000), round(ny * screen[1] / 1000)),
                        "dispatched"))
            continue
        match = DISPLAY.search(content)
        if match:
            nx, ny = int(match.group(1)), int(match.group(2))
            out.append(((round(nx * screen[0] / 1000), round(ny * screen[1] / 1000)),
                        "dispatched"))
            continue
        if "input blocked" in content:
            match = re.search(r"click target \((\d+), (\d+)\)", content)
            if match:
                out.append(((int(match.group(1)), int(match.group(2))), "blocked"))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--window", default="600,100,1274,508")
    parser.add_argument("dirs", nargs="+", type=Path)
    args = parser.parse_args()
    window = tuple(int(v) for v in args.window.split(","))
    buttons = _buttons(args.truth)
    per_arm: dict[str, Counter] = {}
    per_trial: dict[str, Counter] = {}
    for directory in args.dirs:
        for trial in sorted(p for p in directory.iterdir() if p.is_dir()):
            trace = trial / trial.name / "trials/calc-open/1/trace.jsonl"
            if not trace.exists():
                continue
            arm = trial.name.split("-", 2)[2]
            counts = per_arm.setdefault(arm, Counter())
            trial_counts = per_trial.setdefault(trial.name, Counter())
            for (point, state) in _clicks(trace, window):
                label = state if state == "blocked" else _classify(point, buttons, window)
                counts[label] += 1
                trial_counts[label] += 1
    print(f"{'arm':13} {'needed':7} {'other_keypad':13} {'in_window_miss':15} {'blocked':8} {'total':6}")
    for arm in sorted(per_arm):
        c = per_arm[arm]
        needed = sum(v for k, v in c.items() if k.startswith("needed:"))
        print(f"{arm:13} {needed:7} {c['other_keypad']:13} {c['in_window_miss']:15} "
              f"{c['blocked']:8} {sum(c.values()):6}")
    for name in sorted(per_trial):
        c = per_trial[name]
        needed = {k.split(":")[1]: v for k, v in c.items() if k.startswith("needed:")}
        print(f"   {name:22} needed={needed or '{}'} other={c['other_keypad']} "
              f"miss={c['in_window_miss']} blocked={c['blocked']}")
    (args.dirs[0] / "click-attribution.json").write_text(json.dumps(
        {"arm_totals": {arm: dict(c) for arm, c in per_arm.items()},
         "trial_totals": {name: dict(c) for name, c in per_trial.items()}}, indent=2) + "\n")


if __name__ == "__main__":
    main()
