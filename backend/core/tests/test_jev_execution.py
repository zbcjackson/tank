"""Supplemental calibration admission; every test is offline."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def execution():
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(Path(__file__).parents[2]))
        yield importlib.import_module("benchmarks.computer_use.jev_execution")


@pytest.fixture(scope="module")
def prepared(execution, tmp_path_factory):
    root = tmp_path_factory.mktemp("prepared") / "execution"
    execution.prepare(root)
    return root


def verification_receipt(root, frozen):
    checks = {}
    for name in (
        "backend_pytest",
        "backend_ruff",
        "pyright",
        "web_lint",
        "web_tsc_b",
        "cli_ruff",
        "dev_logs",
        "e2e",
        "docs",
    ):
        path = root / (name + ".log")
        path.write_text("passed\n")
        checks[name] = {
            "log": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "exit_code": 0,
        }
    receipt = {"schema_version": 1, "source_sha256": frozen["source_sha256"], "checks": checks}
    path = root / "verification.json"
    path.write_text(json.dumps(receipt))
    return path, receipt


def test_prepare_freezes_full_execution_and_distinct_offline_prefix(execution, prepared):
    root = prepared
    frozen = json.loads((root / "freeze.json").read_text())
    assert len(frozen["cases"]) == 1824 and len(frozen["schedule"]) == 3648
    assert len(frozen["source_sha256"]) == 42
    assert frozen["formal_N"] is None and frozen["formal_confirmation"] is False
    assert frozen["budget"] == {
        "record_only": True,
        "request_limit": None,
        "token_limit": None,
        "nano_usd_limit": None,
        "price_status": "unpriced",
        "unknown_usage": "stop",
        "pending_reservations": "stop",
    }
    assert execution.load_freeze(root, frozen["sha256"]) == frozen
    prefix = json.loads((root / "qualification-freeze.json").read_text())
    assert len(prefix["cases"]) == 96 and len(prefix["schedule"]) == 192
    assert prefix["parent_execution_sha256"] == frozen["sha256"]
    assert execution.load_freeze(root, prefix["sha256"], fake=True) == prefix
    with pytest.raises(ValueError):
        execution.load_freeze(root, prefix["sha256"])
    with pytest.raises(ValueError):
        execution.load_freeze(root, frozen["sha256"], fake=True)
    with pytest.raises(FileExistsError):
        execution.prepare(root)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "goal",
        "critical",
        "cleanup",
        "usage",
        "unknown_effect",
        "operation",
        "cancel",
        "source_drift",
        "pending",
    ],
)
async def test_batch_completion_and_hard_stop_preserve_denominators(
    execution,
    prepared,
    tmp_path,
    monkeypatch,
    failure,
):
    import asyncio
    import shutil

    from benchmarks.computer_use import jev_audit as audit
    from benchmarks.computer_use import jev_calibration_route as calibration

    from tank_backend.benchmarks.spend_ledger import SpendLimit, TokenAllowance

    root = tmp_path / "run"
    shutil.copytree(prepared, root)
    frozen = json.loads((root / "qualification-freeze.json").read_text())
    failed = frozen["schedule"][0]["id"]
    attempted = []

    async def task(case, arm, output, *, ledger, **kwargs):
        identity = case["id"] + "-" + arm
        attempted.append(identity)
        ledger.start_trial(identity, SpendLimit(0, 0))
        if failure == "pending":
            ledger.reserve("pending", TokenAllowance(0, 0, 0, 0))
        else:
            ledger.finish_trial()
        good = failure != "goal" or identity != failed
        row = {
            "id": identity,
            "case": case["id"],
            "arm": arm,
            "status": "finished",
            "task_id": identity,
            "cleanup_confirmed": True,
            "calls": [],
            "events": [],
            "strict_completed": good and not case["negative"],
            "negative_passed": good and bool(case["negative"]),
            "recovery_completed": good and case["recovery"],
            "usage": {
                k: 0
                for k in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "known_calls",
                    "estimated_tokens",
                    "estimated_calls",
                    "unknown_calls",
                )
            },
        }
        if failure == "cancel":
            path = output / identity
            path.mkdir()
            (path / "row.json").write_text(json.dumps({**row, "status": "cancelled"}))
            raise asyncio.CancelledError
        if failure == "operation":
            raise RuntimeError("local fixture failed")
        if failure == "usage":
            row["usage"]["total_tokens"] = 1
        if failure == "cleanup":
            row["cleanup_confirmed"] = False
        return row

    def label(case, row, path):
        if failure == "unknown_effect":
            raise audit.EvidenceError("unknown action effect")
        good = failure != "goal" or row["id"] != failed
        return {
            "strict_verified": good and not case["negative"],
            "negative_verified": good and bool(case["negative"]),
            "recovery_verified": good and case["recovery"],
            "unexpected_action": False,
            "critical_events": 1 if failure == "critical" else 0,
        }

    loads = []

    def load(*args, **kwargs):
        loads.append(True)
        if failure == "source_drift" and len(loads) > 2:
            raise ValueError("source changed before next trial")
        return frozen

    monkeypatch.setattr(calibration, "run_task", task)
    monkeypatch.setattr(audit, "audit_trial", label)
    monkeypatch.setattr(execution, "load_freeze", load)
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await execution.run_batch(root, frozen["sha256"], fake=True)
        result = json.loads((root / "fake/result.json").read_text())
        assert result["rows"][0]["cleanup_confirmed"] is True
        assert result["rows"][0]["status"] == "cancelled"
    else:
        result = await execution.run_batch(root, frozen["sha256"], fake=True)
    assert len(result["rows"]) == 192
    assert result["qualified"] is False
    if failure == "goal":
        assert attempted == [s["id"] for s in frozen["schedule"]]
        assert result["completed"] is True and result["spend"]["stop_reason"] is None
        with pytest.raises(FileExistsError):
            await execution.run_batch(root, frozen["sha256"], fake=True)
    else:
        assert attempted == [failed]
        assert result["completed"] is False and result["spend"]["stop_reason"] is not None
        assert sum(row["status"] == "not_run" for row in result["rows"]) == 191


def test_sdk_completions_reconcile_with_events_and_ledger(execution, tmp_path):
    from benchmarks.computer_use.jev_audit import EvidenceError

    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, TokenAllowance

    row: dict = {"id": "case-jt", "case": "case", "task_id": "task", "calls": [], "events": []}
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True)
    ledger.start_trial("case-jt", SpendLimit(0, 0))
    journal = []
    for identity, visual in (("first", True), ("second", False)):
        call = {"call_id": identity, "request": {"messages": []} if visual else {}, "images": []}
        response = (
            {"usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
            if visual
            else {"input_tokens": 7, "output_tokens": 3}
        )
        row["calls"].append(call)
        journal.extend([call, {"call_id": identity, "response": response}])
        row["events"].extend(
            [
                {"kind": "model_call", "phase": "started", "call_id": identity, "task_id": "task"},
                {
                    "kind": "model_call",
                    "phase": "finished",
                    "call_id": identity,
                    "task_id": "task",
                    "status": "returned",
                    "prompt_tokens": 7,
                    "completion_tokens": 3,
                },
            ]
        )
        ledger.reserve(identity, TokenAllowance(0, 0, 0, 0))
        ledger.settle(identity, input_tokens=7, output_tokens=3)
    ledger.finish_trial()
    row["usage"] = {
        "prompt_tokens": 14,
        "completion_tokens": 6,
        "total_tokens": 20,
        "known_calls": 2,
        "estimated_calls": 0,
        "estimated_tokens": 0,
        "unknown_calls": 0,
    }
    path = tmp_path / "calls.jsonl"
    path.write_text("".join(json.dumps(line) + "\n" for line in journal))
    execution.audit_usage(row, ledger.snapshot(), tmp_path)
    journal[-1]["response"]["input_tokens"] = 8
    path.write_text("".join(json.dumps(line) + "\n" for line in journal))
    with pytest.raises(EvidenceError):
        execution.audit_usage(row, ledger.snapshot(), tmp_path)
    ledger.close()


@pytest.mark.asyncio
async def test_live_schedule_stops_and_retains_all_3648_rows(
    execution,
    prepared,
    tmp_path,
    monkeypatch,
):
    import shutil

    from benchmarks.computer_use import jev_calibration_route as calibration

    root = tmp_path / "live-run"
    shutil.copytree(prepared, root)
    frozen = json.loads((root / "freeze.json").read_text())
    admitted = []
    attempted = []

    def admission(path, approved, verification):
        admitted.append((path, approved, verification))
        return {"ready_for_authorization": True}

    async def broken_product(case, arm, output, **kwargs):
        attempted.append(case["id"] + "-" + arm)
        raise RuntimeError("owned local product failed before any model call")

    monkeypatch.setattr(execution, "preflight", admission, raising=False)
    monkeypatch.setattr(calibration, "run_task", broken_product)
    monkeypatch.setattr(execution, "load_freeze", lambda *args, **kwargs: frozen)
    verification = tmp_path / "receipt.json"
    result = await execution.run_batch(
        root,
        frozen["sha256"],
        verification=verification,
        jev_credential="explicit-test-only",
        peer_credential="explicit-test-only",
    )
    assert admitted == [(root, frozen["sha256"], verification)]
    assert attempted == [frozen["schedule"][0]["id"]]
    assert len(result["rows"]) == 3648
    assert sum(row["attempted"] for row in result["rows"]) == 1
    assert sum(row["status"] == "not_run" for row in result["rows"]) == 3647
    assert result["completed"] is False and result["spend"]["stop_reason"] == "operational_error"
    assert result["external_model_requests"] is None


def test_verification_logs_must_bind_sources_and_integer_success(execution, tmp_path):
    frozen = {"source_sha256": {"runtime.py": "current"}}
    path, receipt = verification_receipt(tmp_path, frozen)
    checks = receipt["checks"]
    execution.verify_checks(frozen, path)
    checks["backend_pytest"]["exit_code"] = False
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        execution.verify_checks(frozen, path)
    checks["backend_pytest"]["exit_code"] = 0
    path.write_text(json.dumps(receipt))
    (tmp_path / "docs.log").write_text("changed after receipt\n")
    with pytest.raises(ValueError):
        execution.verify_checks(frozen, path)


def test_closed_nonattempt_audit_cannot_admit_live_execution(
    execution,
    prepared,
    tmp_path,
):
    import shutil

    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit

    root = tmp_path / "incomplete"
    shutil.copytree(prepared, root)
    frozen = json.loads((root / "qualification-freeze.json").read_text())
    full = json.loads((root / "freeze.json").read_text())
    output = root / "fake"
    output.mkdir()
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True)
    ledger.close()
    rows = [{**slot, "attempted": False, "status": "not_run"} for slot in frozen["schedule"]]
    result = {
        "sha256": frozen["sha256"],
        "mode": "fake-only",
        "rows": rows,
        "spend": ledger.snapshot(),
        "completed": False,
        "qualified": False,
        "external_model_requests": 0,
        "blocked_external_attempts": [],
        "logical_sdk_calls": 0,
        "fake_sdk_calls": 0,
        "fake_image_calls": 0,
    }

    def digest(value):
        return hashlib.sha256(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()

    for name, value in {
        "result.json": result,
        "started.json": {"sha256": frozen["sha256"], "planned_ids": [s["id"] for s in rows]},
        "closed.json": {
            "sha256": frozen["sha256"],
            "result_sha256": digest(result),
            "attempted_ids": [],
            "driver_context_ended": True,
            "fake_http_context_ended": True,
        },
    }.items():
        (output / name).write_text(json.dumps(value))
    (output / "transport.jsonl").write_text("")
    verification, _ = verification_receipt(tmp_path, frozen)
    audit = execution.build_audit(root, frozen["sha256"], verification, fake=True)
    assert audit["evidence_kind"] == "fake" and audit["regressions_passed"] is True
    assert len(audit["trials"]) == 192
    assert all(label["strict_verified"] is False for label in audit["trials"].values())
    (output / "audit.json").write_text(json.dumps(audit))
    with pytest.raises(ValueError):
        execution.preflight(root, full["sha256"], verification)
    result["spend"]["batch"]["known_tokens"] = 1
    (output / "result.json").write_text(json.dumps(result))
    closed = json.loads((output / "closed.json").read_text())
    closed["result_sha256"] = digest(result)
    (output / "closed.json").write_text(json.dumps(closed))
    with pytest.raises(ValueError):
        execution.build_audit(root, frozen["sha256"], verification, fake=True)


def test_execution_cli_refuses_before_reading_credentials(execution, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("credentials read before admission")

    monkeypatch.setattr("dotenv.dotenv_values", forbidden)
    with pytest.raises(SystemExit) as stopped:
        execution.main(
            [
                "run",
                "--root",
                str(tmp_path),
                "--approved-sha",
                "0" * 64,
                "--verification",
                str(tmp_path / "missing.json"),
            ]
        )
    assert stopped.value.code == 2
    assert not (tmp_path / "live").exists()


@pytest.mark.parametrize("damage", ["source", "proof", "budget"])
def test_execution_input_tamper_is_rejected(execution, prepared, tmp_path, damage):
    import shutil

    root = tmp_path / "tampered"
    shutil.copytree(prepared, root)
    frozen = json.loads((root / "qualification-freeze.json").read_text())
    if damage == "source":
        (root / "source/benchmarks/computer_use/jev_execution.py").write_text("changed source")
    elif damage == "proof":
        (root / "prior-proof.json").write_text("{}")
    else:
        frozen["budget"]["record_only"] = False
        (root / "qualification-freeze.json").write_text(json.dumps(frozen))
    with pytest.raises(ValueError):
        execution.load_freeze(root, frozen["sha256"], fake=True)


def test_new_runtime_source_drift_is_rejected(execution, prepared, tmp_path, monkeypatch):
    shadow = tmp_path / "backend"
    path = shadow / "benchmarks/computer_use/jev_execution.py"
    path.parent.mkdir(parents=True)
    path.write_text("changed runtime implementation")
    frozen = json.loads((prepared / "freeze.json").read_text())
    monkeypatch.setattr(execution, "BACKEND", shadow)
    with pytest.raises(ValueError):
        execution.load_freeze(prepared, frozen["sha256"])


@pytest.mark.asyncio
async def test_transport_admission_failure_retains_zero_attempts_and_stop_reason(
    execution,
    prepared,
    tmp_path,
    monkeypatch,
):
    import shutil

    from benchmarks.computer_use import jev_fake_http

    root = tmp_path / "transport-failure"
    shutil.copytree(prepared, root)
    frozen = json.loads((root / "qualification-freeze.json").read_text())
    monkeypatch.setattr(execution, "load_freeze", lambda *args, **kwargs: frozen)

    def fail(*args, **kwargs):
        raise OSError("cannot open offline transport evidence")

    monkeypatch.setattr(jev_fake_http, "offline_http", fail)
    with pytest.raises(OSError):
        await execution.run_batch(root, frozen["sha256"], fake=True)
    result = json.loads((root / "fake/result.json").read_text())
    assert len(result["rows"]) == 192 and not any(r["attempted"] for r in result["rows"])
    assert result["spend"]["stop_reason"] == "operational_error"
    assert result["logical_sdk_calls"] == 0
    closed = json.loads((root / "fake/closed.json").read_text())
    assert closed["fake_http_context_ended"] is False
