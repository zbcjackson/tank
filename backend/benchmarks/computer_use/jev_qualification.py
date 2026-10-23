"""Frozen supplemental calibration qualification; no live-model entry point."""

from __future__ import annotations

import csv
import asyncio
import hashlib
import io
import json
import shutil
import tarfile
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

from agent_computer_use.contracts import GoalContract

BACKEND = Path(__file__).resolve().parents[2]
ARCHIVE = (
    BACKEND.parent
    / "docs/research/artifacts/jev-supplemental-calibration-registration-20261022.tar.xz"
)
ARCHIVE_SHA = "8c21e2696a8b3cf3abc01a5af09897f468f1748cc256b97cae1dc17f75b91f76"
REGISTRATION_SHA = "762859bcce4283f062cd00f7748e3f8b7f507577d19b43650ccc3f463bdf1e28"
EXTRA_SOURCES = tuple(
    "benchmarks/computer_use/" + name
    for name in (
        "jev_qualification.py",
        "jev_audit.py",
        "jev_fake_http.py",
        "jev_native_qualification.py",
    )
)
AMENDED_SOURCES = {
    "benchmarks/computer_use/jev_real_product_route.py",
    "benchmarks/computer_use/jev_calibration_route.py",
}


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def registration(archive: Path = ARCHIVE) -> dict[str, Any]:
    """Read the reviewed registration without extracting or importing its code."""
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA:
        raise ValueError("registration archive changed")
    with tarfile.open(archive) as bundle:

        def read(name: str) -> bytes:
            stream = bundle.extractfile(name)
            if stream is None:
                raise ValueError("registration file missing: " + name)
            return stream.read()

        frozen = json.loads(read("freeze.json"))
        if (
            frozen["sha256"] != REGISTRATION_SHA
            or digest({k: v for k, v in frozen.items() if k != "sha256"})
            != REGISTRATION_SHA
        ):
            raise ValueError("registration digest changed")
        contents = {name: read(name) for name in frozen["files"]}
        if any(
            hashlib.sha256(data).hexdigest() != frozen["files"][name]
            for name, data in contents.items()
        ):
            raise ValueError("registration input changed")
        cases = [json.loads(line) for line in contents["bank/cases.jsonl"].splitlines()]
        by_id = {c["id"]: c for c in cases}
        for case in cases:
            GoalContract.from_input(case["goal"])
        schedule = []
        for row in csv.DictReader(io.StringIO(contents["slot-order.csv"].decode())):
            case = by_id[row["case_id"]]
            schedule.append(
                {
                    "id": case["id"] + "-" + row["arm"],
                    "case": case["id"],
                    "arm": row["arm"],
                    **{
                        k: case[k]
                        for k in ("cluster_id", "condition", "product", "group")
                    },
                }
            )
        return {
            "cases": cases,
            "schedule": schedule,
            "protocol": json.loads(contents["protocol.json"]),
            "runtime_sources": json.loads(contents["runtime-sources.json"]),
            "original": json.loads(contents["inputs/calibration-freeze.json"]),
        }


def prefix(registered: dict[str, Any]) -> tuple[list[dict], list[dict]]:
    """Select only the declared prefix, in registered slot/first-case order."""
    selected = {
        c["id"]: c
        for c in registered["cases"]
        if c["reserved_rank"] < (2 if c["negative"] else 4)
    }
    slots = [s for s in registered["schedule"] if s["case"] in selected]
    ids = dict.fromkeys(s["case"] for s in slots)
    return [selected[cid] for cid in ids], slots


