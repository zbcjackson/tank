import json
import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


def test_business_paste_needs_current_reset_and_expression_input() -> None:
    from tank_backend.benchmarks.calc_validator import assess_calculator

    events = [
        {"kind": "trial_start"},
        {"kind": "setup_done", "stdout": '{"calculator_reset": true}'},
        {"kind": "output", "output_type": "TOOL_RESULT", "metadata": {
            "name": "type_text", "status": "success", "arguments": '{"text":"7*8"}',
        }},
    ]
    evidence = assess_calculator({"expression": "", "result": "56"}, events)
    assert evidence["strict_expression"] is False
    assert evidence["business"] is True
    assert evidence["mouse_only"] is False
    assert evidence["pixels"] == "unknown"
    events[-1]["metadata"]["arguments"] = '{"text":"56"}'
    assert assess_calculator({"result": "56"}, events)["business"] is False
    assert assess_calculator({"result": "56"}, events[:1])["business"] is None


def test_mouse_track_and_screenshot_feedback_do_not_reuse_previous_trial() -> None:
    from tank_backend.benchmarks.calc_validator import assess_calculator

    events: list[dict[str, Any]] = [{"kind": "trial_start"},
              {"kind": "setup_done", "stdout": '{"calculator_reset":true}'}]
    events.append({"kind": "output", "output_type": "TOOL_RESULT", "metadata": {
        "name": "computer_batch", "status": "success", "arguments": json.dumps({
            "actions": [{"action": "click", "x": n, "y": 10} for n in range(4)],
        }),
    }})
    events.extend([{"kind": "screenshot", "sha256": "abc", "ts": 2, "file": "shot.png"},
                   {"kind": "http_request", "image_sha256": ["abc"], "ts": 3}])
    evidence = assess_calculator({"expression": "7×8", "result": "56"}, events)
    assert evidence["business"] is True and evidence["mouse_only"] is True
    assert evidence["last_screenshot"]["http_serialized_at"] == 3
    assert evidence["pixels"] == "unknown"  # hash/AX are not pixel grading
    events.append({"kind": "screenshot", "sha256": "new", "ts": 4, "file": "new.png"})
    assert assess_calculator({}, events)["last_screenshot"]["http_serialized_at"] is None
    events.append({"kind": "trial_start"})
    stale = assess_calculator({"expression": "7×8", "result": "56"}, events)
    assert stale["business"] is None and stale["mouse_only"] is None
    assert stale["last_screenshot"] is None


def test_unfinished_input_cannot_reuse_earlier_success() -> None:
    from tank_backend.benchmarks.calc_validator import assess_calculator

    events = [
        {"kind": "trial_start"},
        {"kind": "setup_done", "stdout": '{"calculator_reset":true}'},
        {"kind": "output", "output_type": "TOOL_RESULT", "metadata": {
            "name": "type_text", "status": "success", "arguments": '{"text":"7*8"}',
        }},
        {"kind": "output", "output_type": "TOOL_EXECUTING", "metadata": {
            "name": "type_text", "turn": 2, "index": 0, "arguments": '{"text":"56"}',
        }},
    ]
    assert assess_calculator({"result": "56"}, events)["business"] is None


@pytest.mark.parametrize("text, business", [("7*8", True), ("56", False)])
async def test_trial_keeps_strict_failure_and_business_evidence(
    tmp_path: Path, text: str, business: bool,
) -> None:
    from tank_backend.agents.base import AgentOutput, AgentOutputType
    from tank_backend.benchmarks.driver import DriverResult
    from tank_backend.benchmarks.runner import _run_trial
    from tank_backend.benchmarks.task import BenchTask
    from tank_backend.benchmarks.trace import TraceSink

    osascript = tmp_path / "osascript"
    osascript.write_text('#!/bin/sh\nprintf "expression=\\nresult=56\\n"\n')
    osascript.chmod(0o755)

    class Driver:
        async def run(self, instruction: str, trace: TraceSink, **kwargs: Any) -> DriverResult:
            trace.output(AgentOutput(AgentOutputType.TOOL_RESULT, metadata={
                "name": "type_text", "status": "success", "arguments": json.dumps({"text": text}),
            }))
            return DriverResult("done", 1, 0.01, 1, 0, False, cleanup="confirmed")

    task = BenchTask("calc-open", "app", 1, ("macos",), "calculate 7 times 8",
                     "python -m tank_backend.benchmarks.calc_validator",
                     setup="printf '%s' '{\"calculator_reset\":true}'", gui_only=True)
    result = await _run_trial(Driver(), task, 1, tmp_path / "run", {
        "BENCH_ASSETS_URL": "", "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
    })
    assert result.success is False  # legacy strict score is unchanged
    assert result.assessment["business"] is business
    assert result.assessment["pixels"] == "unknown"
    stored = json.loads((tmp_path / "run/trials/calc-open/1/result.json").read_text())
    assert stored["assessment"] == result.assessment


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
