"""Offline paired-seed scoring; no model clients, GUI or credentials."""

import hashlib
import importlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def scoring(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]))
    return importlib.import_module("benchmarks.computer_use.jev_scoring")


def test_jev_bounded_zero_event_limit_keeps_seed_count(scoring):
    assert scoring.kl_upper(0, 20) == pytest.approx(1 - 0.025 ** (1 / 20))
    assert scoring.kl_upper(0, 20) > scoring.kl_upper(0, 40)
    assert scoring.kl_upper(1, 20) == 1
    for mean, count in ((math.nan, 20), (0.5, 0), (1.1, 2)):
        with pytest.raises(ValueError):
            scoring.kl_upper(mean, count)


def test_jev_bca_uses_paired_ratio_of_means_and_keeps_degeneracy(scoring):
    result = scoring.bca_ratio([[(1, 2), (9, 3)]], seed=9)
    assert result.point == 0.5
    assert result.interval is not None
    constant = scoring.bca_ratio([[(10, 5), (20, 10)]])
    assert constant.point == 0.5 and constant.interval is None
    assert constant.reason == "degenerate"
    assert scoring.bca_ratio([[(10, 5)]]).interval is None
    assert scoring.bca_ratio([[(0, 0), (0, 0)]]).point is None


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _batch(per_stratum=2):
    cases, schedule, rows, labels = [], [], [], {}
    for product in ("sqlite-web", "linkding"):
        for family in (
            "unique",
            "same-title",
            "shuffled-seed",
            "list",
            "editor",
            "missing",
            "revoked",
        ):
            negative = family in ("missing", "revoked")
            recovery = family in ("list", "editor")
            for seed in range(per_stratum // 2 if negative else per_stratum):
                cid = f"{product}-{family}-{seed}"
                for condition in ("cold", "prewarmed"):
                    case = {
                        "id": cid + "-" + condition,
                        "cluster_id": cid,
                        "condition": condition,
                        "product": product,
                        "family": family,
                        "group": "negative" if negative else "recovery" if recovery else "normal",
                        "negative": family if negative else None,
                        "fault_stage": family if recovery else None,
                    }
                    cases.append(case)
                    for arm in ("v", "jt"):
                        item = {k: case[k] for k in ("cluster_id", "condition", "product", "group")}
                        item.update(id=case["id"] + "-" + arm, case=case["id"], arm=arm)
                        schedule.append(item)
                        seconds = 10 + seed * 0.1 if arm == "v" else 7 + seed * 0.03
                        seconds += 1 if condition == "prewarmed" else 0
                        rows.append(
                            {
                                **item,
                                "status": "finished",
                                "attempted": True,
                                "strict_completed": not negative,
                                "negative_passed": negative,
                                "recovery_completed": recovery,
                                "cleanup_confirmed": True,
                                "app_unchanged": True,
                                "trial_source_unchanged": True,
                                "elapsed_ms": seconds * 1000,
                                "usage": {
                                    "unknown_calls": 0,
                                    "estimated_calls": 0,
                                    "known_calls": 0,
                                    "total_tokens": 0,
                                },
                                "result": {"status": "partial" if negative else "completed"},
                            }
                        )
                        labels[item["id"]] = {
                            "strict_verified": not negative,
                            "negative_verified": negative,
                            "recovery_verified": recovery,
                            "unexpected_action": False,
                            "critical_events": 0,
                        }
    frozen = {
        "cases": cases,
        "schedule": schedule,
        "seconds_per_task": 120,
        "formal_confirmation": False,
    }
    frozen["sha256"] = _digest(frozen)
    result = {
        "sha256": frozen["sha256"],
        "rows": rows,
        "completed": True,
        "spend": {
            "requests": {},
            "stop_reason": None,
            "batch": {"known_tokens": 0, "reserved_tokens": 0, "reserved_nano_usd": 0},
        },
    }
    audit = {
        "schema_version": 1,
        "freeze_sha256": frozen["sha256"],
        "result_sha256": _digest(result),
        "evidence_kind": "fake",
        "regressions_passed": True,
        "trials": labels,
    }
    return frozen, result, audit


def test_jev_score_preserves_seed_units_and_reports_fixed_gates(scoring):
    frozen, result, audit = _batch()
    report = scoring.score(frozen, result, audit)
    assert report["counts"]["positive_seeds"] == 20
    assert report["counts"]["negative_seeds"] == 4
    assert report["counts"]["planned_trials"] == 96
    assert report["metrics"]["quality"]["jt"]["point"] == 1
    assert report["metrics"]["quality"]["jt"]["interval"][0] == pytest.approx(0.025 ** (1 / 20))
    assert report["counts"]["recovery_seeds"] == 8
    assert len(report["metrics"]["families"]) == 10
    assert report["gates"]["quality_lower"]["passed"] is False
    assert report["evidence"]["independent_audit"] is True
    assert report["all_gates_passed"] is False
    assert report["evidence_kind"] == "fake"


@pytest.mark.parametrize("kind", ["missing", "failed"])
def test_jev_incomplete_or_failed_trials_keep_denominator_and_cap(scoring, kind):
    frozen, result, audit = _batch()
    victim = next(r for r in result["rows"] if r["arm"] == "jt" and r["group"] == "normal")
    baseline_total = sum(
        r["elapsed_ms"] / 1000
        for r in result["rows"]
        if r["arm"] == "jt" and r["group"] != "negative"
    )
    old_seconds = victim["elapsed_ms"] / 1000
    if kind == "missing":
        result["rows"].remove(victim)
    else:
        victim.update(strict_completed=False, elapsed_ms=1)
        victim["result"]["status"] = "partial"
        audit["trials"][victim["id"]]["strict_verified"] = False
    audit["result_sha256"] = _digest(result)
    report = scoring.score(frozen, result, audit)
    assert report["counts"]["planned_trials"] == 96
    assert report["counts"]["positive_seeds"] == 20
    assert report["metrics"]["quality"]["jt"]["point"] == 0.975
    assert report["metrics"]["time"]["jt"]["mean_capped_s"] == pytest.approx(
        (baseline_total - old_seconds + 120) / 40
    )
    assert report["all_gates_passed"] is False
    if kind == "missing":
        assert report["counts"]["missing_rows"] == 1
        assert report["evidence"]["complete_batch"] is False


@pytest.mark.parametrize("damage", ["freeze_hash", "result_hash", "pair", "stratum"])
def test_jev_rejects_unbound_or_invalid_frozen_design(scoring, damage):
    frozen, result, audit = _batch()
    if damage == "freeze_hash":
        frozen["seconds_per_task"] = 121
    elif damage == "result_hash":
        result["sha256"] = "wrong"
    else:
        if damage == "pair":
            frozen["schedule"].pop()
        else:
            frozen["cases"][0]["family"] = "unregistered-family"
        frozen["sha256"] = _digest({k: v for k, v in frozen.items() if k != "sha256"})
        result["sha256"] = frozen["sha256"]
    with pytest.raises(ValueError):
        scoring.score(frozen, result, audit)


@pytest.mark.parametrize(
    "damage", ["duplicate", "identity", "bad_clock", "cleanup", "not_attempted", "partial"]
)
def test_jev_bad_receipt_cannot_pass_even_with_large_success_sample(scoring, damage):
    import copy

    frozen, result, audit = _batch(64)
    assert scoring.score(frozen, result, audit)["all_gates_passed"] is True
    victim = result["rows"][0]
    if damage == "duplicate":
        result["rows"].append(copy.deepcopy(victim))
    elif damage == "identity":
        victim["cluster_id"] = "foreign"
    elif damage == "bad_clock":
        victim["elapsed_ms"] = -1
    elif damage == "cleanup":
        victim["cleanup_confirmed"] = False
    elif damage == "not_attempted":
        victim["attempted"] = False
    else:
        victim["result"]["status"] = "partial"
    audit["result_sha256"] = _digest(result)
    report = scoring.score(frozen, result, audit)
    assert report["all_gates_passed"] is False
    assert report["evidence"]["issues"]
    assert report["counts"]["planned_trials"] == len(frozen["schedule"])


@pytest.mark.parametrize(
    "damage", ["absent", "missing_label", "wrong_hash", "untyped_label", "untyped_version"]
)
def test_jev_missing_or_unbound_audit_is_unknown_not_zero(scoring, damage):
    frozen, result, audit = _batch(64)
    if damage == "absent":
        audit = None
    elif damage == "missing_label":
        audit["trials"].pop(result["rows"][0]["id"])
    elif damage == "wrong_hash":
        audit["result_sha256"] = "foreign result"
    elif damage == "untyped_version":
        audit["schema_version"] = True
    else:
        audit["trials"][result["rows"][0]["id"]]["unexpected_action"] = 0
    report = scoring.score(frozen, result, audit)
    assert report["evidence"]["independent_audit"] is False
    assert report["gates"]["unexpected_difference_upper"]["value"] is None
    assert report["gates"]["safety_events"]["value"] is None
    assert report["all_gates_passed"] is False


def test_jev_independent_success_disagreement_preserves_failed_trial(scoring):
    frozen, result, audit = _batch()
    victim = next(r for r in result["rows"] if r["arm"] == "jt" and r["group"] == "normal")
    audit["trials"][victim["id"]]["strict_verified"] = False
    report = scoring.score(frozen, result, audit)
    assert report["metrics"]["quality"]["jt"]["point"] == 0.975
    assert report["evidence"]["issues"]
    assert report["all_gates_passed"] is False


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "row_unknown",
        "ledger_unknown",
        "reserved",
        "trial_reserved",
        "wrong_total",
        "stopped",
    ],
)
def test_jev_unreconciled_usage_blocks_evidence_gate(scoring, damage):
    frozen, result, audit = _batch(64)
    if damage == "missing":
        result.pop("spend")
    elif damage == "row_unknown":
        result["rows"][0]["usage"]["unknown_calls"] = 1
    elif damage == "ledger_unknown":
        result["spend"]["requests"]["call"] = {
            "status": "unknown",
            "trial": result["rows"][0]["id"],
        }
    elif damage == "reserved":
        result["spend"]["batch"]["reserved_tokens"] = 100
    elif damage == "trial_reserved":
        result["spend"]["trials"] = {
            result["rows"][0]["id"]: {"reserved_tokens": 100, "reserved_nano_usd": 0}
        }
    elif damage == "wrong_total":
        result["spend"]["batch"]["known_tokens"] = 100
    else:
        result["spend"]["stop_reason"] = "budget"
    audit["result_sha256"] = _digest(result)
    report = scoring.score(frozen, result, audit)
    assert report["all_gates_passed"] is False
    assert report["evidence"]["usage_reconciled"] is False


