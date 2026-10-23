"""New-bank qualification and independent evidence contracts; no paid models."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def qualification(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]))
    return importlib.import_module("benchmarks.computer_use.jev_qualification")


def test_registered_prefix_keeps_fixed_cases_and_original_order(qualification):
    registered = qualification.registration()
    cases, slots = qualification.prefix(registered)
    assert len(registered["cases"]) == 1824
    assert len(cases) == 96 and len(slots) == 192
    assert len({c["cluster_id"] for c in cases}) == 48
    assert sum(not c["negative"] for c in cases) == 80
    ids = {c["id"] for c in cases}
    assert slots == [s for s in registered["schedule"] if s["case"] in ids]
    assert all(c["reserved_rank"] < (2 if c["negative"] else 4) for c in cases)
    assert all(c["id"].startswith("supp-cal-v1-") for c in cases)


@pytest.fixture
def products(qualification):
    original = qualification.registration()["original"]["apps"]
    paths = [Path(original["sqlite-web"]["python"]), Path(original["linkding"]["python"])]
    if not all(p.is_file() for p in paths):
        pytest.skip("qualified product environments required")


def test_execution_freezes_bind_new_bank_and_both_scopes(qualification, products, tmp_path):
    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    assert len(frozen["cases"]) == 96 and len(frozen["schedule"]) == 192
    assert frozen["registration_sha256"] == qualification.REGISTRATION_SHA
    assert frozen["model_execution_eligible"] is False
    assert qualification.load_freeze(root, frozen["sha256"]) == frozen
    import json

    candidate = json.loads((root / "execution-freeze.json").read_text())
    assert len(candidate["cases"]) == 1824 and len(candidate["schedule"]) == 3648
    assert qualification.load_freeze(root, candidate["sha256"], candidate=True) == candidate
    with pytest.raises(ValueError):
        qualification.load_freeze(root, candidate["sha256"])
    with pytest.raises(FileExistsError):
        qualification.prepare(root)


@pytest.mark.parametrize(
    "damaged", ["cases.json", "source/benchmarks/computer_use/jev_qualification.py"]
)
def test_frozen_input_or_saved_source_tamper_fails(qualification, products, tmp_path, damaged):
    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    path = root / damaged
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError):
        qualification.load_freeze(root, frozen["sha256"])


def test_independent_physical_reader_keeps_schema_and_all_business_tables(qualification, tmp_path):
    import sqlite3

    audit = importlib.import_module("benchmarks.computer_use.jev_audit")
    path = tmp_path / "physical.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE work_items (id INTEGER PRIMARY KEY, title TEXT, notes TEXT)")
        db.execute("CREATE TABLE _writes (operation TEXT, id INTEGER)")
        db.execute("INSERT INTO work_items VALUES (1,'old','preserved')")
    before = path.read_bytes()
    actual = audit.physical(path, "sqlite-web")
    assert actual["tables"]["work_items"] == [{"id": 1, "title": "old", "notes": "preserved"}]
    assert actual["tables"]["_writes"] == []
    assert len(actual["schema"]) == 2
    assert path.read_bytes() == before


def test_independent_html_readback_keeps_record_identity_and_business_fields(qualification):
    audit = importlib.import_module("benchmarks.computer_use.jev_audit")
    sql = (
        '<table class="cell-content"><thead><tr><th></th><th data-col="id">id</th>'
        '<th data-col="title">title</th><th data-col="notes">notes</th></tr></thead>'
        "<tbody><tr><td>Edit</td><td>4</td><td>Approved value</td><td>keep</td></tr>"
        "</tbody></table>"
    )
    assert audit.list_rows(sql, "sqlite-web") == [
        {"id": "4", "title": "Approved value", "notes": "keep"}
    ]
    link = (
        '<ul><li data-bookmark-id="4"><span class="title">'
        '<a href="https://example.test/4">Approved value</a></span>'
        '<div class="description">keep | unchanged</div></li></ul>'
    )
    assert audit.list_rows(link, "linkding") == [
        {
            "id": "4",
            "title": "Approved value",
            "url": "https://example.test/4",
            "description": "keep | unchanged",
        }
    ]


def test_fake_reply_chooses_only_public_target_identity(qualification):
    http = importlib.import_module("benchmarks.computer_use.jev_fake_http")
    packet = {
        "state": {
            "goal": {
                "goal_id": "new-goal",
                "outcomes": [{"conditions": [{"key": "status:Editor seen:4"}]}],
            }
        },
        "questions": {
            "next_action": {
                "criteria": {
                    "wrong": {
                        "operation": "click",
                        "role": "link",
                        "label": "Edit",
                        "ancestors": [["row", "1 duplicate title"]],
                        "effect": [],
                    },
                    "right": {
                        "operation": "click",
                        "role": "link",
                        "label": "Edit",
                        "ancestors": [["row", "4 duplicate title"]],
                        "effect": [],
                    },
                    "none": "none",
                }
            }
        },
    }
    assert http.choose(packet) == "right"
    packet["state"]["goal"]["outcomes"][0]["conditions"][0]["key"] = "status:Editor seen:99"
    assert http.choose(packet) == "none"


@pytest.mark.asyncio
async def test_batch_continues_known_failure_and_keeps_all_planned_rows(
    qualification, products, tmp_path, monkeypatch
):
    from benchmarks.computer_use import jev_audit as audit
    from benchmarks.computer_use import jev_calibration_route as calibration

    from tank_backend.benchmarks.spend_ledger import SpendLimit

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    monkeypatch.setattr(qualification, "load_freeze", lambda *args, **kwargs: frozen)
    attempted = []

    async def task(case, arm, output, *, ledger, **kwargs):
        identity = case["id"] + "-" + arm
        ledger.start_trial(identity, SpendLimit(0, 0))
        ledger.finish_trial()
        attempted.append(identity)
        good = len(attempted) != 1
        return {
            "id": identity,
            "case": case["id"],
            "arm": arm,
            "status": "finished",
            "strict_completed": good and not case["negative"],
            "negative_passed": good and bool(case["negative"]),
            "recovery_completed": good and case["recovery"],
            "cleanup_confirmed": True,
            "app_unchanged": True,
            "trial_source_unchanged": True,
            "elapsed_ms": 10,
            "calls": [],
            "events": [],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_tokens": 0,
                "unknown_calls": 0,
                "estimated_calls": 0,
                "known_calls": 0,
                "total_tokens": 0,
            },
            "result": {"status": "completed" if good else "partial"},
        }

    def independent(case, row, path):
        return {
            "strict_verified": row["strict_completed"],
            "negative_verified": row["negative_passed"],
            "recovery_verified": row["recovery_completed"],
            "unexpected_action": False,
            "critical_events": 0,
        }

    monkeypatch.setattr(calibration, "run_task", task)
    monkeypatch.setattr(audit, "audit_trial", independent)
    result = await qualification.run_fake(root, frozen["sha256"])
    assert len(result["rows"]) == len(attempted) == 192
    assert result["completed"] is True and result["qualified"] is False
    assert result["spend"]["stop_reason"] is None
    assert result["rows"][0]["strict_completed"] is False


@pytest.mark.asyncio
async def test_batch_stops_on_missing_independent_evidence(
    qualification, products, tmp_path, monkeypatch
):
    from benchmarks.computer_use import jev_audit as audit
    from benchmarks.computer_use import jev_calibration_route as calibration

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    monkeypatch.setattr(qualification, "load_freeze", lambda *args, **kwargs: frozen)

    async def task(case, arm, output, **kwargs):
        return {
            "status": "finished",
            "strict_completed": True,
            "cleanup_confirmed": True,
            "usage": {"unknown_calls": 0, "estimated_calls": 0},
        }

    def missing(*args):
        raise audit.EvidenceError("missing cleanup proof")

    monkeypatch.setattr(calibration, "run_task", task)
    monkeypatch.setattr(audit, "audit_trial", missing)
    result = await qualification.run_fake(root, frozen["sha256"])
    assert len(result["rows"]) == 192
    assert sum(r["attempted"] for r in result["rows"]) == 1
    assert sum(r["status"] == "not_run" for r in result["rows"]) == 191
    assert (
        result["completed"] is False and result["spend"]["stop_reason"] == "audit_evidence_missing"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["total", "missing", "boolean"])
async def test_batch_stops_before_next_trial_when_row_and_ledger_usage_disagree(
    qualification, products, tmp_path, monkeypatch, failure
):
    from benchmarks.computer_use import jev_audit as audit
    from benchmarks.computer_use import jev_calibration_route as calibration

    from tank_backend.benchmarks.spend_ledger import SpendLimit

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    monkeypatch.setattr(qualification, "load_freeze", lambda *args, **kwargs: frozen)
    attempted = []

    async def task(case, arm, output, *, ledger, **kwargs):
        identity = case["id"] + "-" + arm
        attempted.append(identity)
        ledger.start_trial(identity, SpendLimit(0, 0))
        ledger.finish_trial()
        row = {
            "status": "finished",
            "cleanup_confirmed": True,
            "calls": [],
            "events": [],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "estimated_tokens": 0,
                "unknown_calls": 0,
                "estimated_calls": 0,
                "known_calls": 0,
                "total_tokens": 1 if failure == "total" else 0,
            },
        }
        if failure == "missing":
            del row["usage"]["known_calls"]
        elif failure == "boolean":
            row["usage"]["known_calls"] = False
        return row

    monkeypatch.setattr(calibration, "run_task", task)
    monkeypatch.setattr(
        audit,
        "audit_trial",
        lambda *args: {
            "critical_events": 0,
            "unexpected_action": False,
            "strict_verified": False,
            "negative_verified": False,
            "recovery_verified": False,
        },
    )
    result = await qualification.run_fake(root, frozen["sha256"])
    assert len(attempted) == 1
    assert sum(r["status"] == "not_run" for r in result["rows"]) == 191
    assert result["spend"]["stop_reason"] == "usage_mismatch"
    assert result["qualified"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["event_usage", "call_id", "trial_id", "transport_count", "transport_goal", "transport_usage"],
)
async def test_batch_reconciles_call_events_and_fake_transport_before_next_trial(
    qualification, products, tmp_path, monkeypatch, failure
):
    from contextlib import contextmanager

    import httpx
    from benchmarks.computer_use import jev_audit as audit
    from benchmarks.computer_use import jev_calibration_route as calibration
    from benchmarks.computer_use import jev_fake_http

    from tank_backend.benchmarks.spend_ledger import SpendLimit, TokenAllowance

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    monkeypatch.setattr(qualification, "load_freeze", lambda *args, **kwargs: frozen)
    original = jev_fake_http.offline_http
    wire = {}

    @contextmanager
    def capture(*args):
        with original(*args) as summary:
            wire.update(summary=summary)
            yield summary

    attempted = []

    async def task(case, arm, output, *, ledger, **kwargs):
        identity = case["id"] + "-" + arm
        attempted.append(identity)
        call = identity + "-call"
        ledger.start_trial(identity + ("-wrong" if failure == "trial_id" else ""), SpendLimit(0, 0))
        ledger.reserve(
            call + ("-wrong" if failure == "call_id" else ""), TokenAllowance(0, 0, 0, 0)
        )
        request = {
            "state": {"goal": case["goal"]},
            "questions": {"next_action": {"criteria": {"none": "none"}}},
        }
        async with httpx.AsyncClient() as client:
            await client.post("https://network-forbidden.invalid", json=request)
        ledger.settle(
            call + ("-wrong" if failure == "call_id" else ""), input_tokens=7, output_tokens=3
        )
        ledger.finish_trial()
        if failure == "transport_count":
            wire["summary"]["requests"].clear()
        elif failure == "transport_goal":
            wire["summary"]["requests"][-1]["goal_id"] = "different-goal"
        elif failure == "transport_usage":
            wire["summary"]["requests"][-1]["usage"] = {"input_tokens": 6, "output_tokens": 4}
        return {
            "task_id": identity,
            "status": "finished",
            "strict_completed": False,
            "cleanup_confirmed": True,
            "calls": [{"call_id": call, "request": request, "images": []}],
            "events": [
                {"kind": "model_call", "phase": "started", "call_id": call, "task_id": identity},
                {
                    "kind": "model_call",
                    "phase": "finished",
                    "call_id": call,
                    "task_id": identity,
                    "status": "returned",
                    "prompt_tokens": 6 if failure == "event_usage" else 7,
                    "completion_tokens": 3,
                },
            ],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 3,
                "estimated_tokens": 0,
                "unknown_calls": 0,
                "estimated_calls": 0,
                "known_calls": 1,
                "total_tokens": 10,
            },
        }

    monkeypatch.setattr(jev_fake_http, "offline_http", capture)
    monkeypatch.setattr(calibration, "run_task", task)
    monkeypatch.setattr(
        audit,
        "audit_trial",
        lambda *args: {
            "critical_events": 0,
            "unexpected_action": False,
            "strict_verified": False,
            "negative_verified": False,
            "recovery_verified": False,
        },
    )
    result = await qualification.run_fake(root, frozen["sha256"])
    assert len(attempted) == 1
    assert sum(r["status"] == "not_run" for r in result["rows"]) == 191
    assert result["spend"]["stop_reason"] == "usage_mismatch"


def test_complete_audit_requires_bound_checks_and_closed_nonattempt_proof(
    qualification, products, tmp_path
):
    import hashlib
    import json

    from benchmarks.computer_use import jev_audit as audit
    from benchmarks.computer_use import jev_scoring as scoring

    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    output = root / "fake"
    output.mkdir()
    ledger = SpendLedger(SpendLimit(0, 0), record_only=True)
    ledger.stop("cancelled")
    ledger.close()
    rows = [
        {
            **slot,
            "status": "not_run",
            "attempted": False,
            "strict_completed": False,
            "negative_passed": False,
            "recovery_completed": False,
            "cleanup_confirmed": False,
        }
        for slot in frozen["schedule"]
    ]
    result = {
        "sha256": frozen["sha256"],
        "mode": "fake-only",
        "rows": rows,
        "completed": False,
        "spend": ledger.snapshot(),
    }
    qualification.save(output / "result.json", result)
    qualification.save(
        output / "started.json",
        {"sha256": frozen["sha256"], "planned_ids": [r["id"] for r in rows]},
    )
    qualification.save(
        output / "closed.json",
        {
            "sha256": frozen["sha256"],
            "result_sha256": qualification.digest(result),
            "attempted_ids": [],
            "transport_context_ended": True,
        },
    )
    (output / "transport.jsonl").write_text("")
    receipt = root / "verification.json"
    with pytest.raises(audit.EvidenceError):
        audit.build_audit(root, frozen["sha256"], receipt)

    names = (
        "backend_pytest",
        "backend_ruff",
        "pyright",
        "web_lint",
        "web_tsc_b",
        "cli_ruff",
        "dev_logs",
        "e2e",
        "docs",
    )
    checks = {}
    for name in names:
        log = root / (name + ".log")
        log.write_text("synthetic unit fixture verification evidence\n")
        checks[name] = {
            "exit_code": 0,
            "log": log.name,
            "sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        }
    verification = {
        "source_sha256": frozen["source_sha256"],
        "checks": checks,
        "kind": "synthetic-test-fixture",
    }
    receipt.write_text(json.dumps(verification))
    doc = audit.build_audit(root, frozen["sha256"], receipt)
    assert doc["schema_version"] == 1 and type(doc["schema_version"]) is int
    assert doc["result_sha256"] == qualification.digest(result) and doc["evidence_kind"] == "fake"
    assert len(doc["trials"]) == 192 and all(
        v["critical_events"] == 0 for v in doc["trials"].values()
    )
    report = scoring.score(frozen, result, doc)
    assert report["evidence"]["independent_audit"] is True
    assert report["counts"]["planned_trials"] == 192 and report["all_gates_passed"] is False
    checks["backend_pytest"]["exit_code"] = False
    receipt.write_text(json.dumps(verification))
    with pytest.raises(audit.EvidenceError):
        audit.build_audit(root, frozen["sha256"], receipt)
    checks["backend_pytest"]["exit_code"] = 0
    receipt.write_text(json.dumps(verification))
    (output / "closed.json").unlink()
    with pytest.raises(audit.EvidenceError):
        audit.build_audit(root, frozen["sha256"], receipt)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["critical", "usage", "pending", "cleanup"])
async def test_batch_hard_stops_before_second_trial(
    qualification, products, tmp_path, monkeypatch, failure
):
    from benchmarks.computer_use import jev_audit as audit
    from benchmarks.computer_use import jev_calibration_route as calibration

    from tank_backend.benchmarks.spend_ledger import SpendLimit, TokenAllowance

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    monkeypatch.setattr(qualification, "load_freeze", lambda *args, **kwargs: frozen)

    async def task(case, arm, output, *, ledger, **kwargs):
        if failure == "pending":
            ledger.start_trial(case["id"] + "-" + arm, SpendLimit(0, 0))
            ledger.reserve("pending-call", TokenAllowance(1, 1, 1, 1))
        return {
            "status": "finished",
            "strict_completed": False,
            "cleanup_confirmed": failure != "cleanup",
            "usage": {"unknown_calls": 1 if failure == "usage" else 0, "estimated_calls": 0},
        }

    def label(*args):
        return {
            "strict_verified": False,
            "negative_verified": False,
            "recovery_verified": False,
            "unexpected_action": False,
            "critical_events": 1 if failure == "critical" else 0,
        }

    monkeypatch.setattr(calibration, "run_task", task)
    monkeypatch.setattr(audit, "audit_trial", label)
    result = await qualification.run_fake(root, frozen["sha256"])
    assert len(result["rows"]) == 192 and sum(r["attempted"] for r in result["rows"]) == 1
    assert sum(r["status"] == "not_run" for r in result["rows"]) == 191
    assert result["spend"]["stop_reason"] == (
        "critical_safety"
        if failure == "critical"
        else "cleanup_unknown"
        if failure == "cleanup"
        else "unknown_usage"
    )
    if failure == "pending":
        assert result["external_model_requests"] is None


@pytest.mark.asyncio
async def test_native_failure_retains_all_fixed_goals(
    qualification, products, tmp_path, monkeypatch
):
    from benchmarks.computer_use import jev_native_qualification as native

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    monkeypatch.setattr(qualification, "load_freeze", lambda *args, **kwargs: frozen)

    async def fail(*args):
        raise RuntimeError("fixture failed before a row returned")

    monkeypatch.setattr(native, "run_case", fail)
    result = await native.run(root, frozen["sha256"])
    assert len(result["rows"]) == 96
    assert sum(r["status"] == "error" for r in result["rows"]) == 1
    assert sum(r["status"] == "not_run" for r in result["rows"]) == 95
    assert result["completed"] is False


def test_standalone_both_official_sdks_use_only_fake_http(qualification, tmp_path):
    import os
    import subprocess
    import sys

    script = tmp_path / "probe.py"
    script.write_text("""
