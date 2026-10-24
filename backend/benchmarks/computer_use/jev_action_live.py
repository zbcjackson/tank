"""One small source-frozen V/current-JT/action-JT development study on owned products."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import re
import tarfile
from importlib.metadata import version
from pathlib import Path

from agent_computer_use.contracts import GoalContract
from benchmarks.computer_use import jev_calibration_route as calibration
from benchmarks.computer_use import jev_action_admission, jev_action_boundary, jev_sdk_diagnostics
from benchmarks.computer_use.jev_image_dev import digest

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT.parent / "docs/research/artifacts/jev-action-admission-20261023.tar.xz"
BASELINE_SHA = "a887d05a025bb547f7de027848fa27bbca1c8d06c04448c40d6572b1b820929a"
PACKAGES = ("playwright", "openai", "typesafe-sdk", "pillow", "httpx", "httpx2")
POLICIES = ("v", "jt", "ja")


def sources() -> dict[str, str]:
    if hashlib.sha256(BASELINE.read_bytes()).hexdigest() != BASELINE_SHA:
        raise ValueError("reviewed prototype baseline changed")
    with tarfile.open(BASELINE) as bundle:
        stream = bundle.extractfile("verification-before-review.json")
        if stream is None:
            raise ValueError("baseline source bindings missing")
        names = list(json.load(stream)["original_registered_source_sha256"])
    names += [
        str(Path(inspect.getfile(module)).relative_to(ROOT))
        for module in (jev_action_admission, jev_sdk_diagnostics, jev_action_boundary)
    ]
    names += [str(Path(__file__).relative_to(ROOT))]
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names
    }


def study_cases(namespace: str) -> tuple[list[dict], list[dict]]:
    if not namespace.strip() or len(namespace) > 128:
        raise ValueError("bounded new study namespace required")
    templates = calibration.calibration_cases()
    result, schedule = [], []
    for product in ("sqlite-web", "linkding"):
        for index, family in enumerate(("unique", "same-title", "missing")):
            candidates = [
                c
                for c in templates
                if c["product"] == product
                and c["family"] == family
                and c["group"] == ("negative" if family == "missing" else "normal")
                and c["condition"] == "cold"
            ]
            template = candidates[(index + 1) % len(candidates)]
            old_nonce = template["goal"]["inputs"][0]["value"].rsplit(" ", 1)[-1]
            if not re.fullmatch("[a-f0-9]{10}", old_nonce):
                raise ValueError("unexpected reviewed seed format")
            nonce = digest([namespace, product, family])[:16]

            def fresh(value: object) -> object:
                if isinstance(value, str):
                    return (
                        value.replace(old_nonce, nonce)
                        .replace("/calibration/", "/action-admission-dev/")
                        .replace("Review ", "Action study ")
                        .replace("Approved ", "Action approved ")
                    )
                if isinstance(value, list):
                    return [fresh(v) for v in value]
                if isinstance(value, dict):
                    return {k: fresh(v) for k, v in value.items()}
                return value

            seed = "aa-" + digest([namespace, product, family])[:20]
            cold_order = POLICIES[index:] + POLICIES[:index]
            for condition in ("cold", "prewarmed"):
                order = cold_order if condition == "cold" else cold_order[::-1]
                for position, policy in enumerate(order):
                    case = fresh(copy.deepcopy(template))
                    if not isinstance(case, dict):
                        raise ValueError("expected task object")
                    case.update(
                        id="case-" + digest([namespace, seed, condition, policy])[:20],
                        cluster_id=seed,
                        condition=condition,
                        pair_id=seed + "-" + condition,
                        policy=policy,
                    )
                    case["goal"]["goal_id"] = case["id"]
                    GoalContract.from_input(case["goal"])
                    arm = "v" if policy == "v" else "jt"
                    result.append(case)
                    schedule.append(
                        {
                            "id": case["id"] + "-" + arm,
                            "case": case["id"],
                            "arm": arm,
                            "policy": policy,
                            "position": position,
                            **{
                                k: case[k]
                                for k in (
                                    "product",
                                    "cluster_id",
                                    "pair_id",
                                    "condition",
                                )
                            },
                        }
                    )
    return result, schedule


def freeze_inputs(sql_python: Path, link_root: Path, namespace: str, *, boundary: bool = False) -> dict:
    original = calibration.freeze_inputs(sql_python, link_root)
    cases, schedule = (jev_action_boundary.study_cases(namespace) if boundary else study_cases(namespace))
    result = {
        "revision": "action-admission-live-1",
        "namespace": namespace,
        "formal_confirmation": False,
        "cases": cases,
        "schedule": schedule,
        "apps": original["apps"],
        "source_sha256": sources(),
        "versions": {name: version(name) for name in PACKAGES},
        "models": copy.deepcopy(original["models"]),
        "provenance": {**original["provenance"], BASELINE.name: BASELINE_SHA},
        "record_only": True,
        "price_evidence": "unpriced; inherited historical model metadata is not a current quote",
        "max_candidates": 64,
        "seconds_per_task": 120,
        "max_actions": 6,
        "max_observations": 24,
        "retries": 0,
        "data_policy": {
            "jev": "public goal/state/candidates/history text only",
            "peer": "same public state and bound synthetic 1280x720 PNG",
        },
        "policy_injection": "serial standalone process; restore VisualSelector binding in finally",
        "authorization_origin": "user: 开始直到完成实测; digest binds integrity, not a user-quoted new hash",
        "sample_scope": "6 new-content seeds in known product/template families; 36 development trials, not holdout confirmation",
    }
    if boundary:
        result.update(
            revision="action-admission-boundary-1",
            policies=["v", "ja"],
            qualification_known_stops=[{"policy": "v", "family": "schema-title",
                                        "reason": "visual_target_unavailable", "sdk_calls": 0}],
            completion_readback="Actual unique public predicate, requested inputs and complete returned list; no private target oracle",
            authorization_origin="user: 继续执行到得出结论",
            sample_scope="12 new task instances in known products, new pages/fields/semantic boundaries; 24 cold two-policy development trials",
        )
    result["sha256"] = digest(result)
    return result


def prepare(output: Path, *, sql_python: Path, link_root: Path, namespace: str,
            boundary: bool = False) -> dict:
    if not output.is_absolute():
        raise ValueError("absolute new output directory required")
    frozen = freeze_inputs(sql_python, link_root, namespace, boundary=boundary)
    output.mkdir(exist_ok=False)
    for name, expected in frozen["source_sha256"].items():
        data = (ROOT / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("source drift during preparation")
        path = output / "source" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (output / "freeze.json").write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2) + "\n"
    )
    return frozen


def load_freeze(output: Path, approved: str) -> dict:
    frozen = json.loads((output / "freeze.json").read_text())
    if (
        frozen["sha256"] != approved
        or digest({k: v for k, v in frozen.items() if k != "sha256"}) != approved
    ):
        raise ValueError("study freeze changed")
    if (
        frozen["source_sha256"] != sources()
        or frozen["versions"] != {n: version(n) for n in PACKAGES}
        or frozen["models"]
        != {"jev": calibration.base.JEV, "peer": calibration.base.PEER}
    ):
        raise ValueError("study runtime/model drift")
    for name, expected in frozen["source_sha256"].items():
        if (
            hashlib.sha256((output / "source" / name).read_bytes()).hexdigest()
            != expected
        ):
            raise ValueError("saved source changed")
    apps = frozen["apps"]
    if (
        calibration.shared.app_manifest(Path(apps["sqlite-web"]["python"]))
        != apps["sqlite-web"]
        or calibration.link.app_manifest(Path(apps["linkding"]["python"]))
        != apps["linkding"]
    ):
        raise ValueError("qualified product drift")
    return frozen


def eligible_aliases(packet: dict) -> set[str]:
    """Independent packet representation of the frozen mechanical text predicate."""
    from collections import Counter

    criteria = {
        k: v
        for k, v in packet["questions"]["next_action"]["criteria"].items()
        if isinstance(v, dict)
    }
    identities = {}
    for alias, value in criteria.items():
        effects = [
            (
                "checkbox:checked"
                if value["role"] == "checkbox"
                and (
                    f["key"].startswith("dom:checked:")
                    or f["key"] == "checkbox:" + value["label"]
                )
                else f["key"],
                f["value"],
            )
            for f in value["effect"]
        ]
        changes = [
            packet["state"]["value_change_checks"][ref]
            for ref in value.get("change_refs", [])
        ]
        identities[alias] = digest(
            [
                value["role"],
                value["label"],
                value["ancestors"],
                value["current_value"],
                value["input_key"],
                effects,
                changes,
            ]
        )
    counts = Counter(identities.values())
    return {
        alias
        for alias, value in criteria.items()
        if counts[identities[alias]] == 1
        and value["label"].strip()
        and value["label"] != value["role"]
    }


def audit_policy(row: dict, path: Path) -> dict:
    from collections import defaultdict

    if not (path / "calls.jsonl").exists():
        if row.get("calls") or any(e["kind"] == "model_call" for e in row["events"]):
            raise ValueError("model-call capture missing")
        return {"text_calls": 0, "visual_calls": 0, "logical_fallbacks": 0}
    responses = {
        r["call_id"]: r["response"]
        for r in map(json.loads, (path / "calls.jsonl").read_text().splitlines())
        if "response" in r
    }
    groups = defaultdict(list)
    for call in row["calls"]:
        request = call["request"]
        peer = "messages" in request
        packet = (
            json.loads(request["messages"][1]["content"][0]["text"])
            if peer
            else json.loads(json.dumps(request, allow_nan=False))
        )
        groups[packet["state"]["binding"]["candidate_set_id"]].append(
            (call, packet, peer)
        )
    routes = {
        e["observation_id"]: e["reason"]
        for e in row["events"]
        if e["kind"] == "computer_use_route"
    }
    admissions = {
        e["candidate_set_id"]: e
        for e in row["events"]
        if e["kind"] == "computer_use_action_admission"
    }
    text_count = visual_count = fallbacks = 0
    for identity, group in groups.items():
        first = group[0][1]
        reason = routes[first["state"]["binding"]["observation_id"]]
        allowed = eligible_aliases(first)
        attempt = (
            row["policy"] == "jt"
            and reason == "jev_eligible"
            or row["policy"] == "ja"
            and bool(allowed)
            and reason in {"jev_eligible", "visual_required"}
        )
        text = [entry for entry in group if not entry[2]]
        visual = [entry for entry in group if entry[2]]
        if len(text) != int(attempt):
            raise ValueError("declared text policy differs from captured calls")
        fallback = False
        if text:
            choice = responses[text[0][0]["call_id"]]["choice"]
            offered = text[0][1]["questions"]["next_action"]["criteria"]
            accepted = isinstance(offered.get(choice), dict) and (
                row["policy"] == "jt" or choice in allowed
            )
            fallback = not accepted
            if row["policy"] == "ja":
                event = admissions[identity]
                if (
                    type(event["accepted"]) is not bool
                    or event["accepted"] != accepted
                    or event["next_route"]
                    != ("text_candidate" if accepted else "visual_fallback")
                ):
                    raise ValueError(
                        "action admission verdict differs from captured answer"
                    )
        if len(visual) != int(not attempt or fallback):
            raise ValueError("visual/fallback count differs")
        for _, packet, _ in group:
            if (
                packet["state"] != first["state"]
                or packet["questions"] != first["questions"]
            ):
                raise ValueError("fallback changed the full observation or candidates")
        text_count += len(text)
        visual_count += len(visual)
        fallbacks += fallback
    if row["policy"] != "ja" and admissions:
        raise ValueError("unexpected action-level policy event")
    if row["policy"] == "ja" and len(admissions) != text_count:
        raise ValueError("missing action admission event")
    return {
        "text_calls": text_count,
        "visual_calls": visual_count,
        "logical_fallbacks": fallbacks,
    }


async def run_trial(
    case: dict,
    slot: dict,
    output: Path,
    frozen: dict,
    ledger,
    jev_credential: str,
    peer_credential: str,
) -> dict:
    from contextlib import nullcontext
    from unittest.mock import patch
    from agent_computer_use import visual_selector

    original = jev_action_admission.VisualSelector
    if visual_selector.VisualSelector is not original:
        raise ValueError("selector namespace drift")
    context = (
        patch.object(
            visual_selector,
            "VisualSelector",
            jev_action_admission.ActionAdmissionSelector,
        )
        if slot["policy"] == "ja"
        else nullcontext()
    )
    with context:
        runner = (jev_action_boundary.run_task if frozen["revision"] == "action-admission-boundary-1"
                  else calibration.run_task)
        row = await runner(
            case,
            slot["arm"],
            output,
            frozen=frozen,
            ledger=ledger,
            jev_credential=jev_credential,
            peer_credential=peer_credential,
        )
    if visual_selector.VisualSelector is not original:
        raise ValueError("selector restoration failed")
    row.update(
        policy=slot["policy"], pair_id=case["pair_id"], negative=case["negative"]
    )
    return row


def check_diagnostics(output: Path, rows: list[dict]) -> None:
    from collections import defaultdict

    records = [
        json.loads(line)
        for line in (output / "sdk-diagnostics.jsonl").read_text().splitlines()
    ]
    groups = defaultdict(list)
    for record in records:
        groups[record["call_id"]].append(record)
    expected = {
        call["call_id"]
        for row in rows
        if row["attempted"]
        for call in row.get("calls", [])
    }
    if set(groups) != expected:
        raise ValueError("diagnostic call IDs differ")
    for identity, events in groups.items():
        if (
            [e["phase"] for e in events]
            != ["invoke_started", "invoke_returned", "call_returned"]
            or events[-1]["usage_status"] != "known"
            or events[-1]["reservation_status"] != "known"
        ):
            raise ValueError("incomplete SDK diagnostic outcome: " + identity)


async def run_batch(
    output: Path,
    approved: str,
    *,
    mode: str,
    jev_credential: str = "",
    peer_credential: str = "",
    qualification: Path | None = None,
    readiness: Path | None = None,
) -> dict:
    import asyncio
    from contextlib import nullcontext
    from benchmarks.computer_use import (
        jev_audit as audit,
        jev_execution as execution,
        jev_fake_http,
    )
    from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit

    frozen = load_freeze(output, approved)
    if mode not in {"fake", "live"}:
        raise ValueError("declared study mode required")
    if mode == "live":
        check_live_ready(output, frozen, qualification, readiness)
        if not jev_credential.strip() or not peer_credential.strip():
            raise ValueError("both model credentials required")
    if any(
        (output / name).exists()
        for name in ("started.json", "result.json", "spend.jsonl")
    ):
        raise FileExistsError("started study cannot resume")
    with (output / "started.json").open("x") as stream:
        json.dump({"sha256": approved, "mode": mode}, stream)
    (output / "trials").mkdir()
    rows = [
        {**slot, "status": "not_run", "attempted": False, "cleanup_confirmed": False}
        for slot in frozen["schedule"]
    ]
    cases = {c["id"]: c for c in frozen["cases"]}
    ledger = SpendLedger(
        SpendLimit(0, 0), record_only=True, journal=output / "spend.jsonl"
    )
    result = {
        "sha256": approved,
        "mode": mode,
        "completed": False,
        "rows": rows,
        "formal_confirmation": False,
    }

    def persist():
        result["spend"] = ledger.snapshot()
        (output / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )

    def restore(row: dict) -> None:
        path = output / "trials" / row["id"] / "row.json"
        if path.exists():
            row.update(json.loads(path.read_text()))

    persist()
    boundary = frozen["revision"] == "action-admission-boundary-1"
    auditor = jev_action_boundary.audit_trial if boundary else audit.audit_trial
    transport_context = (
        jev_fake_http.offline_http(jev_action_boundary.reply if boundary else jev_fake_http.reply,
                                  output / "fake-http.jsonl")
        if mode == "fake"
        else nullcontext(None)
    )
    try:
        with (
            transport_context as transport,
            jev_sdk_diagnostics.sdk_diagnostics(output / "sdk-diagnostics.jsonl"),
        ):
            for row in rows:
                try:
                    load_freeze(output, approved)
                    row.update(attempted=True, status="started")
                    persist()
                    if transport is not None:
                        transport["active_trial"] = row["id"]
                    row.update(
                        await run_trial(
                            cases[row["case"]],
                            row,
                            output / "trials",
                            frozen,
                            ledger,
                            jev_credential or "fixture-only",
                            peer_credential or "fixture-only",
                        )
                    )
                    path = output / "trials" / row["id"]
                    execution.audit_usage(row, ledger.snapshot(), path)
                    if transport is not None:
                        audit.audit_usage(
                            row,
                            ledger.snapshot(),
                            [
                                t
                                for t in transport["requests"]
                                if t["trial_id"] == row["id"]
                            ],
                        )
                    row["labels"] = auditor(cases[row["case"]], row, path)
                    row["policy_metrics"] = audit_policy(row, path)
                    if (
                        row["labels"]["critical_events"]
                        or row["labels"]["unexpected_action"]
                    ):
                        ledger.stop("critical_action")
                except asyncio.CancelledError:
                    restore(row)
                    ledger.stop("cancelled")
                    row["status"] = "cancelled"
                    raise
                except Exception as error:
                    restore(row)
                    row.update(status="error", error_type=type(error).__name__)
                    ledger.stop("operational_error")
                persist()
                if ledger.snapshot()["stop_reason"]:
                    break
            result["completed"] = not ledger.snapshot()["stop_reason"] and all(
                row["status"] == "finished"
                and row["cleanup_confirmed"]
                and "labels" in row
                for row in rows
            )
            if result["completed"]:
                check_diagnostics(output, rows)
            result["fake_external_requests"] = (
                len(transport["blocked_external"]) if transport is not None else None
            )
    except BaseException:
        ledger.stop("batch_error")
        result["completed"] = False
        raise
    finally:
        ledger.close()
        persist()
    return result


def audit_study(output: Path, approved: str) -> dict:
    from benchmarks.computer_use import jev_audit as audit, jev_execution as execution

    frozen = load_freeze(output, approved)
    result = json.loads((output / "result.json").read_text())
    rows = result["rows"]
    started = json.loads((output / "started.json").read_text())
    if (
        started != {"sha256": approved, "mode": result["mode"]}
        or result["mode"] not in {"fake", "live"}
        or result["spend"]["stop_reason"] is not None
        or any(
            r["status"] != "finished" or r["cleanup_confirmed"] is not True
            for r in rows
        )
        or result["sha256"] != approved
        or [r["id"] for r in rows] != [s["id"] for s in frozen["schedule"]]
        or result["completed"] is not True
        or any(r["attempted"] is not True for r in rows)
    ):
        raise ValueError("complete planned study evidence required")
    cases = {c["id"]: c for c in frozen["cases"]}
    policies = {
        p: {
            "positive_planned": 8,
            "positive_passed": 0,
            "negative_planned": 4,
            "negative_passed": 0,
            "text_calls": 0,
            "visual_calls": 0,
            "logical_fallbacks": 0,
            "critical_events": 0,
        }
        for p in frozen.get("policies", POLICIES)
    }
    for row, slot in zip(rows, frozen["schedule"]):
        if any(row[k] != slot[k] for k in slot):
            raise ValueError("planned row identity drift")
        path = output / "trials" / row["id"]
        execution.audit_usage(row, result["spend"], path)
        auditor = (jev_action_boundary.audit_trial if frozen["revision"] == "action-admission-boundary-1"
                   else audit.audit_trial)
        labels = auditor(cases[row["case"]], row, path)
        metrics = audit_policy(row, path)
        if labels != row["labels"] or metrics != row["policy_metrics"]:
            raise ValueError("saved labels or policy metrics differ from raw evidence")
        total = policies[row["policy"]]
        total[
            "negative_passed" if cases[row["case"]]["negative"] else "positive_passed"
        ] += int(
            labels["negative_verified"]
            if cases[row["case"]]["negative"]
            else labels["strict_verified"]
        )
        for key in metrics:
            total[key] += metrics[key]
        total["critical_events"] += labels["critical_events"]
    check_diagnostics(output, rows)
    if result["mode"] == "fake":
        transport = [
            json.loads(line)
            for line in (output / "fake-http.jsonl").read_text().splitlines()
        ]
        for row in rows:
            audit.audit_usage(
                row,
                result["spend"],
                [t for t in transport if t["trial_id"] == row["id"]],
            )
        if result["fake_external_requests"] != 0:
            raise ValueError("fake qualification external egress")
    report = {
        "freeze_sha256": approved,
        "mode": result["mode"],
        "complete": True,
        "planned": len(rows),
        "policies": policies,
        "sdk_calls": len(result["spend"]["requests"]),
        "known_tokens": result["spend"]["batch"]["known_tokens"],
        "result_sha256": hashlib.sha256(
            (output / "result.json").read_bytes()
        ).hexdigest(),
        "diagnostics_sha256": hashlib.sha256(
            (output / "sdk-diagnostics.jsonl").read_bytes()
        ).hexdigest(),
        "scope": "source-bound development measurement; not formal confirmation or physical HTTP billing",
    }
    report["sha256"] = digest(report)
    return report


def check_live_ready(
    output: Path, frozen: dict, qualification: Path | None, readiness: Path | None
) -> None:
    if frozen["revision"] == "action-admission-boundary-1":
        jev_action_boundary.check_readiness(output, frozen, qualification, readiness)
        return
    if (
        qualification is None
        or readiness is None
        or qualification.resolve() == output.resolve()
    ):
        raise ValueError("distinct fake qualification and reviewed readiness required")
    report = audit_study(qualification, frozen["sha256"])
    if report["mode"] != "fake" or any(
        p["positive_passed"] != 8 or p["negative_passed"] != 4 or p["critical_events"]
        for p in report["policies"].values()
    ):
        raise ValueError("source-bound fake business qualification incomplete")
    ready = json.loads(readiness.read_text())
    if (
        ready["freeze_sha256"] != frozen["sha256"]
        or ready["source_sha256"] != frozen["source_sha256"]
        or ready["qualification_sha256"] != report["sha256"]
        or ready["review_passed"] is not True
        or ready["verification_passed"] is not True
    ):
        raise ValueError("reviewed readiness binding differs")
    for key in ("review", "verification"):
        binding = ready[key]
        if (
            hashlib.sha256(Path(binding["path"]).read_bytes()).hexdigest()
            != binding["sha256"]
        ):
            raise ValueError("review/verification receipt changed")
    review = json.loads(Path(ready["review"]["path"]).read_text())
    if (
        review.get("source_sha256") != frozen["source_sha256"]
        or review.get("unresolved_findings") != []
        or review.get("editing_stopped") is not True
    ):
        raise ValueError("source-bound review incomplete")
    verification = json.loads(Path(ready["verification"]["path"]).read_text())
    expected = {
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
    if (
        verification["source_sha256"] != frozen["source_sha256"]
        or set(verification["checks"]) != expected
        or any(
            type(c["exit_code"]) is not int or c["exit_code"] != 0
            for c in verification["checks"].values()
        )
    ):
        raise ValueError("required verification incomplete")
    for entry in verification["checks"].values():
        if (
            hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest()
            != entry["sha256"]
        ):
            raise ValueError("verification log changed")
    authorization = ready["authorization"]
    if (
        authorization["origin"] != "user: 开始直到完成实测"
        or authorization["models"] != frozen["models"]
        or authorization["data_policy"] != frozen["data_policy"]
        or authorization["record_only"] is not True
        or authorization["planned_trials"] != 36
    ):
        raise ValueError("authorization scope differs")


def main() -> None:
    import argparse
    import asyncio
    import os

    os.environ["LANGFUSE_TRACING_ENABLED"] = "false"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "fake", "run", "audit"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sql-python", type=Path)
    parser.add_argument("--link-root", type=Path)
    parser.add_argument("--namespace")
    parser.add_argument("--boundary", action="store_true")
    parser.add_argument("--approved-sha256")
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--readiness", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        if (
            not args.sql_python
            or not args.link_root
            or not args.namespace
            or args.approved_sha256
        ):
            parser.error("prepare requires product paths/namespace and no digest")
        frozen = prepare(
            args.output,
            sql_python=args.sql_python,
            link_root=args.link_root,
            namespace=args.namespace,
            boundary=args.boundary,
        )
        print(
            json.dumps({"sha256": frozen["sha256"], "trials": len(frozen["schedule"])})
        )
        return
    if not args.approved_sha256 or args.sql_python or args.link_root or args.namespace or args.boundary:
        parser.error("execution/audit uses only the frozen digest and inputs")
    if args.command == "audit":
        report = audit_study(args.output, args.approved_sha256)
        (args.output / "audit.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps(report, ensure_ascii=False))
        return
    credentials = {}
    if args.command == "run":
        frozen = load_freeze(args.output, args.approved_sha256)
        check_live_ready(args.output, frozen, args.qualification, args.readiness)
        from dotenv import dotenv_values

        values = {**dotenv_values(ROOT / "core/.env"), **os.environ}
        credentials = {
            "jev_credential": values.get("TYPESAFE_API_KEY") or "",
            "peer_credential": values.get("OPENROUTER_API_KEY") or "",
        }
    result = asyncio.run(
        run_batch(
            args.output,
            args.approved_sha256,
            mode="fake" if args.command == "fake" else "live",
            qualification=args.qualification,
            readiness=args.readiness,
            **credentials,
        )
    )
    print(
        json.dumps(
            {
                "completed": result["completed"],
                "attempted": sum(r["attempted"] for r in result["rows"]),
                "planned": len(result["rows"]),
                "stop_reason": result["spend"]["stop_reason"],
            }
        )
    )
    raise SystemExit(0 if result["completed"] else 1)


if __name__ == "__main__":
    main()