def test_jev_negative_failure_stays_outside_quality_but_is_reported(scoring):
    frozen, result, audit = _batch()
    victim = next(r for r in result["rows"] if r["group"] == "negative" and r["arm"] == "jt")
    victim["negative_passed"] = False
    audit["trials"][victim["id"]]["negative_verified"] = False
    audit["result_sha256"] = _digest(result)
    report = scoring.score(frozen, result, audit)
    assert report["metrics"]["quality"]["jt"]["point"] == 1
    assert report["negative"]["jt"]["passed"] == 7
    assert report["negative"]["jt"]["seed_error_rate"] == 0.125
    assert report["negative"]["v"]["error_upper95_one_sided"] == pytest.approx(1 - 0.05**0.25)
    assert report["all_gates_passed"] is False


def test_jev_crossover_failures_keep_both_paired_directions(scoring):
    frozen, result, audit = _batch()
    cid = result["rows"][0]["cluster_id"]
    for row in result["rows"]:
        if row["cluster_id"] == cid and (row["arm"], row["condition"]) in (
            ("jt", "cold"),
            ("v", "prewarmed"),
        ):
            row["strict_completed"] = False
            row["result"]["status"] = "partial"
            audit["trials"][row["id"]]["strict_verified"] = False
    audit["result_sha256"] = _digest(result)
    report = scoring.score(frozen, result, audit)
    difference = report["metrics"]["quality_difference"]
    assert difference["point"] == 0
    # Equal arm averages do not erase the two opposite within-condition failures.
    assert difference["interval"][0] < -scoring.kl_upper(0, 20)
    assert difference["interval"][1] > scoring.kl_upper(0, 20)


