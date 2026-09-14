"""A12: computer-use doctor — report structure, verdicts, fix hints."""

from __future__ import annotations

from tank_backend.tools.computer_doctor import (
    FAIL,
    OK,
    WARN,
    CheckResult,
    DoctorReport,
    format_report,
)


def _report(*checks: CheckResult) -> DoctorReport:
    return DoctorReport(platform="linux", checks=list(checks))


def test_exit_code_zero_when_all_ok():
    r = _report(CheckResult("a", OK, "fine"))
    assert r.exit_code == 0


def test_exit_code_one_on_any_fail():
    r = _report(
        CheckResult("a", OK, "fine"),
        CheckResult("clipboard", FAIL, "missing", "install x"),
    )
    assert r.exit_code == 1


def test_exit_code_two_when_screenshot_dead():
    r = _report(CheckResult("screenshot", FAIL, "nope"))
    assert r.exit_code == 2  # unusable, not merely degraded


def test_warn_does_not_fail_the_report():
    r = _report(CheckResult("a", WARN, "meh", "consider"))
    assert r.exit_code == 0


def test_as_dict_shape():
    data = _report(CheckResult("a", FAIL, "boom", "fix it")).as_dict()
    assert data["exit_code"] == 1
    assert data["checks"][0] == {
        "name": "a", "status": "fail", "detail": "boom", "fix": "fix it",
    }


def test_format_report_includes_fix_and_verdict():
    text = format_report(
        _report(CheckResult("clipboard", FAIL, "missing", "apt install wl-clipboard"))
    )
    assert "✗ clipboard" in text
    assert "apt install wl-clipboard" in text
    assert "verdict: DEGRADED" in text
