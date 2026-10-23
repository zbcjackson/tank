"""Supplemental calibration execution, gated by source-bound offline qualification."""

from __future__ import annotations

import asyncio
import json
import shutil
import tarfile
from collections.abc import Mapping
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from benchmarks.computer_use import jev_qualification as qualification

BACKEND = qualification.BACKEND
SOURCE = "benchmarks/computer_use/jev_execution.py"
PROOF_ARCHIVE = (
    BACKEND.parent
    / "docs/research/artifacts"
    / "jev-supplemental-calibration-qualification-review-20261023.tar.xz"
)
PROOF_SHA = "5b9a0f40c8c0dd7a7b7cf59f98d8eb009b99ab1b1a5782b6343167dba1a03930"
QUALIFIED_SHA = "647574930ed78a803b875b476dfc315ebe4410811af389957695518e5e2e0da0"
CANDIDATE_SHA = "a650e4f726ec0a25b4f5585f8dc241623b5e342e387b778eb608abb62596e4a5"
PRIOR_HOST = "qualification-final-r1/freeze.json"
HOST_AMENDMENTS = frozenset(
    {
        "plugins/agent-computer-use/src/agent_computer_use/channels/dom.py",
        "benchmarks/computer_use/jev_qualification.py",
    }
)
BUDGET = {
    "record_only": True,
    "request_limit": None,
    "token_limit": None,
    "nano_usd_limit": None,
    "price_status": "unpriced",
    "unknown_usage": "stop",
    "pending_reservations": "stop",
}
CHECKS = frozenset(
    {
        "backend_pytest",
        "backend_ruff",
        "pyright",
        "web_lint",
        "web_tsc_b",
        "cli_ruff",
        "dev_logs",
        "e2e",
        "docs",
    }
)


def prior_proof() -> dict[str, Any]:
    """Read trusted receipts, without extracting or importing archived code."""
    if qualification.sha(PROOF_ARCHIVE) != PROOF_SHA:
        raise ValueError("prior qualification archive changed")
    wanted = {"postrun-independent-check.json", "final-bindings-check.json", PRIOR_HOST}
    receipts = {}
    with tarfile.open(PROOF_ARCHIVE, "r|xz") as archive:
        for member in archive:
            if member.name in wanted:
                stream = archive.extractfile(member)
                if stream is None or not member.isfile():
                    raise ValueError("prior receipt is not a regular file")
                receipts[member.name] = json.loads(stream.read())
                if set(receipts) == wanted:
                    break
    if set(receipts) != wanted:
        raise ValueError("missing prior qualification receipts")
    prior = receipts[PRIOR_HOST]
    if (
        prior.get("sha256") != QUALIFIED_SHA
        or qualification.digest({k: v for k, v in prior.items() if k != "sha256"})
        != QUALIFIED_SHA
    ):
        raise ValueError("prior host freeze differs")
    result = receipts["postrun-independent-check.json"]
    expected = {
        "sha256": QUALIFIED_SHA,
        "native_goals": 96,
        "native_qualified": 96,
        "native_cleanup": 96,
        "native_model_calls": 0,
        "planned": 192,
        "attempted": 192,
        "completed": True,
        "qualified": True,
        "stop_reason": None,
        "unknown_requests": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0,
        "external_model_requests": 0,
        "blocked_external": [],
        "cleanup_confirmed": 192,
        "audited": 192,
        "critical_events": 0,
        "unexpected_actions": 0,
    }
    if any(result.get(k) != v for k, v in expected.items()):
        raise ValueError("prior host qualification did not pass")
    bindings = receipts["final-bindings-check.json"]
    if any(
        bindings.get(k) is not True
        for k in (
            "runtime_source_match",
            "verification_log_match",
            "task_file_match",
            "audit_freeze_result_receipt_bindings",
        )
    ):
        raise ValueError("prior qualification bindings incomplete")
    return {"archive_sha256": PROOF_SHA, "receipts": receipts}


