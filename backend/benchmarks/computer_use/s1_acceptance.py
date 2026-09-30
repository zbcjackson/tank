"""Local Vision acceptance on frozen synthetic frames; no capture or network calls.

Run from backend: uv run --no-sync python -m benchmarks.computer_use.s1_acceptance
Output is JSON on stdout; redirect to an acceptance artifact after freezing inputs.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

from agent_computer_use.contracts import Element
from agent_computer_use.vision import recognize_text

from tank_backend.tools.computer_observation import Observation

FIXTURES = Path(__file__).parent / "fixtures/s1"


def score_regions(elements: tuple[Element, ...], truths: list[dict[str, Any]]) -> dict[str, Any]:
    """One-to-one exact text matches; duplicates must each have spatial evidence."""
    remaining = list(truths)
    hits = 0
    errors = []
    false_matches = 0
    for element in elements:
        if element.bounds is None:
            false_matches += 1
            continue
        x, y, w, h = element.bounds
        cx, cy = x + w / 2, y + h / 2
        found = next((item for item in remaining if item["text"] == element.label
                      and item["bounds"][0] <= cx <= item["bounds"][2]
                      and item["bounds"][1] <= cy <= item["bounds"][3]), None)
        if found is None:
            false_matches += 1
            continue
        remaining.remove(found)
        hits += 1
        left, top, right, bottom = found["bounds"]
        errors.append(math.hypot(cx - (left + right) / 2, cy - (top + bottom) / 2))
    return {"expected": len(truths), "hits": hits, "false_matches": false_matches,
            "center_errors_px": errors}


def evaluate() -> dict[str, Any]:
    manifest_bytes = (FIXTURES / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    results = []
    for case in manifest["cases"]:
        png = (FIXTURES / case["image"]).read_bytes()
        if hashlib.sha256(png).hexdigest() != case["sha256"]:
            raise ValueError("Frozen S1 image changed")
        frame, png = Observation.capture(png, session_id="s1-offline", display_id=1)
        elements = recognize_text(frame, png)
        results.append({"id": case["id"], "split": case["split"],
                        "category": case["category"], **score_regions(elements, case["texts"]),
                        "regions": [asdict(element) for element in elements]})
    splits = {}
    for split in ("calibration", "holdout"):
        cases = [item for item in results if item["split"] == split]
        expected = sum(item["expected"] for item in cases)
        hits = sum(item["hits"] for item in cases)
        false_matches = sum(item["false_matches"] for item in cases)
        splits[split] = {"expected": expected, "hits": hits, "recall": hits / expected,
                         "false_matches": false_matches,
                         "passed": hits / expected >= manifest["thresholds"]["ocr_recall"]
                         and false_matches == manifest["thresholds"]["ocr_false_matches"]}
    return {"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "macos": platform.mac_ver()[0], "vision_binding": version("pyobjc-framework-Vision"),
            "revision": 3, "splits": splits, "cases": results,
            "mode": "auxiliary_only", "desktop_input": False, "model_requests": 0}


if __name__ == "__main__":
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))
