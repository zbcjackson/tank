"""Trial and batch reservations share one conservative spend ledger."""

import pytest


def test_batch_http_limit_persists_across_trials_and_usage_refunds(tmp_path):
    import json

    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )

    path = tmp_path / "spend.jsonl"
    ledger = SpendLedger(SpendLimit(100, 1000), journal=path, request_limit=2)
    for trial in ("A", "D"):
        ledger.start_trial(trial, SpendLimit(100, 1000))
        ledger.reserve(trial, TokenAllowance(30, 20, 2, 5))
        ledger.settle(trial, input_tokens=0, output_tokens=0)
        ledger.finish_trial()
    ledger.start_trial("later", SpendLimit(100, 1000))
    with pytest.raises(SpendLimitExceeded, match="batch_requests"):
        ledger.reserve("third", TokenAllowance(0, 0, 0, 0))
    ledger.close()
    saved = json.loads(path.read_text().splitlines()[-1])
    assert saved["batch"]["admitted_requests"] == 2
    assert saved["batch"]["limit_requests"] == 2
    assert saved["batch"]["charged_tokens"] == 0
    assert "third" not in saved["requests"]
    assert saved["stop_reason"] == "batch_requests"


@pytest.mark.parametrize("value", [-1, True, 1.5, "2"])
def test_batch_request_limit_rejects_invalid_values(value):
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit

    with pytest.raises(ValueError):
        SpendLedger(SpendLimit(100, 1000), request_limit=value)


def test_durable_reservation_is_readable_before_send_and_cannot_be_replayed(tmp_path):
    import json

    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance

    path = tmp_path / "spend.jsonl"
    ledger = SpendLedger(SpendLimit(100, 1000), journal=path)
    ledger.start_trial("A", SpendLimit(60, 600))
    ledger.reserve("request", TokenAllowance(30, 20, 2, 5))
    saved = json.loads(path.read_text().splitlines()[-1])
    assert saved["batch"]["reserved_tokens"] == 50
    assert saved["requests"]["request"]["status"] == "pending"
    with pytest.raises(FileExistsError):
        SpendLedger(SpendLimit(100, 1000), journal=path)
    ledger.finish_trial()
    ledger.close()
    saved = json.loads(path.read_text().splitlines()[-1])
    assert saved["requests"]["request"]["status"] == "unknown"
    assert saved["batch"]["reserved_tokens"] == 50
    assert saved["stop_reason"] == "unknown_usage"


@pytest.mark.parametrize("operation", ["reserve", "settle"])
def test_journal_sync_failure_stops_admission(monkeypatch, tmp_path, operation):
    import os

    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )

    ledger = SpendLedger(SpendLimit(100, 1000), journal=tmp_path / "spend.jsonl")
    ledger.start_trial("A", SpendLimit(100, 1000))
    if operation == "settle":
        ledger.reserve("request", TokenAllowance(30, 20, 2, 5))

    def fail_sync(fd):
        raise OSError("disk failure")

    with monkeypatch.context() as failure:
        failure.setattr(os, "fsync", fail_sync)
        with pytest.raises(SpendLimitExceeded, match="persistence_error"):
            if operation == "reserve":
                ledger.reserve("request", TokenAllowance(30, 20, 2, 5))
            else:
                ledger.settle("request", input_tokens=3, output_tokens=2)
    with pytest.raises(SpendLimitExceeded, match="persistence_error"):
        ledger.reserve("next", TokenAllowance(1, 1, 1, 1))
    ledger.close()


def test_closed_journal_rejects_all_mutations(tmp_path):
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded

    ledger = SpendLedger(SpendLimit(100, 1000), journal=tmp_path / "spend.jsonl")
    ledger.close()
    ledger.close()
    with pytest.raises(SpendLimitExceeded, match="ledger_closed"):
        ledger.start_trial("A", SpendLimit(100, 1000))
    with pytest.raises(SpendLimitExceeded, match="ledger_closed"):
        ledger.finish_trial()
    with pytest.raises(SpendLimitExceeded, match="ledger_closed"):
        ledger.stop("later")