def save(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources(registered: dict[str, Any]) -> dict[str, str]:
    original = registered["runtime_sources"]
    sources = {name: sha(BACKEND / name) for name in (*original, *EXTRA_SOURCES)}
    if any(
        sources[name] != value and name not in AMENDED_SOURCES
        for name, value in original.items()
    ):
        raise ValueError("unregistered runtime change requires a separate amendment")
    return sources


def _body(root: Path, registered: dict[str, Any], *, candidate: bool) -> dict[str, Any]:
    from benchmarks.computer_use import jev_calibration_route as calibration

    original = registered["original"]
    actual = calibration.freeze_inputs(
        Path(original["apps"]["sqlite-web"]["python"]),
        Path(original["apps"]["linkding"]["root"]),
    )
    protocol = registered["protocol"]
    if (
        actual["apps"] != original["apps"]
        or actual["models"] != protocol["models"]
        or actual["versions"] != protocol["sdk_versions"]
        or any(
            version(name) != expected
            for name, expected in protocol["sdk_versions"].items()
        )
        or any(
            actual[key] != value for key, value in protocol["execution_limits"].items()
        )
    ):
        raise ValueError("registered product/profile/limits changed")
    sources = _sources(registered)
    files = {"registration.tar.xz": ARCHIVE_SHA}
    for name, value in sources.items():
        relative = "source/" + name
        if sha(root / relative) != value:
            raise ValueError("saved source drift: " + name)
        files[relative] = value
    cases, schedule = (
        (registered["cases"], registered["schedule"])
        if candidate
        else prefix(registered)
    )
    if not candidate:
        if json.loads((root / "cases.json").read_text()) != cases:
            raise ValueError("qualification case selection changed")
        files.update(
            {
                "cases.json": sha(root / "cases.json"),
                "execution-freeze.json": sha(root / "execution-freeze.json"),
            }
        )
    changed = {
        name: {"before": value, "after": sources[name]}
        for name, value in registered["runtime_sources"].items()
        if sources[name] != value
    }
    frozen = {
        "revision": "supplemental-execution-v2",
        "kind": "calibration-candidate" if candidate else "qualification-only",
        "registration_sha256": REGISTRATION_SHA,
        "formal_N": None,
        "formal_confirmation": False,
        "model_execution_eligible": False,
        "amendment": {
            "parent": REGISTRATION_SHA,
            "prior_qualification_sha256": "cf402dd6334144db156b7eefc99ac6bd65b55bd9d1cd9b3d6de4e03cd200a11b",
            "runtime_changes": changed,
            "new_sources": list(EXTRA_SOURCES),
            "reason": "Review R1/R2: reconcile row/event/ledger/fake HTTP before each next slot; preserve cancellation after native cleanup. No real models.",
        },
        "cases": cases,
        "schedule": schedule,
        "files": files,
        "source_sha256": sources,
        "apps": actual["apps"],
        "models": actual["models"],
        "versions": actual["versions"],
        **protocol["execution_limits"],
    }
    frozen["sha256"] = digest(frozen)
    return frozen


def prepare(root: Path) -> dict[str, Any]:
    """Freeze a candidate full study and its fixed offline qualification prefix."""
    registered = registration()
    sources = _sources(registered)
    root.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(ARCHIVE, root / "registration.tar.xz")
    for name in sources:
        target = root / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BACKEND / name, target)
    save(root / "cases.json", prefix(registered)[0])
    save(root / "execution-freeze.json", _body(root, registered, candidate=True))
    frozen = _body(root, registered, candidate=False)
    save(root / "freeze.json", frozen)
    return frozen


def load_freeze(
    root: Path, approved: str, *, candidate: bool = False
) -> dict[str, Any]:
    """Revalidate registration, cases/order, sources and products before any trial."""
    try:
        frozen = json.loads(
            (
                root / ("execution-freeze.json" if candidate else "freeze.json")
            ).read_text()
        )
        if (
            frozen["sha256"] != approved
            or digest({k: v for k, v in frozen.items() if k != "sha256"}) != approved
        ):
            raise ValueError("freeze digest mismatch")
        expected = _body(
            root, registration(root / "registration.tar.xz"), candidate=candidate
        )
        if frozen != expected:
            raise ValueError("execution freeze drift")
        return frozen
    except (OSError, KeyError, TypeError) as error:
        raise ValueError("missing or invalid frozen input") from error