def body(root: Path, *, fake: bool) -> dict[str, Any]:
    """Bind the explicit current-host amendment; the old proof is provenance only."""
    candidate = json.loads((root / "qualified-input/execution-freeze.json").read_text())
    host = json.loads((root / "qualified-input/freeze.json").read_text())
    parent = qualification.load_freeze(
        root / "qualified-input",
        candidate["sha256"],
        candidate=True,
    )
    qualification.load_freeze(root / "qualified-input", host["sha256"])
    if qualification.sha(PROOF_ARCHIVE) != PROOF_SHA:
        raise ValueError("prior qualification archive changed")
    prior = json.loads((root / "prior-proof.json").read_text())["receipts"][PRIOR_HOST]
    if qualification.digest({k: v for k, v in prior.items() if k != "sha256"}) != QUALIFIED_SHA:
        raise ValueError("prior host source baseline differs")
    old_sources = prior["source_sha256"]
    current_sources = parent["source_sha256"]
    changes = {
        name: {"before": old_sources.get(name), "after": value}
        for name, value in current_sources.items()
        if old_sources.get(name) != value
    }
    if (
        len(old_sources) != 41
        or set(current_sources) != set(old_sources)
        or set(changes) != HOST_AMENDMENTS
    ):
        raise ValueError("only the two explicit current-host amendments are allowed")
    sources = {**parent["source_sha256"], SOURCE: qualification.sha(BACKEND / SOURCE)}
    files = {"prior-proof.json": qualification.sha(root / "prior-proof.json")}
    for name, value in sources.items():
        saved = "source/" + name
        if qualification.sha(root / saved) != value:
            raise ValueError("saved execution source changed: " + name)
        files[saved] = value
    cases, schedule = (
        qualification.prefix({"cases": parent["cases"], "schedule": parent["schedule"]})
        if fake
        else (parent["cases"], parent["schedule"])
    )
    frozen = {
        "revision": "supplemental-calibration-execution-v2",
        "kind": "execution-qualification" if fake else "calibration-execution",
        "formal_N": None,
        "formal_confirmation": False,
        "requires_explicit_approval": True,
        "registration_sha256": qualification.REGISTRATION_SHA,
        "qualified_host_sha256": host["sha256"],
        "prior_qualified_host_sha256": QUALIFIED_SHA,
        "prior_candidate_sha256": CANDIDATE_SHA,
        "current_candidate_sha256": parent["sha256"],
        "prior_archive_sha256": PROOF_SHA,
        "host_amendment": {
            "runtime_changes": changes,
            "unchanged_prior_sources": 39,
            "current_native_goals_required": 96,
            "prior_native_is_current_qualification": False,
        },
        "cases": cases,
        "schedule": schedule,
        "source_sha256": sources,
        "files": files,
        "budget": dict(BUDGET),
        "data_policy": {
            "jev": "TypeSafe: public goal, current structured state/candidates; text only",
            "peer": "OpenRouter: same public state plus bound synthetic 1280x720 PNG",
            "private_oracle": "never included in model requests",
        },
        **{
            k: parent[k]
            for k in (
                "apps",
                "models",
                "versions",
                "seconds_per_task",
                "max_actions",
                "max_observations",
                "max_candidates",
                "retries",
                "max_parameter_bytes",
            )
        },
    }
    if fake:
        frozen["parent_execution_sha256"] = body(root, fake=False)["sha256"]
    frozen["sha256"] = qualification.digest(frozen)
    return frozen


def prepare(root: Path) -> dict[str, Any]:
    """Prepare both schedules without reading credentials or constructing clients."""
    if not root.is_absolute():
        raise ValueError("absolute new execution directory required")
    proof = prior_proof()
    root.mkdir(parents=True, exist_ok=False)
    qualification.prepare(root / "qualified-input")
    shutil.copytree(root / "qualified-input/source", root / "source")
    shutil.copyfile(BACKEND / SOURCE, root / "source" / SOURCE)
    qualification.save(root / "prior-proof.json", proof)
    frozen = body(root, fake=False)
    qualification.save(root / "freeze.json", frozen)
    qualification.save(root / "qualification-freeze.json", body(root, fake=True))
    return frozen


def load_freeze(root: Path, approved: str, *, fake: bool = False) -> dict[str, Any]:
    try:
        stored = json.loads(
            (
                root / ("qualification-freeze.json" if fake else "freeze.json")
            ).read_text()
        )
        if stored != body(root, fake=fake) or stored["sha256"] != approved:
            raise ValueError("execution source, input or approval drift")
        return stored
    except (OSError, KeyError, TypeError) as error:
        raise ValueError("missing or invalid execution freeze") from error


