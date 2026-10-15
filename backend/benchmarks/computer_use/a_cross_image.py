"""Two preannotated images, two modes, one balanced schedule and spend ledger."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from tank_backend.benchmarks.spend_ledger import SpendLedger, SpendLimit, SpendSnapshot

from . import a_preflight as static
from .s3_replay import digest

TOTAL_CAP = 2048
BATCH_NANO = 700000000
BATCH_TOKENS = 4000000


def freeze_inputs(inputs: list[Path]) -> dict[str, Any]:
    if len(inputs) != 2:
        raise ValueError("cross-image gate requires exactly two inputs")
    images = []
    base: dict[str, Any] = {}
    for index, folder in enumerate(inputs, 1):
        case = json.loads((folder / "case.json").read_bytes(), object_pairs_hook=static._unique)
        base = static.freeze_inputs((folder / "frame.png").read_bytes(), case)
        images.append({"id": f"image-{index}", "image_sha256": base["image_sha256"],
                       "annotation": base["annotation"]})
    if images[0]["image_sha256"] == images[1]["image_sha256"]:
        raise ValueError("cross-image gate requires distinct images")
    schedule = [
        {"id": f"image-{index}-{arm}", "image_id": f"image-{index}", "arm": arm,
         "max_completion_tokens": TOTAL_CAP,
         "extra_body": {"enable_thinking": False} if arm == "no-think" else {}}
        for index, arms in ((1, ("default", "no-think")), (2, ("no-think", "default")))
        for arm in arms
    ]
    sources = dict(base["source_sha256"])
    path = Path(__file__)
    sources[str(path.relative_to(path.parents[2]))] = hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = {
        "revision": "a-cross-image-1", "images": images, "schedule": schedule,
        "model": base["model"], "system": base["system"], "target": base["target"],
        "output_contract": base["output_contract"], "response_format": base["response_format"],
        "temperature": 0.1, "stream_options": {"include_usage": True},
        "seconds_per_request": base["seconds_per_request"], "source_sha256": sources,
        "packages": base["packages"], "nano_usd_limit": BATCH_NANO,
        "token_limit": BATCH_TOKENS, "request_limit": 4,
        "accounting": base["accounting"],
        "continuation": "known semantic failures continue; any ledger/runtime failure stops all",
        "candidate_gate": "only a complete settled batch and two valid no-think hits may advance to owned GUI smoke preparation",
        "inference_limit": "two images, one request per mode; no adoption or S5 confirmation conclusion",
    }
    return {**frozen, "sha256": digest(frozen)}


def prepare(inputs: list[Path], output: Path) -> dict[str, Any]:
    frozen = freeze_inputs(inputs)
    output.mkdir(parents=True, exist_ok=False)
    for index, folder in enumerate(inputs, 1):
        target = output / f"image-{index}"
        target.mkdir()
        for name in ("frame.png", "case.json"):
            (target / name).write_bytes((folder / name).read_bytes())
    (output / "freeze.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2))
    return frozen


def load_freeze(output: Path, approved: str) -> dict[str, Any]:
    frozen = freeze_inputs([output / "image-1", output / "image-2"])
    if frozen["sha256"] != approved or json.loads((output / "freeze.json").read_text()) != frozen:
        raise ValueError("cross-image freeze changed; prepare a new directory")
    return frozen


def verdict(rows: list[dict[str, Any]], completed: bool, mode: str) -> str:
    if not completed:
        return "incomplete_no_candidate_conclusion"
    if mode == "fake":
        return "fake_wiring_only_no_candidate_conclusion"
    candidate = [row for row in rows if row["arm"] == "no-think"]
    if len(candidate) == 2 and all(
        row["status"] == "finished" and row["schema_valid"] and row["within_annotation"]
        for row in candidate
    ):
        return "advance_to_owned_gui_smoke_preparation"
    return "candidate_not_qualified"


def pairs(rows: list[dict[str, Any]], spend: SpendSnapshot) -> list[dict[str, Any]]:
    results = []
    for image_id in ("image-1", "image-2"):
        group = {row["arm"]: row for row in rows if row["image_id"] == image_id}
        baseline, candidate = group["default"], group["no-think"]
        results.append({"image_id": image_id, "default": baseline["id"],
            "no_think": candidate["id"],
            "no_think_minus_default_seconds": candidate["seconds"] - baseline["seconds"],
            "no_think_minus_default_nano_usd": (
                spend["trials"][candidate["id"]]["known_nano_usd"]
                - spend["trials"][baseline["id"]]["known_nano_usd"]),
        })
    return results


async def run_batch(
    output: Path, approved: str, *, mode: str, credential: str = "",
) -> dict[str, Any]:
    frozen = load_freeze(output, approved)
    if mode not in {"fake", "live"} or (mode == "live" and not credential.strip()):
        raise ValueError("choose fake/live and provide live credentials")
    images = {item["id"]: item for item in frozen["images"]}
    pngs = {image_id: (output / image_id / "frame.png").read_bytes() for image_id in images}
    with (output / "started.json").open("x") as marker:
        json.dump({"mode": mode, "sha256": approved}, marker)
    ledger = SpendLedger(SpendLimit(frozen["token_limit"], frozen["nano_usd_limit"]),
                         request_limit=4, journal=output / "spend.jsonl")
    rows: list[dict[str, Any]] = [{"id": job["id"], "image_id": job["image_id"],
        "arm": job["arm"], "status": "not_run"} for job in frozen["schedule"]]
    report: dict[str, Any] = {"sha256": approved, "mode": mode, "rows": rows,
        "completed": False, "pairs": [], "new_gui_operations": 0}
    try:
        for row, job in zip(rows, frozen["schedule"]):
            load_freeze(output, approved)
            folder = output / job["id"]
            folder.mkdir(exist_ok=False)
            trial = {**frozen, **images[job["image_id"]]}
            await static.run_trial(folder, trial, pngs[job["image_id"]], job, ledger, row,
                                   mode=mode, credential=credential)
            report["spend"] = ledger.snapshot()
            (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            if ledger.snapshot()["stop_reason"] is not None:
                break
        report["completed"] = (ledger.snapshot()["stop_reason"] is None
            and all(row["status"] in {"finished", "failed"}
                    and row.get("usage", {}).get("status") == "returned" for row in rows))
    finally:
        try:
            ledger.close()
        except Exception:
            report["completed"] = False
            raise
        finally:
            report["spend"] = ledger.snapshot()
            report["verdict"] = verdict(rows, report["completed"], mode)
            if report["completed"]:
                report["pairs"] = pairs(rows, report["spend"])
            count = sum(item["status"] != "not_sent" for item in report["spend"]["requests"].values())
            report["external_model_requests"] = count if mode == "live" else 0
            report["fake_http_requests"] = count if mode == "fake" else 0
            (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare")
    preparation.add_argument("--input", type=Path, action="append", required=True)
    preparation.add_argument("--output", type=Path, required=True)
    execution = commands.add_parser("run")
    execution.add_argument("--output", type=Path, required=True)
    execution.add_argument("--mode", choices=("fake", "live"), required=True)
    execution.add_argument("--approved-sha256", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare(args.input, args.output)["sha256"])
    else:
        if args.mode == "live":
            from dotenv import load_dotenv

            load_dotenv(Path(__file__).resolve().parents[2] / "core/.env")
        report = await run_batch(args.output, args.approved_sha256, mode=args.mode,
                                 credential=os.environ.get("BAILIAN_API_KEY", ""))
        print(json.dumps({key: report[key] for key in ("completed", "verdict",
            "external_model_requests", "fake_http_requests", "new_gui_operations")}))


if __name__ == "__main__":
    asyncio.run(main())
