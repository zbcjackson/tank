"""Suite orchestration: setup → drive → validate → teardown per trial."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Protocol

from .driver import BenchmarkDriver, DriverResult
from .ime import pin_ascii_input_source, restore_saved_input_source, save_current_input_source
from .pageserver import LocalPageServer
from .report import (
    SCORING_REVISION,
    SuiteReport,
    TrialRecord,
    aggregate,
    write_json_report,
    write_markdown_report,
)
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
    save_current_input_source()
    run_started = time.monotonic()
    aborted = False
    driver_metadata = {}
    try:
        for task in tasks:
            driver = driver_factory()
            describe = getattr(driver, "describe", None)
            if describe is not None:
                driver_metadata = describe()
            task_started = time.monotonic()
            task_records: list[TrialRecord] = []
            for trial in range(1, trials + 1):
                # A Chinese IME eats ASCII punctuation ("-"/"."); input-source
                # stickiness is per-app, so pin fresh before every trial.
                pin_ascii_input_source()
                trial_env = dict(bench_env)
                trial_capture = out_dir / "trials" / task.id / str(trial) / "page_capture.jsonl"
                trial_capture.parent.mkdir(parents=True, exist_ok=True)
                trial_capture.write_text("", encoding="utf-8")
                trial_env["BENCH_CAPTURE"] = str(trial_capture)
                if server is not None:
                    trial_env["BENCH_ASSETS_URL"] = server.begin_trial(trial_capture)
                try:
                    record = await _run_trial(
                        driver, task, trial, out_dir, trial_env, server=server,
                    )
                finally:
                    if server is not None:
                        server.end_trial()
                if describe is not None:
                    driver_metadata = describe()
                records.append(record)
                task_records.append(record)
                logger.info(
                    "task=%s trial=%d success=%s steps=%d wall=%.1fs "
                    "llm=%dcalls streamed_ttft=%s/call=%.1fs total=%.1fs",
                    task.id, trial, record.success, record.steps, record.wall_s,
                    record.llm_calls, record.llm_ttft_s, record.llm_call_s,
                    record.llm_total_s,
                )
                if record.cleanup == "unconfirmed":
                    aborted = True
                    break
            passed = sum(1 for r in task_records if r.success)
            logger.info(
                "task=%s done: %d/%d passed in %.1fs",
                task.id, passed, len(task_records), time.monotonic() - task_started,
            )
            if aborted:
                break
    finally:
        if server is not None:
            server.stop()
        restore_saved_input_source()
    logger.info(
        "suite done: %d trials in %.1fs", len(records), time.monotonic() - run_started
    )

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
    )
    task_hash = hashlib.sha256()
    for path in sorted((suite_dir / "tasks").glob("*.yaml")):
        task_hash.update(path.name.encode())
        task_hash.update(path.read_bytes())
    report = replace(aggregate(records), metadata={
        **driver_metadata, "platform": platform, "git_revision": revision.stdout.strip(),
        "task_revision": task_hash.hexdigest(), "scoring_revision": SCORING_REVISION,
        "aborted_cleanup": aborted,
        "outcomes": [{"task": r.task_id, "trial": r.trial, "stop_reason": r.stop_reason,
                      "cleanup": r.cleanup, "scoring": r.scoring, "success": r.success,
                      "unknown_calls": r.unknown_calls} for r in records],
        "limits": [{"task": t.id, "tool_call_limit": t.max_steps,
                    "timeout_s": t.timeout_s, "gui_only": t.gui_only} for t in tasks],
    })
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
    *, server: LocalPageServer | None = None,
) -> TrialRecord:
    trial_dir = out_dir / "trials" / task.id / str(trial)
    trace = TraceSink(trial_dir)
    instruction = task.instruction.replace("${BENCH_ASSETS_URL}", bench_env["BENCH_ASSETS_URL"])
    if task.gui_only:
        instruction += (
            "\n本任务仅允许 GUI 工具操作；"
            "不得调用 shell 或文件工具读取答案或完成任务。\n"
        )
    trace.event("trial_start", task=task.id, trial=trial, instruction=instruction,
                scoring_revision=SCORING_REVISION, scoring=task.scoring, gui_only=task.gui_only)
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
            instruction, trace, timeout_s=task.timeout_s, max_steps=task.max_steps,
        )
        if server is not None:
            server.end_trial()
        timed_out = result.timed_out
        error = result.error

        if result.cleanup == "unconfirmed":
            raise RuntimeError("cleanup unconfirmed; validator and teardown skipped")

        # Verdict by side effects even when the run timed out: the agent's
        # closing narration is not part of the task — if the effect landed,
        # the trial succeeded (A17: validators only check side effects).
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
        if task.gui_only and result.non_gui_tools:
            success = False
            error = "GUI-only task attempted non-GUI tools: " + ", ".join(result.non_gui_tools)
            trace.event("execution_path_failed", tools=result.non_gui_tools)
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
        if server is not None:
            server.end_trial()
        if task.teardown and (result is None or result.cleanup != "unconfirmed"):
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
        scoring=task.scoring,
        llm_rtt_s=result.llm_rtt_s if result else 0.0,
        stop_reason=result.stop_reason if result else "error",
        cleanup=result.cleanup if result else "unknown",
        primitives=result.primitives if result else 0,
        model_turns=result.model_turns if result else 0,
        unknown_calls=result.unknown_calls if result else 0,
        tool_call_limit=task.max_steps, gui_only=task.gui_only,
        non_gui_tools=result.non_gui_tools if result else (),
        llm_calls=result.llm_calls if result else 0,
        llm_ttft_s=result.llm_ttft_s if result else None,
        llm_call_s=result.llm_call_s if result else 0.0,
        llm_total_s=result.llm_total_s if result else 0.0,
    )
    (trial_dir / "result.json").write_text(
        json.dumps(asdict(record), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return record