def test_process_exit_leaves_synced_pending_reservation(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit

    path = tmp_path / "spend.jsonl"
    result = subprocess.run(
        [sys.executable, "-c", """
import os, sys
from pathlib import Path
from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance
ledger = SpendLedger(SpendLimit(100, 1000), journal=Path(sys.argv[1]))
ledger.start_trial('A', SpendLimit(60, 600))
ledger.reserve('request', TokenAllowance(30, 20, 2, 5))
os._exit(17)
""", str(path)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 17, result.stderr
    saved = json.loads(path.read_text().splitlines()[-1])
    assert saved["requests"]["request"]["status"] == "pending"
    assert saved["batch"]["reserved_tokens"] == 50
    with pytest.raises(FileExistsError):
        SpendLedger(SpendLimit(100, 1000), journal=path)


def test_known_usage_releases_only_unused_reservation_across_trials():
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        TokenAllowance,
    )

    ledger = SpendLedger(SpendLimit(tokens=100, nano_usd=1000))
    ledger.start_trial("A", SpendLimit(tokens=60, nano_usd=600))
    allowance = TokenAllowance(
        input_tokens=30, output_tokens=20, input_nano_usd=2, output_nano_usd=5
    )
    ledger.reserve("request-1", allowance)
    assert ledger.snapshot()["batch"]["charged_tokens"] == 50
    assert ledger.snapshot()["batch"]["charged_nano_usd"] == 160
    ledger.settle("request-1", input_tokens=10, output_tokens=5)
    assert ledger.snapshot()["batch"]["charged_tokens"] == 15
    assert ledger.snapshot()["batch"]["charged_nano_usd"] == 45
    ledger.finish_trial()
    ledger.start_trial("D", SpendLimit(tokens=60, nano_usd=600))
    ledger.reserve("request-2", allowance)
    assert ledger.snapshot()["batch"]["charged_tokens"] == 65
    assert ledger.snapshot()["trials"]["D"]["charged_tokens"] == 50


@pytest.mark.parametrize(
    "scope,dimension",
    [
        ("batch", "tokens"),
        ("batch", "nano_usd"),
        ("trial", "tokens"),
        ("trial", "nano_usd"),
    ],
)
def test_admission_checks_both_limits_before_mutating(scope, dimension):
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )

    small = SpendLimit(**{dimension: 10, "nano_usd" if dimension == "tokens" else "tokens": 100})
    large = SpendLimit(tokens=100, nano_usd=100)
    ledger = SpendLedger(small if scope == "batch" else large)
    ledger.start_trial("A", small if scope == "trial" else large)
    ledger.reserve("one", TokenAllowance(5, 5, 1, 1))  # Exact boundary is allowed.
    ledger.settle("one", input_tokens=5, output_tokens=5)
    before = ledger.snapshot()["batch"]
    with pytest.raises(SpendLimitExceeded, match=f"{scope}_{dimension}"):
        ledger.reserve("two", TokenAllowance(1, 0, 1, 1))
    assert ledger.snapshot()["batch"] == before
    with pytest.raises(SpendLimitExceeded):
        ledger.reserve("smaller", TokenAllowance(0, 0, 0, 0))
    ledger.finish_trial()
    with pytest.raises(SpendLimitExceeded):
        ledger.start_trial("B", large)


@pytest.mark.parametrize("usage", [(None, None), (3, None), (None, 4)])
def test_unknown_usage_retains_full_allowance_and_stops_batch(usage):
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )

    ledger = SpendLedger(SpendLimit(100, 1000))
    ledger.start_trial("A", SpendLimit(100, 1000))
    ledger.reserve("failed", TokenAllowance(30, 20, 2, 5))
    ledger.settle("failed", input_tokens=usage[0], output_tokens=usage[1])
    snapshot = ledger.snapshot()
    assert snapshot["stop_reason"] == "unknown_usage"
    assert snapshot["batch"]["charged_tokens"] == 50
    assert snapshot["batch"]["charged_nano_usd"] == 160
    assert snapshot["batch"]["known_tokens"] == 0
    assert snapshot["batch"]["reserved_tokens"] == 50
    assert snapshot["requests"]["failed"]["status"] == "unknown"
    with pytest.raises(SpendLimitExceeded, match="unknown_usage"):
        ledger.reserve("later", TokenAllowance(1, 1, 1, 1))


