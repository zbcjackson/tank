import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.parametrize("output, success", [
    ("expression=\u200e7\u200e×\u200e8\nresult=\u200e56\n", True),
    ("expression=5×7\nresult=35\n", False),
    ("expression=56\nresult=0\n", False),
    ("expression=\nresult=56\n", False),
    ("expression=7×8\nresult=560\n", False),
    ("", False),
])
def test_calculator_validates_expression_and_display(output, success):
    from tank_backend.benchmarks.calc_validator import validate_calculator

    with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, output, "")):
        assert validate_calculator() == success


@pytest.mark.parametrize("failure", [
    subprocess.CompletedProcess([], 1, "", "Calculator is not foreground"),
    subprocess.CompletedProcess([], 1, "", "Not authorized"),
    subprocess.TimeoutExpired("osascript", 20),
])
def test_calculator_fails_closed_when_display_cannot_be_read(failure):
    from tank_backend.benchmarks.calc_validator import validate_calculator

    with patch("subprocess.run") as command:
        if isinstance(failure, Exception):
            command.side_effect = failure
        else:
            command.return_value = failure
        assert not validate_calculator()


@pytest.mark.parametrize("value, expected", [("0", True), ("56", False), ("", False)])
def test_reset_requires_observed_zero_to_prevent_stale_success(value, expected):
    from tank_backend.benchmarks.calc_validator import reset_calculator

    with patch("subprocess.run", side_effect=[
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, f"result={value}\n", ""),
    ]):
        assert reset_calculator() == expected


@pytest.mark.parametrize("display, passes", [
    ("expression=7×8\nresult=56", True),
    ("expression=5×7\nresult=35", False),
])
async def test_task_shell_command_runs_real_validator(tmp_path, display, passes):
    from tank_backend.benchmarks.shell import ShellError, run_shell
    from tank_backend.benchmarks.task import load_task

    # Only the OS accessibility boundary is fake. Task loading, bash, Python
    # entry point, parsing and exit status all execute normally.
    osascript = tmp_path / "osascript"
    osascript.write_text('#!/bin/sh\nprintf "%s\\n" "$CALC_TEST_DISPLAY"\n')
    osascript.chmod(0o755)
    path = Path(__file__).resolve().parents[2] / "benchmarks/computer_use/tasks/01-calc-open.yaml"
    task = load_task(path, "macos")
    env = {"PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
           "CALC_TEST_DISPLAY": display}
    if passes:
        result = await run_shell(task.validator_command, timeout_s=10, extra_env=env)
        assert result.returncode == 0
    else:
        with pytest.raises(ShellError, match="Calculator validation failed"):
            await run_shell(task.validator_command, timeout_s=10, extra_env=env)