def progress(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    temporary.replace(path)


async def run_fake(root: Path, approved: str) -> dict[str, Any]:
    """Execute exactly the qualified prefix; both official SDKs use fake HTTP."""
    from benchmarks.computer_use import (
        jev_audit as audit,
        jev_calibration_route as calibration,
    )
    from benchmarks.computer_use import jev_fake_http
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit

    frozen = load_freeze(root, approved)
    output = root / "fake"
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
        "mode": "fake-only",
        "formal_N": None,
        "model_execution_eligible": False,
        "external_model_requests": None,
        "rows": rows,
        "completed": False,
        "qualified": False,
    }
    labels: dict[str, Any] = {}
    unresolved: dict[str, str] = {}
    save(
        output / "started.json",
        {"sha256": approved, "planned_ids": [r["id"] for r in rows]},
    )

    def persist() -> None:
        result["spend"] = ledger.snapshot()
        progress(output / "result.json", result)
        progress(
            output / "audit-evidence.json",
            {
                "sha256": approved,
                "trials": labels,
                "unresolved": unresolved,
                "regressions_passed": None,
                "note": "Complete typed audit.json requires a separately bound verification receipt.",
            },
        )

    def restore(row: dict) -> None:
        path = output / row["id"] / "row.json"
        if path.is_file():
            try:
                partial = json.loads(path.read_text())
                if partial.get("id") == row["id"]:
                    row.update(partial)
            except (OSError, ValueError):
                row["partial_receipt_unreadable"] = True

    with jev_fake_http.offline_http(
        jev_fake_http.reply, output / "transport.jsonl"
    ) as transport:
        persist()
        try:
            for row in rows:
                try:
                    load_freeze(root, approved)
                    row.update(status="started", attempted=True)
                    persist()
                    transport["active_trial"] = row["id"]
                    transport_start = len(transport["requests"])
                    row.update(
                        await calibration.run_task(
                            cases[row["case"]],
                            row["arm"],
                            output,
                            frozen=frozen,
                            jev_credential="qualification-fake",
                            peer_credential="qualification-fake",
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
                    snapshot = ledger.snapshot()
                    usage = row.get("usage", {})
                    if usage.get("unknown_calls") or usage.get("estimated_calls"):
                        ledger.stop("unknown_usage")
                    if (
                        snapshot["batch"]["reserved_tokens"]
                        or snapshot["batch"]["reserved_nano_usd"]
                    ):
                        ledger.stop("unreleased_reservations")
                    requests = snapshot["requests"].values()
                    if any(r["status"] != "known" for r in requests):
                        ledger.stop("unknown_usage")
                    elif (
                        sum(
                            cast(int, r["input_tokens"]) + cast(int, r["output_tokens"])
                            for r in requests
                        )
                        != snapshot["batch"]["known_tokens"]
                    ):
                        ledger.stop("usage_mismatch")
                    if not ledger.snapshot()["stop_reason"]:
                        try:
                            audit.audit_usage(
                                row, snapshot, transport["requests"][transport_start:]
                            )
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
                    if row["attempted"]:
                        restore(row)
                        row.update(status="error", error_type=type(error).__name__)
                        ledger.stop("operational_error")
                    else:
                        ledger.stop("freeze_drift")
                finally:
                    transport["active_trial"] = None
                    persist()
                if ledger.snapshot()["stop_reason"]:
                    break
            result["completed"] = not ledger.snapshot()["stop_reason"] and all(
                r["status"] == "finished" for r in rows
            )
            result["qualified"] = bool(
                result["completed"]
                and len(labels) == len(rows)
                and all(
                    not label["critical_events"]
                    and not label["unexpected_action"]
                    and (
                        label["negative_verified"]
                        if cases[row["case"]]["negative"]
                        else label["strict_verified"]
                        and (
                            not cases[row["case"]]["recovery"]
                            or label["recovery_verified"]
                        )
                    )
                    and (
                        row["negative_passed"]
                        if cases[row["case"]]["negative"]
                        else row["strict_completed"]
                        and (
                            not cases[row["case"]]["recovery"]
                            or row["recovery_completed"]
                        )
                    )
                    for row in rows
                    if (label := labels.get(row["id"])) is not None
                )
            )
        finally:
            ledger.close()
            result["fake_sdk_calls"] = len(transport["requests"])
            result["fake_image_calls"] = sum(
                r["provider"] == "peer" for r in transport["requests"]
            )
            result["blocked_external_attempts"] = transport["blocked_external"]
            captured = [
                call["call_id"] for row in rows for call in row.get("calls", [])
            ]
            requests = ledger.snapshot()["requests"]
            if (
                len(transport["requests"]) == len(captured) == len(set(captured))
                and set(captured) == set(requests)
                and all(request["status"] == "known" for request in requests.values())
            ):
                result["external_model_requests"] = 0
            else:
                result["qualified"] = False
            if transport["blocked_external"]:
                result["qualified"] = False
            persist()
    save(
        output / "closed.json",
        {
            "sha256": approved,
            "result_sha256": digest(result),
            "attempted_ids": [r["id"] for r in rows if r["attempted"]],
            "transport_context_ended": True,
        },
    )
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "native", "fake", "audit"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, required=True)
        if name != "prepare":
            command.add_argument("--approved-sha", required=True)
        if name == "audit":
            command.add_argument("--verification", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            frozen = prepare(args.root)
            summary = {
                "sha256": frozen["sha256"],
                "cases": len(frozen["cases"]),
                "slots": len(frozen["schedule"]),
                "model_execution_eligible": False,
            }
            passed = True
        elif args.command == "audit":
            from benchmarks.computer_use.jev_audit import build_audit

            audit = build_audit(args.root, args.approved_sha, args.verification)
            save(args.root / "fake/audit.json", audit)
            summary = {
                "trials": len(audit["trials"]),
                "regressions_passed": audit["regressions_passed"],
            }
            passed = audit["regressions_passed"]
        elif args.command == "native":
            from benchmarks.computer_use.jev_native_qualification import run

            result = asyncio.run(run(args.root, args.approved_sha))
            summary = {
                "completed": result["completed"],
                "cases": len(result["rows"]),
                "model_calls": result["model_calls"],
            }
            passed = result["completed"]
        else:
            result = asyncio.run(run_fake(args.root, args.approved_sha))
            summary = {
                key: result[key]
                for key in (
                    "completed",
                    "qualified",
                    "fake_sdk_calls",
                    "fake_image_calls",
                    "external_model_requests",
                )
            }
            passed = result["qualified"]
        print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
        return 0 if passed else 1
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