@pytest.mark.parametrize("value", [-1, True, 1.5, "10"])
@pytest.mark.parametrize(
    "field",
    ["tokens", "nano_usd", "input_tokens", "output_tokens", "input_nano_usd", "output_nano_usd"],
)
def test_limits_and_allowances_require_nonnegative_integers(field, value):
    from tank_backend.benchmarks.spend_ledger import SpendLimit, TokenAllowance

    if field in ("tokens", "nano_usd"):
        values = {"tokens": 100, "nano_usd": 100}
        values[field] = value
        with pytest.raises(ValueError):
            SpendLimit(**values)
    else:
        values = {
            "input_tokens": 10,
            "output_tokens": 10,
            "input_nano_usd": 1,
            "output_nano_usd": 1,
        }
        values[field] = value
        with pytest.raises(ValueError):
            TokenAllowance(**values)


@pytest.mark.parametrize("value", [-1, True, 1.5, "10"])
@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
def test_malformed_usage_retains_reservation_and_stops(field, value):
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance

    ledger = SpendLedger(SpendLimit(100, 1000))
    ledger.start_trial("A", SpendLimit(100, 1000))
    ledger.reserve("malformed", TokenAllowance(20, 10, 2, 3))
    usage = {"input_tokens": 1, "output_tokens": 1}
    usage[field] = value
    ledger.settle("malformed", **usage)
    snapshot = ledger.snapshot()
    assert snapshot["stop_reason"] == "invalid_usage"
    assert snapshot["batch"]["reserved_tokens"] == 30
    assert snapshot["batch"]["reserved_nano_usd"] == 70


def test_serial_lifecycle_prevents_duplicate_charges_and_closes_unfinished_request():
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance

    ledger = SpendLedger(SpendLimit(100, 1000))
    allowance = TokenAllowance(20, 10, 2, 3)
    with pytest.raises(ValueError):
        ledger.reserve("outside", allowance)
    ledger.start_trial("A", SpendLimit(100, 1000))
    with pytest.raises(ValueError):
        ledger.start_trial("B", SpendLimit(100, 1000))
    ledger.reserve("one", allowance)
    with pytest.raises(ValueError):
        ledger.reserve("overlap", allowance)
    ledger.settle("one", input_tokens=0, output_tokens=0)
    snapshot = ledger.snapshot()
    with pytest.raises(ValueError):
        ledger.settle("one", input_tokens=1, output_tokens=1)
    with pytest.raises(ValueError):
        ledger.reserve("one", allowance)
    assert ledger.snapshot() == snapshot
    ledger.finish_trial()
    with pytest.raises(ValueError):
        ledger.start_trial("A", SpendLimit(100, 1000))
    ledger.start_trial("B", SpendLimit(100, 1000))
    ledger.reserve("cancelled", allowance)
    ledger.finish_trial()  # Finally path when transport raises or is cancelled.
    snapshot = ledger.snapshot()
    assert snapshot["stop_reason"] == "unknown_usage"
    assert snapshot["batch"]["reserved_tokens"] == 30
    assert snapshot["batch"]["reserved_nano_usd"] == 70
    with pytest.raises(ValueError):
        ledger.settle("cancelled", input_tokens=0, output_tokens=0)
    assert ledger.snapshot() == snapshot


