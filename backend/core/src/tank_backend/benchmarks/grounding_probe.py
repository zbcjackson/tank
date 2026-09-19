"""Synthetic-only diagnostic; never execute model actions or capture the desktop."""

from __future__ import annotations

import json
import math


def response_point(arguments: dict) -> tuple[float, float] | None:
    """Decode a diagnostic response without assuming a coordinate range."""
    values = arguments.get("bbox", arguments.get("x"))
    if "bbox" in arguments and ("x" in arguments or "y" in arguments):
        return None
    if not isinstance(values, list):
        if "bbox" in arguments:
            return None
        values = [values, arguments.get("y")]
    if len(values) not in (2, 4):
        return None
    nums: list[float] = []
    try:
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                return None
            nums.append(float(value))
    except (ValueError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in nums):
        return None
    if len(nums) == 4:
        return (nums[0] + nums[2]) / 2, (nums[1] + nums[3]) / 2
    return nums[0], nums[1]


def text_response_point(text: str, *, native_bbox: bool = False) -> tuple[float, float] | None:
    """Score a whole JSON answer, optionally fenced; never repair broken JSON."""
    text = text.strip()
    if text.startswith("```json\n") and text.endswith("\n```"):
        text = text[len("```json\n"):-len("\n```")]
    try:
        arguments = json.loads(text)
    except json.JSONDecodeError:
        return None
    if native_bbox:
        if not isinstance(arguments, list) or len(arguments) != 1:
            return None
        item = arguments[0]
        box = item.get("bbox_2d") if isinstance(item, dict) else None
        if not isinstance(box, list) or len(box) != 4:
            return None
        return response_point({"bbox": box})
    return response_point(arguments) if isinstance(arguments, dict) else None


def score_point(
    point: tuple[float, float], size: tuple[int, int], target: tuple[float, float],
) -> dict[str, float]:
    """Distance in original-image pixels under three explicit hypotheses."""
    x, y = point
    w, h = size
    scale = min(1, 1280 / max(size))
    candidates = {
        "normalized": (x * w / 1000, y * h / 1000),
        "pixels": (x, y),
        "long_edge_1280": (x / scale, y / scale),
    }
    return {name: math.dist(candidate, target) for name, candidate in candidates.items()}