def verify_native(root: Path, frozen: dict) -> dict[str, Any]:
    """Re-audit the current host's fixed 96 goals; never fall back to old receipts."""
    from benchmarks.computer_use import jev_audit as audit

    try:
        host = qualification.load_freeze(root / "qualified-input", frozen["qualified_host_sha256"])
        output = root / "qualified-input/native"
        result_path = output / "result.json"
        result = json.loads(result_path.read_text())
        cases, rows = host["cases"], result["rows"]
        if (
            not isinstance(rows, list)
            or any(not isinstance(row, dict) for row in rows)
            or len(cases) != 96
            or result.get("sha256") != host["sha256"]
            or result.get("completed") is not True
            or result.get("stop_reason") is not None
            or type(result.get("model_calls")) is not int
            or result["model_calls"] != 0
            or [row.get("id") for row in rows] != [case["id"] for case in cases]
        ):
            raise ValueError("current native qualification is incomplete or misbound")
        raw = {}
        for case, row in zip(cases, rows):
            path = output / case["id"]
            saved = json.loads((path / "row.json").read_text())
            proof = json.loads((path / "native-proof.json").read_text())
            if not isinstance(saved, dict) or not isinstance(proof, dict):
                raise ValueError("invalid native row or evidence seal")
            if (
                row.get("attempted") is not True
                or any(
                    receipt.get("status") != "finished"
                    or receipt.get("qualified") is not True
                    or receipt.get("cleanup") is not True
                    or type(receipt.get("model_calls")) is not int
                    or receipt["model_calls"] != 0
                    for receipt in (row, saved)
                )
                or saved.get("id") != case["id"]
                or any(row.get(key) != value for key, value in saved.items())
                or not isinstance(proof.get("files"), dict)
                or set(proof["files"])
                != {"before.db", "after.db", "http.jsonl", "final.html", "events.json", "observations.json"}
                or audit.audit_native_trial(case, row, path) is not True
            ):
                raise ValueError("invalid or failed current native goal: " + case["id"])
            raw[case["id"]] = {
                "row_sha256": qualification.sha(path / "row.json"),
                "proof_sha256": qualification.sha(path / "native-proof.json"),
            }
        result_sha = qualification.sha(result_path)
        return {
            "current_host_sha256": host["sha256"],
            "native_goals": 96,
            "native_result_sha256": result_sha,
            "native_raw_proof_sha256": qualification.digest({"result": result_sha, "trials": raw}),
        }
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError("missing or invalid current native qualification: " + str(error)) from error


def audit_usage(row: dict, spend: Mapping[str, Any], path: Path) -> None:
    """Reconcile captured SDK completions, not physical HTTP transmission counts."""
    from benchmarks.computer_use import jev_audit as audit

    try:
        journal = path / "calls.jsonl"
        raw = (
            [json.loads(line) for line in journal.read_text().splitlines()]
            if journal.exists()
            else []
        )
        requests = [item for item in raw if "request" in item]
        responses = [item for item in raw if "response" in item]
        if (
            requests != json.loads(json.dumps(row["calls"], allow_nan=False))
            or [r["call_id"] for r in requests] != [r["call_id"] for r in responses]
            or len(raw) != len(requests) + len(responses)
        ):
            raise audit.EvidenceError("SDK request/completion capture differs")
        receipts = []
        for call, response in zip(requests, responses):
            visual = "messages" in call["request"]
            payload = response["response"]
            receipts.append(
                {
                    "trial_id": row["id"],
                    "goal_id": row["case"],
                    "provider": "peer" if visual else "jev",
                    "images": [image["sha256"] for image in call["images"]],
                    "request_sha256": qualification.digest(call["request"]),
                    "usage": payload["usage"]
                    if visual
                    else {k: payload[k] for k in ("input_tokens", "output_tokens")},
                }
            )
        # Reuse the same strict row/event/call/ledger count contract; receipt origin
        # here is the sealed SDK capture, while fake mode also checks fake HTTP.
        audit.audit_usage(row, spend, receipts)
        verify_ledger(spend)
    except (OSError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, audit.EvidenceError):
            raise
        raise audit.EvidenceError("missing or invalid SDK usage evidence") from error


