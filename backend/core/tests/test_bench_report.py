"""Tests for benchmark aggregation (success rate, Wilson CI, medians)."""

from __future__ import annotations

import json
import math

from tank_backend.benchmarks.report import (
    TaskStats,
    TrialRecord,
    aggregate,
    wilson_interval,
    write_json_report,
    write_markdown_report,
)


def _record(task: str, ok: bool, *, steps: int = 10, wall_s: float = 30.0,
            tokens: int = 1000, shots: int = 5, error: str | None = None,
            llm_calls: int = 4, llm_ttft_s: float = 2.0,
            llm_call_s: float = 6.0, llm_total_s: float = 24.0) -> TrialRecord:
    return TrialRecord(
        task_id=task, trial=1, success=ok, error=error,
        steps=steps, wall_s=wall_s, tokens=tokens, screenshots=shots,
        timed_out=False,
        llm_calls=llm_calls, llm_ttft_s=llm_ttft_s,
        llm_call_s=llm_call_s, llm_total_s=llm_total_s,
    )


# ── Wilson interval ──────────────────────────────────────────────────


def test_wilson_all_success():
    lo, hi = wilson_interval(3, 3)
    # Lower bound is well below 1 even for a perfect score
    assert lo < 1.0 and hi == 1.0


def test_wilson_known_value():
    # 7/10 at z=1.96 → ≈ (0.3926, 0.9127) — canonical worked example
    lo, hi = wilson_interval(7, 10)
    assert math.isclose(lo, 0.3475, abs_tol=0.01) or math.isclose(lo, 0.3926, abs_tol=0.01)
    assert hi > 0.85


def test_wilson_zero_trials():
    lo, hi = wilson_interval(0, 0)
    assert (lo, hi) == (0.0, 0.0)


# ── aggregation ──────────────────────────────────────────────────────


def test_aggregate_per_task_and_overall():
    records = [
        _record("a", True, steps=10, wall_s=20.0, tokens=100),
        _record("a", True, steps=20, wall_s=40.0, tokens=300),
        _record("a", False, steps=30, wall_s=60.0, tokens=500),
        _record("b", True, steps=5, wall_s=10.0, tokens=50),
    ]
    report = aggregate(records)
    assert report.total_trials == 4
    assert report.successes == 3
    a = report.tasks["a"]
    assert isinstance(a, TaskStats)
    assert a.trials == 3 and a.successes == 2
    assert a.success_rate == 2 / 3
    assert a.medians["steps"] == 20
    assert a.medians["wall_s"] == 40.0
    assert a.medians["tokens"] == 300
    assert report.tasks["b"].successes == 1


def test_aggregate_includes_llm_latency_medians():
    records = [
        _record("a", True, llm_calls=2, llm_ttft_s=1.0, llm_call_s=5.0, llm_total_s=10.0),
        _record("a", True, llm_calls=4, llm_ttft_s=3.0, llm_call_s=7.0, llm_total_s=28.0),
        _record("a", False, llm_calls=6, llm_ttft_s=2.0, llm_call_s=6.0, llm_total_s=36.0),
    ]
    a = aggregate(records).tasks["a"]
    assert a.medians["llm_calls"] == 4
    assert a.medians["llm_ttft_s"] == 2.0
    assert a.medians["llm_call_s"] == 6.0
    assert a.medians["llm_total_s"] == 28.0


def test_aggregate_empty():
    report = aggregate([])
    assert report.total_trials == 0
    assert report.tasks == {}


# ── writers ──────────────────────────────────────────────────────────


def test_markdown_report_contains_table(tmp_path):
    records = [_record("a", True), _record("a", False, error="validator failed")]
    report = aggregate(records)
    out = tmp_path / "report.md"
    write_markdown_report(report, out, title="A17 baseline", label="baseline-macos")
    text = out.read_text(encoding="utf-8")
    assert "A17 baseline" in text
    assert "| a |" in text
    assert "baseline-macos" in text
    assert "LLM latency" in text
    assert "ttft" in text


def test_json_report_roundtrip(tmp_path):
    records = [_record("a", True)]
    report = aggregate(records)
    out = tmp_path / "report.json"
    write_json_report(report, out, label="x")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["label"] == "x"
    assert data["tasks"]["a"]["trials"] == 1
    assert data["overall"]["successes"] == 1
