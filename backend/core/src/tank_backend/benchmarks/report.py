"""Trial records, aggregation, and report writers."""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

_Z_95 = 1.96


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """Wilson score interval (95%) for a binomial proportion."""
    if trials <= 0:
        return 0.0, 0.0
    p = successes / trials
    denom = 1 + _Z_95**2 / trials
    center = (p + _Z_95**2 / (2 * trials)) / denom
    margin = (_Z_95 / denom) * math.sqrt(
        p * (1 - p) / trials + _Z_95**2 / (4 * trials**2)
    )
    return max(0.0, center - margin), min(1.0, center + margin)


@dataclass(frozen=True)
class TrialRecord:
    """The outcome of one benchmark trial."""

    task_id: str
    trial: int
    success: bool
    error: str | None
    steps: int
    wall_s: float
    tokens: int
    screenshots: int
    timed_out: bool
    # LLM latency (see DriverResult); defaults keep older constructors valid.
    llm_calls: int = 0
    llm_ttft_s: float = 0.0
    llm_call_s: float = 0.0
    llm_total_s: float = 0.0


@dataclass(frozen=True)
class TaskStats:
    trials: int
    successes: int
    success_rate: float
    ci_lo: float
    ci_hi: float
    medians: dict[str, float]


@dataclass(frozen=True)
class SuiteReport:
    total_trials: int
    successes: int
    success_rate: float
    ci_lo: float
    ci_hi: float
    tasks: dict[str, TaskStats]
    # Suite-level LLM latency: API calls (model round-trips) across all
    # trials, median ttft of trial medians, total-weighted mean per call,
    # and total seconds spent in LLM calls.
    llm_calls_total: int = 0
    llm_ttft_s: float = 0.0
    llm_call_s_mean: float = 0.0
    llm_total_s: float = 0.0


def _median(records: list[TrialRecord], key: str) -> float:
    values = [float(getattr(r, key)) for r in records]
    return statistics.median(values) if values else 0.0


def aggregate(records: list[TrialRecord]) -> SuiteReport:
    """Aggregate trial records into per-task stats and an overall score."""
    by_task: dict[str, list[TrialRecord]] = {}
    for r in records:
        by_task.setdefault(r.task_id, []).append(r)

    task_stats: dict[str, TaskStats] = {}
    for task_id, recs in by_task.items():
        successes = sum(1 for r in recs if r.success)
        lo, hi = wilson_interval(successes, len(recs))
        task_stats[task_id] = TaskStats(
            trials=len(recs),
            successes=successes,
            success_rate=successes / len(recs),
            ci_lo=lo,
            ci_hi=hi,
            medians={
                k: _median(recs, k)
                for k in (
                    "steps", "wall_s", "tokens", "screenshots",
                    "llm_calls", "llm_ttft_s", "llm_call_s", "llm_total_s",
                )
            },
        )

    total = len(records)
    successes = sum(1 for r in records if r.success)
    lo, hi = wilson_interval(successes, total)
    llm_calls_total = sum(r.llm_calls for r in records)
    llm_total_s = sum(r.llm_total_s for r in records)
    return SuiteReport(
        total_trials=total,
        successes=successes,
        success_rate=(successes / total) if total else 0.0,
        ci_lo=lo,
        ci_hi=hi,
        tasks=task_stats,
        llm_calls_total=llm_calls_total,
        llm_ttft_s=statistics.median([r.llm_ttft_s for r in records]) if records else 0.0,
        llm_call_s_mean=(llm_total_s / llm_calls_total) if llm_calls_total else 0.0,
        llm_total_s=llm_total_s,
    )


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def write_markdown_report(
    report: SuiteReport, out: Path, *, title: str, label: str
) -> None:
    lines = [
        f"# {title}",
        "",
        f"- Run label: `{label}`",
        f"- Overall: **{report.successes}/{report.total_trials}** "
        f"({_fmt_pct(report.success_rate)}, 95% CI "
        f"{_fmt_pct(report.ci_lo)}–{_fmt_pct(report.ci_hi)})",
        "",
        "| task | pass | rate | 95% CI | steps (med) | wall s (med) | tokens (med) | shots (med) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for task_id in sorted(report.tasks):
        t = report.tasks[task_id]
        lines.append(
            f"| {task_id} | {t.successes}/{t.trials} | {_fmt_pct(t.success_rate)} "
            f"| {_fmt_pct(t.ci_lo)}–{_fmt_pct(t.ci_hi)} "
            f"| {t.medians['steps']:.0f} | {t.medians['wall_s']:.0f} "
            f"| {t.medians['tokens']:.0f} | {t.medians['screenshots']:.0f} |"
        )

    # Per-call LLM latency — the knob to turn when comparing providers.
    lines += [
        "",
        "## LLM latency (per call)",
        "",
        "| task | calls (med) | ttft s (med) | call s (med) | llm total s (med) |",
        "|---|---|---|---|---|",
    ]
    for task_id in sorted(report.tasks):
        t = report.tasks[task_id]
        lines.append(
            f"| {task_id} | {t.medians['llm_calls']:.0f} "
            f"| {t.medians['llm_ttft_s']:.1f} | {t.medians['llm_call_s']:.1f} "
            f"| {t.medians['llm_total_s']:.0f} |"
        )
    lines += [
        "",
        f"- API calls total: {report.llm_calls_total}, "
        f"mean {report.llm_call_s_mean:.1f}s/call, "
        f"median ttft {report.llm_ttft_s:.1f}s, "
        f"LLM time total {report.llm_total_s:.0f}s",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json_report(report: SuiteReport, out: Path, *, label: str) -> None:
    payload = {
        "label": label,
        "overall": {
            "trials": report.total_trials,
            "successes": report.successes,
            "success_rate": report.success_rate,
            "ci_lo": report.ci_lo,
            "ci_hi": report.ci_hi,
            "llm": {
                "calls_total": report.llm_calls_total,
                "ttft_s_median": report.llm_ttft_s,
                "call_s_mean": report.llm_call_s_mean,
                "total_s": report.llm_total_s,
            },
        },
        "tasks": {tid: asdict(t) for tid, t in sorted(report.tasks.items())},
    }
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