def verify_ledger(spend: Mapping[str, Any]) -> None:
    from benchmarks.computer_use.jev_audit import EvidenceError

    batch = spend["batch"]
    requests = spend["requests"].values()
    if (
        spend["record_only"] is not True
        or spend["cost_status"] != "unpriced"
        or any(
            type(batch[k]) is not int or batch[k] != 0
            for k in (
                "reserved_tokens",
                "reserved_nano_usd",
            )
        )
        or any(
            r["status"] != "known"
            or any(
                type(r[k]) is not int or r[k] < 0
                for k in ("input_tokens", "output_tokens")
            )
            for r in requests
        )
        or type(batch["known_tokens"]) is not int
        or sum(r["input_tokens"] + r["output_tokens"] for r in requests)
        != batch["known_tokens"]
    ):
        raise EvidenceError("global ledger totals or reservations differ")


def verify_checks(frozen: dict, verification: Path) -> None:
    """Only closed, byte-bound successful logs certify this executable source."""
    try:
        receipt = json.loads(verification.read_text())
        if (
            type(receipt.get("schema_version")) is not int
            or receipt["schema_version"] != 1
            or receipt.get("source_sha256") != frozen["source_sha256"]
            or not CHECKS <= set(receipt.get("checks", {}))
        ):
            raise ValueError("verification does not bind current execution sources")
        for name in CHECKS:
            check = receipt["checks"][name]
            if (
                type(check.get("exit_code")) is not int
                or check["exit_code"] != 0
                or qualification.sha(verification.parent / check["log"])
                != check["sha256"]
            ):
                raise ValueError("failed or changed verification log: " + name)
    except (OSError, KeyError, TypeError) as error:
        raise ValueError("incomplete verification evidence") from error


def build_audit(
    root: Path,
    approved: str,
    verification: Path,
    *,
    fake: bool = False,
) -> dict[str, Any]:
    """Re-read raw product and SDK evidence; unattempted rows remain in the audit."""
    from benchmarks.computer_use import jev_audit as audit

    try:
        frozen = load_freeze(root, approved, fake=fake)
        verify_checks(frozen, verification)
        native = verify_native(root, frozen)
        output = root / ("fake" if fake else "live")

        def receipt(name: str) -> Any:
            return json.loads((output / name).read_text())

        result, started, closed = (
            receipt(name)
            for name in (
                "result.json",
                "started.json",
                "closed.json",
            )
        )
        verify_ledger(result["spend"])
        rows = result["rows"]
        if (
            result.get("sha256") != approved
            or result.get("mode") != ("fake-only" if fake else "calibration")
            or started.get("sha256") != approved
            or closed.get("sha256") != approved
            or closed.get("driver_context_ended") is not True
            or closed.get("fake_http_context_ended") is not fake
            or closed.get("result_sha256") != qualification.digest(result)
            or started.get("planned_ids") != [s["id"] for s in frozen["schedule"]]
            or [r["id"] for r in rows] != [s["id"] for s in frozen["schedule"]]
            or closed.get("attempted_ids")
            != [r["id"] for r in rows if r.get("attempted") is True]
        ):
            raise audit.EvidenceError(
                "execution start/closure/denominator binding differs"
            )
        transport = receipt_lines(output / "transport.jsonl") if fake else []
        ids = [c["call_id"] for row in rows for c in row.get("calls", [])]
        if (
            len(ids) != len(set(ids))
            or set(ids) != set(result["spend"]["requests"])
            or type(result.get("logical_sdk_calls")) is not int
            or result["logical_sdk_calls"] != len(ids)
        ):
            raise audit.EvidenceError("global SDK capture and ledger differ")
        if fake and (
            type(result.get("fake_sdk_calls")) is not int
            or result["fake_sdk_calls"] != len(transport)
            or len(transport) != len(ids)
            or type(result.get("fake_image_calls")) is not int
            or result["fake_image_calls"]
            != sum(t["provider"] == "peer" for t in transport)
            or type(result.get("external_model_requests")) is not int
            or result["external_model_requests"] != 0
            or result.get("blocked_external_attempts") != []
            or any(t["trial_id"] not in closed["attempted_ids"] for t in transport)
        ):
            raise audit.EvidenceError("fake transport closure/coverage differs")
        if not fake and result.get("external_model_requests") is not None:
            raise audit.EvidenceError(
                "SDK capture cannot certify physical HTTP request counts"
            )
        cases = {c["id"]: c for c in frozen["cases"]}
        labels = {}
        for slot, row in zip(frozen["schedule"], rows):
            if any(row.get(k) != v for k, v in slot.items()):
                raise audit.EvidenceError("trial identity differs")
            path = output / row["id"]
            if row.get("attempted") is True:
                labels[row["id"]] = audit.audit_trial(cases[row["case"]], row, path)
                audit_usage(row, result["spend"], path)
                if fake:
                    audit.audit_usage(
                        row,
                        result["spend"],
                        [t for t in transport if t["trial_id"] == row["id"]],
                    )
            elif (
                row.get("attempted") is False
                and row.get("status") == "not_run"
                and not path.exists()
                and not any(
                    r["trial"] == row["id"]
                    for r in result["spend"]["requests"].values()
                )
                and not any(t["trial_id"] == row["id"] for t in transport)
            ):
                labels[row["id"]] = {
                    "strict_verified": False,
                    "negative_verified": False,
                    "recovery_verified": False,
                    "unexpected_action": False,
                    "critical_events": 0,
                    "evidence": {
                        "nonattempt": "closed batch, no directory/SDK/native attempt"
                    },
                }
            else:
                raise audit.EvidenceError("unresolved attempted/nonattempt proof")
        return {
            "schema_version": 1,
            "freeze_sha256": approved,
            "result_sha256": qualification.digest(result),
            "evidence_kind": "fake" if fake else "calibration",
            "regressions_passed": True,
            "trials": labels,
            "verification_sha256": qualification.sha(verification),
            "usage_evidence": "sealed SDK completion capture; additionally fake HTTP in fake mode",
            **native,
        }
    except (OSError, KeyError, TypeError, ValueError) as error:
        if isinstance(error, audit.EvidenceError):
            raise
        raise audit.EvidenceError(
            "incomplete execution audit: " + str(error)
        ) from error


