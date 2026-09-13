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
from typing import Any

# Canonical spellings for keys that models write inconsistently.
_KEY_SYNONYMS = {"return": "enter"}


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


def _clamp(v: int) -> int:
    return max(0, min(1000, v))


def normalize_point(x: Any, y: Any) -> tuple[int, int] | None:
    """Normalize a coordinate argument to a clamped 0-1000 point.

    Accepts ``(x: int, y: int)`` or a bbox ``[x1, y1, x2, y2]`` in ``x``
    (list or JSON-encoded string) — bbox takes the CENTER. Returns
    ``None`` for anything else.
    """
    bbox: Any = x
    if isinstance(bbox, str):
        try:
            bbox = json.loads(bbox)
        except ValueError:
            return None
    if isinstance(bbox, (list, tuple)):
        if len(bbox) < 4 or not all(_is_number(v) for v in bbox[:4]):
            return None
        x1, y1, x2, y2 = (int(v) for v in bbox[:4])
        return _clamp((x1 + x2) // 2), _clamp((y1 + y2) // 2)
    if _is_number(x) and _is_number(y):
        return _clamp(int(x)), _clamp(int(y))
    return None