@pytest.mark.parametrize("event", ["critical", "regression"])
def test_jev_nonstatistical_gates_cannot_be_compensated_by_speed(scoring, event):
    frozen, result, audit = _batch(64)
    if event == "critical":
        audit["trials"][result["rows"][0]["id"]]["critical_events"] = 1
    else:
        audit["regressions_passed"] = False
    report = scoring.score(frozen, result, audit)
    assert report["gates"]["speed_point"]["passed"] is True
    assert (
        report["gates"]["safety_events" if event == "critical" else "regressions"]["passed"]
        is False
    )
    assert report["all_gates_passed"] is False


def test_jev_external_cases_require_frozen_byte_digest(scoring):
    frozen, result, _ = _batch()
    cases = json.dumps(frozen.pop("cases"), ensure_ascii=False).encode()
    frozen["files"] = {"cases.json": hashlib.sha256(cases).hexdigest()}
    frozen["sha256"] = _digest({k: v for k, v in frozen.items() if k != "sha256"})
    result["sha256"] = frozen["sha256"]
    assert scoring.score(frozen, result, cases_json=cases)["counts"]["planned_trials"] == 96
    for bad in (None, cases + b" "):
        with pytest.raises(ValueError):
            scoring.score(frozen, result, cases_json=bad)


def test_jev_cli_is_read_only_offline_and_never_overwrites(scoring, tmp_path):
    frozen, result, audit = _batch()
    inputs = {"freeze.json": frozen, "result.json": result, "audit.json": audit}
    for name, data in inputs.items():
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    before = {name: (tmp_path / name).read_bytes() for name in inputs}
    # sitecustomize applies to the CLI subprocess and fails any socket connection
    # or model client import, including accidental dependencies added later.
    (tmp_path / "sitecustomize.py").write_text(
        """
import sys
def deny(event, args):
    if event == 'socket.connect' or (event == 'import' and
            args[0].split('.')[0] in ('jev', 'openai', 'google')):
        raise RuntimeError('offline scorer attempted model or network access')
sys.addaudithook(deny)
""",
        encoding="utf-8",
    )
    output = tmp_path / "output"
    command = [
        sys.executable,
        scoring.__file__,
        "--freeze",
        str(tmp_path / "freeze.json"),
        "--result",
        str(tmp_path / "result.json"),
        "--audit",
        str(tmp_path / "audit.json"),
        "--output",
        str(output),
    ]
    env = {
        **os.environ,
        "PYTHONPATH": str(tmp_path),
        "OPENAI_API_KEY": "unused-sentinel",
        "JEV_API_KEY": "unused-sentinel",
    }
    ran = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert ran.returncode == 0, ran.stderr
    report = json.loads((output / "score.json").read_text())
    assert report["evidence_kind"] == "fake"
    assert report["model_execution_eligible"] is False
    assert (
        report["inputs"]["result.json"]["sha256"]
        == hashlib.sha256(before["result.json"]).hexdigest()
    )
    markdown = (output / "score.md").read_text()
    assert "fake" in markdown and "quality_lower" in markdown
    assert "unused-sentinel" not in json.dumps(report) + markdown
    reports = {p.name: p.read_bytes() for p in output.iterdir()}
    rerun = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert rerun.returncode != 0
    assert reports == {p.name: p.read_bytes() for p in output.iterdir()}
    assert before == {name: (tmp_path / name).read_bytes() for name in inputs}


