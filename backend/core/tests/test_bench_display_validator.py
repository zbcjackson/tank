"""Multi-display benchmark validator: strict window-placement checks."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tank_backend.benchmarks import display_validator as dv


def _quartz(topology, windows):
    quartz = MagicMock()
    quartz.CGGetActiveDisplayList.side_effect = (
        lambda *a: (0, tuple(e[0] for e in topology), len(topology))
    )

    def entry_for(display):
        return next(e for e in topology if e[0] == display)

    quartz.CGDisplayBounds.side_effect = lambda d: (entry_for(d)[1:3], entry_for(d)[3:5])
    quartz.CGDisplayCopyDisplayMode.side_effect = entry_for
    quartz.CGDisplayModeGetPixelWidth.side_effect = lambda m: m[5]
    quartz.CGDisplayModeGetPixelHeight.side_effect = lambda m: m[6]
    quartz.kCGWindowListOptionOnScreenOnly = 1
    quartz.CGWindowListCopyWindowInfo.return_value = [
        {
            "kCGWindowNumber": 10 + i,
            "kCGWindowOwnerName": owner,
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h},
        }
        for i, (owner, x, y, w, h) in enumerate(windows)
    ]
    return quartz


MAIN = (2, 0, 0, 1920, 1080, 3840, 2160)
SECONDARY = (5, 1920, -602, 1080, 1920, 2160, 3840)


def test_passes_when_calculator_wholly_on_secondary(monkeypatch):
    quartz = _quartz(
        [MAIN, SECONDARY], [("Calculator", 2000, -500, 400, 300)],
    )
    monkeypatch.setattr(dv, "_load_quartz", lambda: quartz)
    ok, detail = dv.calculator_on_secondary()
    assert ok, detail
    assert "display 5" in detail


def test_fails_when_calculator_only_on_main(monkeypatch):
    monkeypatch.setattr(
        dv, "_load_quartz", lambda: _quartz([MAIN, SECONDARY], [("Calculator", 100, 100, 400, 300)])
    )
    ok, detail = dv.calculator_on_secondary()
    assert not ok
    assert "non-main" in detail


def test_fails_when_window_spans_displays(monkeypatch):
    monkeypatch.setattr(
        dv, "_load_quartz",
        lambda: _quartz([MAIN, SECONDARY], [("Calculator", 1800, -500, 400, 300)]),
    )
    ok, detail = dv.calculator_on_secondary()
    assert not ok
    assert "non-main" in detail


def test_fails_without_calculator_window(monkeypatch):
    monkeypatch.setattr(
        dv, "_load_quartz", lambda: _quartz([MAIN, SECONDARY], [("Finder", 0, 0, 100, 100)])
    )
    ok, detail = dv.calculator_on_secondary()
    assert not ok
    assert "no on-screen Calculator" in detail


def test_fails_on_single_display_host(monkeypatch):
    monkeypatch.setattr(
        dv, "_load_quartz", lambda: _quartz([MAIN], [("Calculator", 100, 100, 400, 300)])
    )
    ok, detail = dv.calculator_on_secondary()
    assert not ok
    assert "only 1 display" in detail


def test_main_fails_closed_when_quartz_unreadable(monkeypatch, capsys):
    def broken():
        raise ImportError("no Quartz")

    monkeypatch.setattr(dv, "_load_quartz", broken)
    monkeypatch.setattr("sys.platform", "darwin")
    import sys

    saved = sys.argv
    sys.argv = ["display_validator", "--calculator-on-secondary"]
    try:
        assert dv.main() == 2
    finally:
        sys.argv = saved
    assert "unreadable" in capsys.readouterr().err


def test_main_requires_explicit_check(monkeypatch, capsys):
    assert dv.main() == 2
    assert "usage" in capsys.readouterr().err


@pytest.mark.parametrize("argv,expected", [(["--calculator-on-secondary"], 0), ([], 2)])
def test_main_exit_codes(monkeypatch, argv, expected):
    monkeypatch.setattr(dv, "calculator_on_secondary", lambda: (True, "ok"))
    monkeypatch.setattr("sys.platform", "darwin")
    import sys

    saved = sys.argv
    sys.argv = ["display_validator", *argv]
    try:
        assert dv.main() == expected
    finally:
        sys.argv = saved
