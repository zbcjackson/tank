"""Run one already-authorized controlled launcher with an outer recovery owner.

Example (preview only; the launcher's own live gates still apply):
  uv run python scripts/supervise_computer_pilot.py \
    --state-dir /tmp/tank-pilot-recovery-new --timeout 180 -- python launcher.py

Never archive baseline.json: it contains the user's private clipboard/app state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tank_backend.benchmarks.desktop_recovery import supervise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    result = supervise(command, args.state_dir, timeout=args.timeout)
    print(json.dumps(result, indent=2))
    return 0 if result["child_returncode"] == 0 and result["recovery"]["confirmed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
