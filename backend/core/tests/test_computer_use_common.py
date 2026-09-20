"""Tests for platform-agnostic computer-use input normalization.

Evidence-driven (2026-09-11 baseline): qwen emits double-encoded key
arguments ('["return"]') and bbox arrays where a point is expected —
both platforms must normalize at the tool entry.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio.plugin  # noqa: F401 — asyncio marker support

from tank_backend.tools.computer_use_common import (
    CANONICAL_KEYS,
    normalize_keys,
    normalize_point,
)

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
        ("esc", ["escape"]),
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


async def test_bbox_keyword_click_and_conflicting_inputs_both_platforms():
    from tank_backend.tools import computer_use as linux_mod
    from tank_backend.tools import computer_use_macos as macos_mod

    for module, helper in [(linux_mod, "_run_pyautogui"), (macos_mod, "_click_macos")]:
        with (
            patch("tank_backend.tools.computer_use._ydotool_available", return_value=False),
            patch(f"{module.__name__}.{helper}") as click,
        ):
            result = await module.ClickTool().execute(bbox=[100, 100, 200, 200])
            assert not result.error and "(150, 150)" in str(result.content)
            click.assert_called_once()
            result = await module.ClickTool().execute(x=500, y=500, bbox=[100, 100, 200, 200])
            assert result.error
            assert click.call_count == 1


def test_click_raw_schema_matches_coordinate_forms_both_platforms():
    from tank_backend.tools import computer_use as linux_mod
    from tank_backend.tools import computer_use_macos as macos_mod

    linux = linux_mod.ClickTool().get_raw_schema()
    assert linux is not None and linux == macos_mod.ClickTool().get_raw_schema()
    assert linux["properties"]["x"]["anyOf"][0]["type"] == "integer"
    assert linux["properties"]["x"]["anyOf"][1]["type"] == "array"
    assert linux["properties"]["bbox"]["minItems"] == 4
    assert linux["properties"]["bbox"]["maxItems"] == 4
    assert {tuple(branch["required"]) for branch in linux["oneOf"]} == {
        ("x", "y"), ("x",), ("bbox",),
    }


# ── A4: canonical key vocabulary ──────────────────────────────────────


def test_normalize_keys_rejects_unknown_names():
    assert normalize_keys("foo+c") is None
    assert normalize_keys("enterx") is None


@pytest.mark.parametrize("key", sorted(CANONICAL_KEYS - {"cmd", "ctrl", "alt", "shift"}))
def test_every_canonical_key_has_a_macos_keycode(key):
    """The macOS keycode map must cover the whole advertised vocabulary."""
    from tank_backend.tools.computer_use_macos import _KEYCODE_MAP

    assert key in _KEYCODE_MAP, key


@pytest.mark.asyncio
async def test_linux_repeat_clamped_and_pressed():
    from tank_backend.tools import computer_use as m

    with (
        patch(f"{m.__name__}._ydotool_available", return_value=False),
        patch(f"{m.__name__}._run_pyautogui") as mock,
    ):
        result = await m.KeyPressTool().execute(keys="enter", repeat=99)
    assert result.error is False
    assert mock.call_count == 20  # clamped to 1-20
    assert "×20" in result.content


@pytest.mark.asyncio
async def test_linux_modifier_aliases_per_backend():
    from tank_backend.tools import computer_use as m

    # pyautogui (X11): cmd → winleft
    with (
        patch(f"{m.__name__}._ydotool_available", return_value=False),
        patch(f"{m.__name__}._run_pyautogui") as mock,
    ):
        await m.KeyPressTool().execute(keys="cmd+c")
    mock.assert_called_once_with("hotkey", "winleft", "c")

    # ydotool: cmd → meta (libevdev name)
    with (
        patch(f"{m.__name__}._ydotool_available", return_value=True),
        patch(f"{m.__name__}._key_ydotool") as mock,
    ):
        await m.KeyPressTool().execute(keys="cmd+c")
    mock.assert_called_once_with(["meta", "c"])


@pytest.mark.asyncio
async def test_macos_repeat_presses_multiple_times():
    from tank_backend.tools import computer_use_macos as m

    with patch(f"{m.__name__}._key_macos") as mock:
        result = await m.KeyPressTool().execute(keys="cmd+c", repeat=3)
    assert result.error is False
    assert mock.call_count == 3
    mock.assert_called_with(["cmd", "c"])


def test_observation_maps_actual_crop_pixels_to_screen():
    """Non-even crop edges must match the pixels actually sent to the model."""
    import io

    from PIL import Image

    from tank_backend.tools.computer_observation import Observation

    source = io.BytesIO()
    Image.new("RGB", (1001, 701), "red").save(source, format="PNG")
    observation, png = Observation.capture(
        source.getvalue(), session_id="one", display_id=5,
        region=(333, 200, 666, 800),
    )
    with Image.open(io.BytesIO(png)) as image:
        assert observation.image_size == image.size
    assert observation.map_point(0, 0) == (333, 140)
    width, height = observation.image_size
    assert observation.map_point(width / 2, height / 2) == (500, 351)


@pytest.mark.parametrize("point", [(-1, 0), (640, 0), (0, 480), (True, 2),
                                   ("1", 2), (float("nan"), 2), (float("inf"), 2)])
def test_observation_rejects_invalid_image_points(point):
    import io

    from PIL import Image

    from tank_backend.tools.computer_observation import Observation

    source = io.BytesIO()
    Image.new("RGB", (640, 480)).save(source, format="PNG")
    observation, _ = Observation.capture(source.getvalue(), session_id="one", display_id=5)
    with pytest.raises(ValueError, match="image"):
        observation.map_point(*point)
