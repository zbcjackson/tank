"""Tests for platform-agnostic computer-use input normalization.

Evidence-driven (2026-09-11 baseline): qwen emits double-encoded key
arguments ('["return"]') and bbox arrays where a point is expected —
both platforms must normalize at the tool entry.
"""

from __future__ import annotations

import pytest

from tank_backend.tools.computer_use_common import normalize_keys, normalize_point

# ── normalize_keys ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("enter", ["enter"]),
        (" cmd+c ", ["cmd", "c"]),
        ("CTRL+ALT+DELETE", ["ctrl", "alt", "delete"]),
        # Real qwen artifact: JSON-encoded array instead of a plain string
        ('["return"]', ["enter"]),  # also exercises the return→enter synonym
        ('["cmd", "c"]', ["cmd", "c"]),
        ("return", ["enter"]),
        (["cmd", "c"], ["cmd", "c"]),  # model sent an actual list
    ],
)
def test_normalize_keys_accepts_model_quirks(raw, expected):
    assert normalize_keys(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "  ", "[]", "[]]", "[1, 2]"])
def test_normalize_keys_rejects_garbage(raw):
    assert normalize_keys(raw) is None


# ── normalize_point ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        (500, 500, (500, 500)),
        (0, 0, (0, 0)),
        (1000, 1000, (1000, 1000)),
        (1200, -5, (1000, 0)),  # clamped
        # bbox [x1, y1, x2, y2] → center (Qwen-VL native output form)
        ([100, 100, 200, 200], None, (150, 150)),
        ([0, 0, 999, 999], None, (499, 499)),
        ([100, 100, 200, 200], 999, (150, 150)),  # y ignored when bbox given
        ('[100, 100, 200, 200]', None, (150, 150)),  # JSON-encoded bbox
    ],
)
def test_normalize_point_forms(x, y, expected):
    assert normalize_point(x, y) == expected


@pytest.mark.parametrize(
    ("x", "y"),
    [
        (None, None),
        (500, None),  # point form requires both
        ("abc", 500),
        ([100, 200], None),  # too short for a bbox
        ([100, 100, 200, "x"], None),
    ],
)
def test_normalize_point_rejects_bad_input(x, y):
    assert normalize_point(x, y) is None