def receipt_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def preflight(root: Path, approved: str, verification: Path) -> dict[str, Any]:
    """Return a reviewable preview, never grant permission or read credentials."""
    frozen = load_freeze(root, approved)
    verify_checks(frozen, verification)
    prefix = body(root, fake=True)
    raw = build_audit(root, prefix["sha256"], verification, fake=True)
    saved = json.loads((root / "fake/audit.json").read_text())
    result = json.loads((root / "fake/result.json").read_text())
    if (
        qualification.digest(saved) != qualification.digest(raw)
        or result.get("completed") is not True
        or result.get("qualified") is not True
        or result["spend"].get("stop_reason") is not None
        or any(
            row.get("attempted") is not True or row.get("status") != "finished"
            for row in result["rows"]
        )
    ):
        raise ValueError(
            "execution qualification is incomplete or differs from raw audit"
        )
    cases = {c["id"]: c for c in prefix["cases"]}
    for row in result["rows"]:
        case, label = cases[row["case"]], raw["trials"][row["id"]]
        if (
            any(
                type(row.get(field)) is not bool
                for field in (
                    "strict_completed",
                    "negative_passed",
                    "recovery_completed",
                )
            )
            or label["critical_events"]
            or label["unexpected_action"]
            or not (
                label["negative_verified"] and row["negative_passed"]
                if case["negative"]
                else label["strict_verified"]
                and row["strict_completed"]
                and (
                    not case["recovery"]
                    or label["recovery_verified"]
                    and row["recovery_completed"]
                )
            )
        ):
            raise ValueError("execution qualification contains an invalid or failed goal")
    return {
        "ready_for_authorization": True,
        "model_execution_eligible": False,
        "execution_sha256": approved,
        "qualification_sha256": prefix["sha256"],
        "qualification_audit_sha256": qualification.digest(raw),
        "verification_sha256": qualification.sha(verification),
        **{key: raw[key] for key in (
            "current_host_sha256", "native_goals", "native_result_sha256", "native_raw_proof_sha256"
        )},
        "planned_trials": len(frozen["schedule"]),
        "condition_goals": len(frozen["cases"]),
        "seed_clusters": len({c["cluster_id"] for c in frozen["cases"]}),
        "budget": frozen["budget"],
        "models": frozen["models"],
        "data_policy": frozen["data_policy"],
        "formal_N": None,
        "note": "New exact-digest authorization is still required; this preview sends nothing.",
    }


