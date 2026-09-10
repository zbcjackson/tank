"""Suite orchestration: setup → drive → validate → teardown per trial."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Protocol

from .driver import BenchmarkDriver, DriverResult
from .ime import current_input_source_id, pin_ascii_input_source, restore_input_source
from .pageserver import LocalPageServer
from .report import SuiteReport, TrialRecord, aggregate, write_json_report, write_markdown_report
from .shell import ShellError, run_shell
from .task import BenchTask, load_suite, load_suite_tasks
from .trace import TraceSink

logger = logging.getLogger(__name__)

_SETUP_TIMEOUT_S = 60.0
_VALIDATOR_TIMEOUT_S = 30.0
_TEARDOWN_TIMEOUT_S = 60.0


class DriverFactory(Protocol):
    def __call__(self) -> BenchmarkDriver: ...


async def run_suite(
    suite_dir: Path,
    driver_factory: DriverFactory,
    *,
    platform: str,
    trials: int,
    out_dir: Path,
    label: str,
    title: str | None = None,
    task_filter: re.Pattern[str] | None = None,
) -> SuiteReport:
    """Run every platform-matching task ``trials`` times and report.

    A fresh driver is built per task (``driver_factory``), mirroring a
    clean session per measured unit. Trial dirs land under
    ``out_dir/trials/<task_id>/<n>/`` with trace.jsonl + screenshots +
    result.json; the aggregated report lands beside them.

    ``task_filter`` keeps only tasks whose id matches the regex — for
    debugging single tasks without running the whole suite. Filtered
    runs are for diagnosis, not for comparable reports.
    """
    suite = load_suite(suite_dir / "suite.yaml")
    tasks = load_suite_tasks(suite_dir / "tasks", platform, defaults=dict(suite.defaults))
    if task_filter is not None:
        tasks = [t for t in tasks if task_filter.search(t.id)]
    if not tasks:
        raise ValueError(f"no tasks for platform '{platform}' in {suite_dir / 'tasks'}")

    out_dir.mkdir(parents=True, exist_ok=True)
    capture_path = out_dir / "page_capture.jsonl"
    capture_path.write_text("", encoding="utf-8")

    records: list[TrialRecord] = []

    assets_dir = suite_dir / suite.assets_dir if suite.assets_dir else None
    server: LocalPageServer | None = None
    if assets_dir is not None and assets_dir.is_dir():
        server = LocalPageServer(assets_dir, capture_path, port=suite.server_port)
    bench_env = {
        "BENCH_CAPTURE": str(capture_path),
        "BENCH_ASSETS_DIR": str(assets_dir) if assets_dir is not None else "",
        "BENCH_ASSETS_URL": server.base_url if server is not None else "",
    }
    original_ime = current_input_source_id()
    run_started = time.monotonic()
    try:
        for task in tasks:
            driver = driver_factory()
            task_started = time.monotonic()
            task_records: list[TrialRecord] = []
            for trial in range(1, trials + 1):
                # A Chinese IME eats ASCII punctuation ("-"/"."); input-source
                # stickiness is per-app, so pin fresh before every trial.
                pin_ascii_input_source()
                record = await _run_trial(driver, task, trial, out_dir, bench_env)
                records.append(record)
                task_records.append(record)
                logger.info(
                    "task=%s trial=%d success=%s steps=%d wall=%.1fs",
                    task.id, trial, record.success, record.steps, record.wall_s,
                )
            passed = sum(1 for r in task_records if r.success)
            logger.info(
                "task=%s done: %d/%d passed in %.1fs",
                task.id, passed, len(task_records), time.monotonic() - task_started,
            )
    finally:
        if server is not None:
            server.stop()
        restore_input_source(original_ime)
    logger.info(
        "suite done: %d trials in %.1fs", len(records), time.monotonic() - run_started
    )

    report = aggregate(records)
    write_markdown_report(
        report,
        out_dir / "report.md",
        title=title or f"{suite.name} benchmark",
        label=label,
    )
    write_json_report(report, out_dir / "report.json", label=label)
    return report


async def _run_trial(
    driver: BenchmarkDriver,
    task: BenchTask,
    trial: int,
    out_dir: Path,
    bench_env: dict[str, str],
) -> TrialRecord:
    trial_dir = out_dir / "trials" / task.id / str(trial)
    trace = TraceSink(trial_dir)
    trace.event("trial_start", task=task.id, trial=trial, instruction=task.instruction)
    trial_started = time.monotonic()

    error: str | None = None
    timed_out = False
    success = False
    result: DriverResult | None = None

    try:
        if task.setup:
            await run_shell(task.setup, timeout_s=_SETUP_TIMEOUT_S, extra_env=bench_env)
            trace.event("setup_done")

        result = await driver.run(
            task.instruction, trace, timeout_s=task.timeout_s, max_steps=task.max_steps,
        )
        timed_out = result.timed_out
        error = result.error

        if timed_out:
            success = False
        else:
            try:
                await run_shell(
                    task.validator_command,
                    timeout_s=_VALIDATOR_TIMEOUT_S,
                    extra_env=bench_env,
                )
                success = True
                trace.event("validator_passed")
            except ShellError as e:
                success = False
                error = error or "validator failed"
                trace.event("validator_failed", detail=str(e)[:2000])
    except ShellError as e:
        success = False
        error = f"setup failed: {e}"
        trace.event("setup_failed", detail=str(e)[:2000])
    except Exception as e:  # noqa: BLE001 — one bad trial must not kill the suite
        success = False
        error = f"driver error: {e}"
        trace.event("driver_error", detail=str(e)[:2000])
        logger.exception("trial crashed: task=%s trial=%d", task.id, trial)
    finally:
        if task.teardown:
            try:
                await run_shell(task.teardown, timeout_s=_TEARDOWN_TIMEOUT_S, extra_env=bench_env)
            except ShellError as e:
                logger.warning("teardown failed for %s: %s", task.id, e)
        trace.event("trial_end", success=success, error=error)
        trace.close()

    record = TrialRecord(
        task_id=task.id,
        trial=trial,
        success=success,
        error=error,
        steps=result.steps if result else 0,
        # Full trial wall time (setup + agent + validator + teardown);
        # the agent-only segment is in the trace's driver_done event.
        wall_s=time.monotonic() - trial_started,
        tokens=result.tokens if result else 0,
        screenshots=result.screenshots if result else 0,
        timed_out=timed_out,
    )
    (trial_dir / "result.json").write_text(
        json.dumps(
            {
                "task_id": record.task_id,
                "trial": record.trial,
                "success": record.success,
                "error": record.error,
                "steps": record.steps,
                "wall_s": record.wall_s,
                "tokens": record.tokens,
                "screenshots": record.screenshots,
                "timed_out": record.timed_out,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return record
