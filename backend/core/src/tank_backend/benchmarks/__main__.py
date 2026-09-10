"""CLI: run a benchmark suite.

Usage (from ``backend/core`` or repo root — config.yaml is located by
walking up from either):

    uv run python -m tank_backend.benchmarks \
        --suite ../../benchmarks/computer_use \
        --agent computer_use --trials 3 --label baseline-macos

Reports land in ``<suite>/reports/<timestamp>-<label>/``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from .driver import SubAgentDriver
from .runner import run_suite
from .task import current_platform


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tank_backend.benchmarks",
        description="Run a Tank sub-agent benchmark suite.",
    )
    parser.add_argument(
        "--suite", type=Path, required=True,
        help="suite directory (contains suite.yaml + tasks/)",
    )
    parser.add_argument(
        "--agent", default=None,
        help="agent definition name (default: suite.yaml 'agent')",
    )
    parser.add_argument("--trials", type=int, default=None)
    parser.add_argument(
        "--tasks", default=None,
        help="regex on task ids — run a subset (debugging; not for comparable reports)",
    )
    parser.add_argument("--platform", choices=("macos", "linux"), default=None)
    parser.add_argument("--label", default=None, help="run label for the report")
    parser.add_argument("--out", type=Path, default=None, help="output dir override")
    parser.add_argument("--config", type=Path, default=None, help="config.yaml override")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from .task import load_suite

    suite = load_suite(args.suite / "suite.yaml")
    agent = args.agent or suite.agent
    if agent is None:
        parser.error("no --agent given and suite.yaml has no 'agent' default")
    trials = args.trials or int(suite.defaults.get("trials", 3))
    platform = args.platform or current_platform()
    label = args.label or f"{suite.name}-{platform}"
    out_dir = args.out or (
        args.suite
        / "reports"
        / f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{label}"
    )

    print(f"suite={suite.name} agent={agent} trials={trials} platform={platform}")
    print(f"output: {out_dir}")

    driver_factory = lambda: SubAgentDriver.create(agent, config_path=args.config)  # noqa: E731

    report = asyncio.run(
        run_suite(
            args.suite.resolve(),
            driver_factory,
            platform=platform,
            trials=trials,
            out_dir=out_dir,
            label=label,
            task_filter=re.compile(args.tasks) if args.tasks else None,
        )
    )
    total = report.total_trials
    print(
        f"\n{report.successes}/{total} passed "
        f"({report.success_rate * 100:.0f}%, 95% CI "
        f"{report.ci_lo * 100:.0f}–{report.ci_hi * 100:.0f}%)"
    )
    print(f"report: {out_dir / 'report.md'}")


if __name__ == "__main__":
    main()