import asyncio,base64,io,json,socket
from PIL import Image
from openai import AsyncOpenAI
from typesafe_sdk import AsyncTypeSafeClient,Choice
from benchmarks.computer_use.jev_fake_http import offline_http,reply
from pathlib import Path
def forbidden(*args,**kwargs):
    raise AssertionError('standalone SDK probe attempted DNS/network')
socket.getaddrinfo=forbidden
goal={'goal_id':'probe','outcomes':[{'conditions':[{'key':'status:Editor seen:4'}]}]}
packet={'state':{'goal':goal},
        'questions':{'next_action':{'criteria':{'c1':{'operation':'fill','role':'textbox','label':'title'},'none':'none'}}}}
async def run():
    png=io.BytesIO();Image.new('RGB',(1280,720)).save(png,format='PNG')
    uri='data:image/png;base64,'+base64.b64encode(png.getvalue()).decode()
    with offline_http(reply,Path(__file__).with_suffix('.jsonl')) as seen:
        seen['active_trial']='probe'
        async with AsyncTypeSafeClient(api_key='qualification-fake',
            base_url='https://network-forbidden.invalid',compression=False) as client:
            await client.system_one(state=packet['state'],questions={
                'next_action':Choice(criteria=packet['questions']['next_action']['criteria'])})
        async with AsyncOpenAI(api_key='qualification-fake',
            base_url='https://network-forbidden.invalid/v1',max_retries=0) as client:
            await client.chat.completions.create(model='probe',messages=[
                {'role':'system','content':'fixture'},
                {'role':'user','content':[{'type':'text','text':json.dumps(packet)},
                    {'type':'image_url','image_url':{'url':uri}}]}])
        assert len(seen['requests'])==2 and not seen['blocked_external']
        assert {r['provider'] for r in seen['requests']}=={'jev','peer'}
    print('two_sdk_fake_responses')
