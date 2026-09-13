"""Platform-agnostic input normalization for computer-use tools.

Models don't always emit the argument shapes the schema asks for. Two
forms showed up in the 2026-09-11 baseline traces and must be accepted
by BOTH platform backends:

- ``keys='["return"]'`` — a JSON-encoded array where a plain key string
  was declared (qwen);
- ``x=[100, 100, 200, 200]`` — a bbox quadruple where a point was
  declared (Qwen-VL emits 0-1000 bboxes natively; clicking a corner
  misses small targets).

All normalization lives here so Linux and macOS stay behaviorally
identical; platform files call these at tool entry.
"""

from __future__ import annotations

import json
from typing import Any, cast

# Canonical spellings for keys that models write inconsistently.
_KEY_SYNONYMS = {"return": "enter"}

# Appended to every screenshot result, identically on both platforms —
# the coordinate contract the models are told to follow.
COORDINATE_NOTE = (
    "When reporting element positions, use NORMALIZED coordinates "
    "on a 0-1000 scale where (0, 0) is the top-left corner and "
    "(1000, 1000) is the bottom-right corner. "
    "For example, the center of the screen is (500, 500). "
    "All coordinate tools (click, scroll, mouse_move) expect this "
    "0-1000 normalized format."
)


def normalized_to_pixel(
    nx: int, ny: int, size: tuple[int, int]
) -> tuple[int, int]:
    """Map a 0-1000 normalized point to pixel space for ``size``."""
    w, h = size
    return round(nx * (w - 1) / 1000), round(ny * (h - 1) / 1000)


# Coordinate parameter descriptions — identical strings on both platforms
# (a cross-platform consistency test pins this).
COORDINATE_X_DESCRIPTION = (
    "X coordinate (0-1000 normalized); a bbox array [x1,y1,x2,y2] is "
    "accepted (its center is used)"
)
COORDINATE_Y_DESCRIPTION = "Y coordinate (0-1000 normalized)"


def _as_part_list(raw: Any) -> list[str] | None:
    """Coerce str/list input into a '+'-joined lowercase string."""
    if isinstance(raw, list):
        if not raw or not all(isinstance(k, str) for k in raw):
            return None
        joined = "+".join(raw)
    elif isinstance(raw, str):
        joined = raw.strip()
    else:
        return None
    if not joined:
        return None
    # Unwrap one level of JSON encoding: '["return"]' / '["cmd", "c"]'.
    # A bracket-wrapped string that isn't valid JSON is a mangled model
    # artifact, never a real key name — reject it outright.
    if joined.startswith("[") and joined.endswith("]"):
        try:
            parsed = json.loads(joined)
        except ValueError:
            return None
        if not (isinstance(parsed, list) and parsed):
            return None
        if not all(isinstance(k, str) for k in parsed):
            return None
        joined = "+".join(parsed)
    return joined


def normalize_keys(raw: Any) -> list[str] | None:
    """Normalize a key argument to a list of lowercase parts.

    Returns ``None`` when the input can't be interpreted — callers turn
    that into an error result listing valid key names (models can then
    self-correct on the next turn).
    """
    joined = _as_part_list(raw)
    if joined is None:
        return None
    parts = [p.strip().lower() for p in joined.split("+")]
    parts = [_KEY_SYNONYMS.get(p, p) for p in parts if p]
    return parts or None


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _num(v: Any) -> int | None:
    """Coerce int/float/numeric-string to int; None otherwise."""
    if _is_number(v):
        return int(v)
    if isinstance(v, str):
        try:
            return int(float(v))
        except ValueError:
            return None
    return None


def _clamp(v: int) -> int:
    return max(0, min(1000, v))


def normalize_point(x: Any, y: Any) -> tuple[int, int] | None:
    """Normalize a coordinate argument to a clamped 0-1000 point.

    Accepted forms (observed across models):
    - ``(x: int, y: int)`` — declared shape (numeric strings tolerated);
    - ``x=[x1, y1]`` — a 2-element list (legacy macOS quirk);
    - ``x=[x1, y1, x2, y2]`` — a bbox (Qwen-VL native); its CENTER is used.

    Lists may arrive JSON-encoded as strings. Returns ``None`` otherwise.
    """
    seq: Any = x
    if isinstance(seq, str):
        try:
            seq = json.loads(seq)
        except ValueError:
            seq = None
    if isinstance(seq, (list, tuple)):
        nums = [_num(v) for v in seq[:4]]
        if any(n is None for n in nums) or len(seq) < 2:
            return None
        if len(seq) >= 4:
            x1, y1, x2, y2 = (cast(int, n) for n in nums)
            return _clamp((x1 + x2) // 2), _clamp((y1 + y2) // 2)
        px, py = cast(int, nums[0]), cast(int, nums[1])
        return _clamp(px), _clamp(py)
    nx, ny = _num(x), _num(y)
    if nx is None or ny is None:
        return None
    return _clamp(nx), _clamp(ny)