async def run_batch(
    root: Path,
    approved: str,
    *,
    fake: bool = False,
    verification: Path | None = None,
    jev_credential: str = "",
    peer_credential: str = "",
) -> dict[str, Any]:
    """Use one serial schedule; never resume or replace a started batch."""
    from benchmarks.computer_use import jev_audit as audit
    from benchmarks.computer_use import jev_calibration_route as calibration
    from benchmarks.computer_use import jev_fake_http
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit

    frozen = load_freeze(root, approved, fake=fake)
    if fake:
        verify_native(root, frozen)
    if not fake:
        if (
            verification is None
            or preflight(root, approved, verification).get("ready_for_authorization")
            is not True
        ):
            raise ValueError("real execution requires completed source-bound admission")
        if not jev_credential.strip() or not peer_credential.strip():
            raise ValueError("both explicit model credentials required after admission")
    output = root / ("fake" if fake else "live")
    output.mkdir(exist_ok=False)
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
    cases = {c["id"]: c for c in frozen["cases"]}
    ledger = SpendLedger(
        SpendLimit(0, 0), record_only=True, journal=output / "spend.jsonl"
    )
    result: dict[str, Any] = {
        "sha256": approved,
        "mode": "fake-only" if fake else "calibration",
        "formal_N": None,
        "formal_confirmation": False,
        "model_execution_eligible": False,
        "external_model_requests": None,
        "logical_sdk_calls": 0,
        "rows": rows,
        "completed": False,
        "qualified": False,
    }
    labels: dict[str, Any] = {}
    unresolved: dict[str, str] = {}
    qualification.save(
        output / "started.json",
        {
            "sha256": approved,
            "planned_ids": [r["id"] for r in rows],
        },
    )

    def persist() -> None:
        result["spend"] = ledger.snapshot()
        qualification.progress(output / "result.json", result)
        qualification.progress(
            output / "audit-evidence.json",
            {
                "sha256": approved,
                "trials": labels,
                "unresolved": unresolved,
            },
        )

    def restore(row: dict) -> None:
        partial = output / row["id"] / "row.json"
        if partial.is_file():
            try:
                saved = json.loads(partial.read_text())
                if saved.get("id") == row["id"]:
                    row.update(saved)
            except (OSError, ValueError, TypeError):
                row["partial_receipt_unreadable"] = True

    transport = None
    try:
        with (
            jev_fake_http.offline_http(jev_fake_http.reply, output / "transport.jsonl")
            if fake
            else nullcontext(None)
        ) as transport:
            try:
                persist()
                for row in rows:
                    try:
                        load_freeze(root, approved, fake=fake)
                        row.update(status="started", attempted=True)
                        persist()
                        if transport is not None:
                            transport["active_trial"] = row["id"]
                        first = (
                            len(transport["requests"]) if transport is not None else 0
                        )
                        row.update(
                            await calibration.run_task(
                                cases[row["case"]],
                                row["arm"],
                                output,
                                frozen=frozen,
                                jev_credential="execution-fake"
                                if fake
                                else jev_credential,
                                peer_credential="execution-fake"
                                if fake
                                else peer_credential,
                                ledger=ledger,
                            )
                        )
                        label = audit.audit_trial(
                            cases[row["case"]], row, output / row["id"]
                        )
                        labels[row["id"]] = label
                        if label["critical_events"]:
                            ledger.stop("critical_safety")
                        if row.get("cleanup_confirmed") is not True:
                            ledger.stop("cleanup_unknown")
                        if not ledger.snapshot()["stop_reason"]:
                            try:
                                if transport is not None:
                                    audit.audit_usage(
                                        row,
                                        ledger.snapshot(),
                                        transport["requests"][first:],
                                    )
                                audit_usage(row, ledger.snapshot(), output / row["id"])
                            except audit.EvidenceError:
                                ledger.stop("usage_mismatch")
                                raise
                    except audit.EvidenceError as error:
                        unresolved[row["id"]] = str(error)
                        ledger.stop("audit_evidence_missing")
                    except asyncio.CancelledError:
                        restore(row)
                        if row["attempted"]:
                            row["status"] = "cancelled"
                        ledger.stop("cancelled")
                        raise
                    except Exception as error:
                        restore(row)
                        if row["attempted"]:
                            row.update(status="error", error_type=type(error).__name__)
                        ledger.stop(
                            "operational_error" if row["attempted"] else "freeze_drift"
                        )
                    finally:
                        if transport is not None:
                            transport["active_trial"] = None
                        persist()
                    if ledger.snapshot()["stop_reason"]:
                        break
                result["completed"] = not ledger.snapshot()["stop_reason"] and all(
                    row["status"] == "finished" for row in rows
                )
                result["qualified"] = bool(
                    result["completed"]
                    and len(labels) == len(rows)
                    and all(
                        not label["critical_events"]
                        and not label["unexpected_action"]
                        and (
                            label["negative_verified"] and row["negative_passed"]
                            if cases[row["case"]]["negative"]
                            else label["strict_verified"]
                            and row["strict_completed"]
                            and (
                                not cases[row["case"]]["recovery"]
                                or label["recovery_verified"]
                                and row["recovery_completed"]
                            )
                        )
                        for row in rows
                        if (label := labels.get(row["id"])) is not None
                    )
                )
            finally:
                captured = [
                    call["call_id"] for row in rows for call in row.get("calls", [])
                ]
                result["logical_sdk_calls"] = len(captured)
                if transport is not None:
                    result["fake_sdk_calls"] = len(transport["requests"])
                    result["fake_image_calls"] = sum(
                        r["provider"] == "peer" for r in transport["requests"]
                    )
                    result["blocked_external_attempts"] = transport["blocked_external"]
                    requests = ledger.snapshot()["requests"]
                    if (
                        len(transport["requests"])
                        == len(captured)
                        == len(set(captured))
                        and set(captured) == set(requests)
                        and all(r["status"] == "known" for r in requests.values())
                    ):
                        result["external_model_requests"] = 0
                    else:
                        result["qualified"] = False
                    if transport["blocked_external"]:
                        result["qualified"] = False
                persist()
    except (Exception, asyncio.CancelledError) as error:
        if not ledger.snapshot()["stop_reason"]:
            ledger.stop(
                "cancelled"
                if isinstance(error, asyncio.CancelledError)
                else "operational_error"
            )
        raise
    finally:
        ledger.close()
        persist()
        qualification.save(
            output / "closed.json",
            {
                "sha256": approved,
                "result_sha256": qualification.digest(result),
                "attempted_ids": [r["id"] for r in rows if r["attempted"]],
                "driver_context_ended": True,
                "fake_http_context_ended": fake and transport is not None,
            },
        )
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "fake", "audit", "check", "run"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        if name != "prepare":
            command.add_argument("--approved-sha", required=True)
        if name in ("audit", "check", "run"):
            command.add_argument("--verification", type=Path, required=True)
        if name == "audit":
            command.add_argument("--fake", action="store_true")
    args = parser.parse_args(argv)
    if not args.root.is_absolute():
        parser.error("an absolute execution directory is required")
    try:
        if args.command == "prepare":
            frozen = prepare(args.root)
            prefix = json.loads((args.root / "qualification-freeze.json").read_text())
            summary = {
                "execution_sha256": frozen["sha256"],
                "qualification_sha256": prefix["sha256"],
                "current_host_sha256": frozen["qualified_host_sha256"],
                "current_native_goals_required": 96,
                "planned_trials": len(frozen["schedule"]),
                "budget": frozen["budget"],
                "model_execution_eligible": False,
            }
            passed = True
        elif args.command == "audit":
            document = build_audit(
                args.root, args.approved_sha, args.verification, fake=args.fake
            )
            qualification.save(
                args.root / ("fake" if args.fake else "live") / "audit.json", document
            )
            summary = {
                "trials": len(document["trials"]),
                "regressions_passed": document["regressions_passed"],
            }
            passed = True
        elif args.command == "check":
            summary = preflight(args.root, args.approved_sha, args.verification)
            passed = True
        else:
            fake = args.command == "fake"
            credentials: dict[str, str] = {}
            if not fake:
                # Validate the exact executable and raw qualification before even
                # reading credentials; run_batch repeats admission before dispatch.
                preflight(args.root, args.approved_sha, args.verification)
                import os
                from dotenv import dotenv_values

                values = {**dotenv_values(BACKEND / "core/.env"), **os.environ}
                credentials = {
                    "jev_credential": values.get("TYPESAFE_API_KEY") or "",
                    "peer_credential": values.get("OPENROUTER_API_KEY") or "",
                }
            result = asyncio.run(
                run_batch(
                    args.root,
                    args.approved_sha,
                    fake=fake,
                    verification=None if fake else args.verification,
                    **credentials,
                )
            )
            summary = {
                "completed": result["completed"],
                "qualified": result["qualified"],
                "attempted": sum(r["attempted"] for r in result["rows"]),
                "stop_reason": result["spend"]["stop_reason"],
                "logical_sdk_calls": result["logical_sdk_calls"],
                "external_model_requests": result["external_model_requests"],
            }
            passed = result["qualified"] if fake else result["completed"]
        print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
        return 0 if passed else 1
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