asyncio.run(run())
""")
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[2]),
            "OPENAI_API_KEY": "unused-sentinel",
            "TYPESAFE_API_KEY": "unused-sentinel",
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "two_sdk_fake_responses" in result.stdout
    assert "unused-sentinel" not in result.stdout + result.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["cancel", "drift"])
async def test_interruption_preserves_planned_denominator(
    qualification, products, tmp_path, monkeypatch, failure
):
    import asyncio
    import json

    from benchmarks.computer_use import jev_calibration_route as calibration

    root = tmp_path / "qualification"
    frozen = qualification.prepare(root)
    count = 0

    def load(*args, **kwargs):
        nonlocal count
        count += 1
        if count > 1 and failure == "drift":
            raise ValueError("fixture drift")
        return frozen

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(qualification, "load_freeze", load)
    monkeypatch.setattr(calibration, "run_task", cancel)
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await qualification.run_fake(root, frozen["sha256"])
    else:
        await qualification.run_fake(root, frozen["sha256"])
    result = json.loads((root / "fake/result.json").read_text())
    assert len(result["rows"]) == 192 and result["qualified"] is False
    assert sum(r["status"] == "not_run" for r in result["rows"]) == (
        191 if failure == "cancel" else 192
    )
    assert result["spend"]["stop_reason"] == (
        "cancelled" if failure == "cancel" else "freeze_drift"
    )


def test_qualification_cli_has_no_live_entry_point(qualification, tmp_path):
    import os
    import subprocess
    import sys

    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[2])}
    base = [sys.executable, "-m", "benchmarks.computer_use.jev_qualification"]
    help_result = subprocess.run(
        [*base, "--help"], env=env, capture_output=True, text=True, timeout=20
    )
    assert (
        help_result.returncode == 0
        and "prepare" in help_result.stdout
        and "audit" in help_result.stdout
    )
    blocked = subprocess.run(
        [*base, "live", "--root", str(tmp_path / "never-created")],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert blocked.returncode == 2 and not (tmp_path / "never-created").exists()


def test_fake_http_denies_external_dns_before_resolution(qualification, tmp_path, monkeypatch):
    import socket

    from benchmarks.computer_use.jev_fake_http import offline_http, reply

    def leaked(*args, **kwargs):
        pytest.fail("external DNS resolver entered")

    monkeypatch.setattr(socket, "getaddrinfo", leaked)
    with offline_http(reply, tmp_path / "transport.jsonl") as transport:
        with pytest.raises(AssertionError, match="external"):
            socket.getaddrinfo("network-forbidden.invalid", 443)
        assert len(transport["blocked_external"]) == 1