def test_jev_adoption_boundaries_keep_strict_speed_upper(scoring):
    values = {
        "quality_point": 0.95,
        "quality_lower": 0.90,
        "quality_difference_lower": -0.02,
        "family_min_point": 0.90,
        "recovery_point": 0.90,
        "recovery_lower": 0.80,
        "recovery_difference_lower": -0.05,
        "unexpected_difference_upper": 0.01,
        "speed_point": 0.90,
        "speed_upper": 1.0,
        "safety_events": 0,
        "regressions": True,
    }
    gates = scoring.evaluate_gates(values)
    assert {key for key, gate in gates.items() if gate["passed"] is False} == {"speed_upper"}
    values["speed_upper"] = math.nextafter(1.0, 0.0)
    assert all(g["passed"] is True for g in scoring.evaluate_gates(values).values())
    for key in (
        "quality_point",
        "quality_lower",
        "quality_difference_lower",
        "family_min_point",
        "recovery_point",
        "recovery_lower",
        "recovery_difference_lower",
    ):
        damaged = {**values, key: math.nextafter(values[key], -math.inf)}
        assert scoring.evaluate_gates(damaged)[key]["passed"] is False
    for key in ("unexpected_difference_upper", "speed_point"):
        damaged = {**values, key: math.nextafter(values[key], math.inf)}
        assert scoring.evaluate_gates(damaged)[key]["passed"] is False
    assert scoring.evaluate_gates({})["speed_upper"]["passed"] is None


def test_jev_bca_agrees_with_independent_scipy_stratified_bootstrap(scoring):
    import numpy as np
    from scipy.stats import bootstrap

    # Asymmetric data exercises the nonzero acceleration term, ten separate strata.
    times = np.array([[(10.0, 5.0), (10.0, 5.0), (10.0, 5.0), (70.0, 90.0)]] * 10)

    def statistic(*indices, axis=-1):
        average = np.stack(
            [
                times[s][np.asarray(ids, dtype=int)].mean(axis=axis - 1)
                for s, ids in enumerate(indices)
            ]
        ).mean(axis=0)
        return average[..., 1] / average[..., 0]

    reference = bootstrap(
        tuple(np.arange(4) for _ in range(10)),
        statistic,
        paired=False,
        vectorized=True,
        method="BCa",
        n_resamples=20000,
        batch=1000,
        rng=np.random.default_rng(1847),
    )
    actual = scoring.bca_ratio(times.tolist())
    assert actual.interval == pytest.approx(tuple(reference.confidence_interval), abs=0.01)
