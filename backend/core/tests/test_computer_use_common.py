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
        ([100], None),  # too short even for the 2-element point form
        ([100, 100, 200, "x"], None),
    ],
)
def test_normalize_point_rejects_bad_input(x, y):
    assert normalize_point(x, y) is None


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        ([180, 168], None, (180, 168)),  # legacy 2-element list (macOS quirk)
        ("380", "310", (380, 310)),  # numeric strings
    ],
)
def test_normalize_point_extra_model_quirks(x, y, expected):
    assert normalize_point(x, y) == expected


# ── cross-platform contract ───────────────────────────────────────────


def _param_map(tool_info):
    return {p.name: p.description for p in tool_info.parameters}


COORD_TOOLS = ("ClickTool", "ScrollTool", "MouseMoveTool")


def test_coordinate_descriptions_identical_across_platforms():
    """A1: click/scroll/mouse_move must advertise identical schemas on
    Linux and macOS — the same model must work unchanged on either."""
    from tank_backend.tools import computer_use as linux_mod
    from tank_backend.tools import computer_use_macos as macos_mod

    for name in COORD_TOOLS:
        linux_params = _param_map(getattr(linux_mod, name)().get_info())
        macos_params = _param_map(getattr(macos_mod, name)().get_info())
        assert linux_params == macos_params, name


async def test_bbox_click_center_end_to_end_both_platforms():
    """E1: a bbox in x clicks its center on both platforms."""
    from unittest.mock import patch

    from tank_backend.tools import computer_use as linux_mod
    from tank_backend.tools import computer_use_macos as macos_mod

    with (
        patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
        patch("tank_backend.tools.computer_use._run_pyautogui") as linux_mock,
        patch("tank_backend.tools.computer_use._screen_size", (1000, 1000)),
    ):
        result = await linux_mod.ClickTool().execute(x=[100, 100, 200, 200])
    assert result.error is False
    assert "(150, 150)" in result.content  # normalized center reported
    linux_mock.assert_called_once_with("click", 150, 150, button="left", clicks=1)

    with patch("tank_backend.tools.computer_use_macos._normalized_to_pixel") as n2p:
        n2p.return_value = (150, 150)
        with patch("tank_backend.tools.computer_use_macos._click_macos") as mac_mock:
            result = await macos_mod.ClickTool().execute(x=[100, 100, 200, 200])
    assert result.error is False
    n2p.assert_called_once_with(150, 150)
    mac_mock.assert_called_once()