@pytest.mark.parametrize("usage", [(11, 1), (1, 11), (101, 101)])
def test_bound_violation_preserves_actual_usage_without_clamping(usage):
    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )

    ledger = SpendLedger(SpendLimit(100, 1000))
    ledger.start_trial("A", SpendLimit(100, 1000))
    ledger.reserve("bad-bound", TokenAllowance(10, 10, 2, 5))
    ledger.settle("bad-bound", input_tokens=usage[0], output_tokens=usage[1])
    snapshot = ledger.snapshot()
    assert snapshot["stop_reason"] == "bound_exceeded"
    assert snapshot["batch"]["known_tokens"] == sum(usage)
    assert snapshot["batch"]["known_nano_usd"] == usage[0] * 2 + usage[1] * 5
    assert snapshot["batch"]["reserved_tokens"] == 0
    assert snapshot["requests"]["bad-bound"]["status"] == "bound_exceeded"
    with pytest.raises(SpendLimitExceeded):
        ledger.reserve("later", TokenAllowance(1, 1, 1, 1))


@pytest.mark.parametrize("dimension", ["tokens", "nano_usd"])
def test_later_trial_cannot_reset_batch_spend_with_different_prices(dimension):
    import json

    from tank_backend.benchmarks.spend_ledger import (
        SpendLedger,
        SpendLimit,
        SpendLimitExceeded,
        TokenAllowance,
    )

    limit = SpendLimit(
        tokens=100 if dimension == "tokens" else 1000,
        nano_usd=100 if dimension == "nano_usd" else 1000,
    )
    ledger = SpendLedger(limit)
    ledger.start_trial("A", limit)
    ledger.reserve("flash", TokenAllowance(40, 20, 1, 1))
    ledger.settle("flash", input_tokens=40, output_tokens=20)
    ledger.finish_trial()
    archived = ledger.snapshot()
    ledger.start_trial("D", limit)
    allowance = (
        TokenAllowance(30, 20, 1, 1) if dimension == "tokens" else TokenAllowance(10, 10, 2, 3)
    )
    with pytest.raises(SpendLimitExceeded, match=f"batch_{dimension}"):
        ledger.reserve("max", allowance)
    snapshot = ledger.snapshot()
    assert snapshot["trials"]["D"]["charged_tokens"] == 0
    assert snapshot["batch"]["known_tokens"] == 60
    assert "max" not in snapshot["requests"]
    assert "D" not in archived["trials"]
    assert json.loads(json.dumps(snapshot)) == snapshot


def test_nano_usd_accounting_is_exact_beyond_float_precision():
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance

    price = 2**53 + 1
    ledger = SpendLedger(SpendLimit(10, price * 10))
    ledger.start_trial("A", SpendLimit(10, price * 10))
    ledger.reserve("one", TokenAllowance(2, 3, price, price + 1))
    assert ledger.snapshot()["batch"]["reserved_nano_usd"] == price * 5 + 3
    ledger.settle("one", input_tokens=1, output_tokens=1)
    assert ledger.snapshot()["batch"]["known_nano_usd"] == price * 2 + 1


@pytest.mark.parametrize("usage,charged,cost", [(30, 40, 90), (3, 30, 70)])
@pytest.mark.parametrize("output", [None, "bad"])
def test_partial_usage_keeps_observed_overrun_as_well_as_unknown_reserve(
    usage,
    charged,
    cost,
    output,
):
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance

    ledger = SpendLedger(SpendLimit(100, 1000))
    ledger.start_trial("A", SpendLimit(100, 1000))
    ledger.reserve("partial", TokenAllowance(20, 10, 2, 3))
    ledger.settle("partial", input_tokens=usage, output_tokens=output)
    snapshot = ledger.snapshot()
    assert snapshot["requests"]["partial"]["input_tokens"] == usage
    assert snapshot["stop_reason"] == (
        "bound_exceeded" if usage > 20 else "unknown_usage" if output is None else "invalid_usage"
    )
    assert snapshot["batch"]["charged_tokens"] == charged
    assert snapshot["batch"]["reserved_nano_usd"] == cost
    assert snapshot["batch"]["known_tokens"] == 0
