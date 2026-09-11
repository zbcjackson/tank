"""Tests for trace sink, runner orchestration, and driver pieces."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, cast

from tank_backend.agents.base import AgentOutput, AgentOutputType
from tank_backend.benchmarks.driver import (
    CountingLLM,
    DriverResult,
    TracedScreenshotTool,
)
from tank_backend.benchmarks.report import TrialRecord
from tank_backend.benchmarks.runner import run_suite
from tank_backend.benchmarks.shell import ShellError
from tank_backend.benchmarks.trace import TraceSink
from tank_backend.core.content import ImageBlock, TextBlock
from tank_backend.core.events import UpdateType
from tank_backend.tools.base import BaseTool, ToolInfo, ToolResult

# ---------------------------------------------------------------------------
# TraceSink
# ---------------------------------------------------------------------------


def test_trace_sink_writes_outputs_and_screenshots(tmp_path):
    sink = TraceSink(tmp_path / "trial1")
    sink.event("trial_start", task="x")
    sink.output(
        AgentOutput(type=AgentOutputType.TOKEN, content="hello", metadata={})
    )
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    rel = sink.save_screenshot(f"data:image/png;base64,{png_b64}")
    sink.close()

    lines = [
        json.loads(ln)
        for ln in (tmp_path / "trial1" / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert lines[0]["kind"] == "trial_start"
    assert lines[1]["output_type"] == "TOKEN"
    assert any(r["kind"] == "screenshot" and r["file"] == rel for r in lines)
    assert sink.screenshot_count == 1
    assert (tmp_path / "trial1" / rel).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# CountingLLM
# ---------------------------------------------------------------------------


class _FakeInnerLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def chat_stream(self, *args, **kwargs):
        self.calls += 1
        yield (UpdateType.TEXT, "hi", {})
        yield (UpdateType.USAGE, "", {"prompt_tokens": 10, "completion_tokens": 5})
        yield (UpdateType.USAGE, "", {"prompt_tokens": 7, "completion_tokens": 3})


async def test_counting_llm_accumulates_usage_and_delegates():
    inner = _FakeInnerLLM()
    counting = CountingLLM(inner)  # type: ignore[arg-type]
    items = [u async for u in counting.chat_stream()]
    assert len(items) == 3
    assert counting.total_tokens == 25
    assert counting.prompt_tokens == 17
    assert inner.calls == 1
    counting.reset()
    assert counting.total_tokens == 0


async def test_counting_llm_times_each_model_round_trip():
    # _FakeInnerLLM streams TEXT + 2 USAGE — one chat_stream call spans
    # TWO model round-trips (LLM.chat_stream runs the tool loop inside),
    # each delimited by a USAGE update. Both must be timed separately.
    counting = CountingLLM(_FakeInnerLLM())  # type: ignore[arg-type]
    _ = [u async for u in counting.chat_stream()]
    assert len(counting.call_stats) == 2
    for ttft, total in counting.call_stats:
        assert 0.0 <= ttft <= total
    counting.reset()
    assert counting.call_stats == []


async def test_counting_llm_records_round_cancelled_mid_stream():
    # A task timeout cancels chat_stream mid-round; the in-flight API
    # call still consumed wall time and must be recorded (real bug:
    # timeout trials reported llm_calls=0 because timing only ran after
    # the loop completed).
    import asyncio

    import pytest

    class _StallingLLM:
        async def chat_stream(self, *args, **kwargs):
            yield (UpdateType.TEXT, "partial", {})
            await asyncio.sleep(30)
            yield (UpdateType.USAGE, "", {"prompt_tokens": 1, "completion_tokens": 1})

    counting = CountingLLM(cast(Any, _StallingLLM()))

    async def consume() -> None:
        _ = [u async for u in counting.chat_stream()]

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(consume(), timeout=0.05)
    assert len(counting.call_stats) == 1
    ttft, total = counting.call_stats[0]
    assert ttft >= 0.0
    assert total >= 0.05  # the cancelled in-flight round


async def test_counting_llm_reports_calls_via_callback():
    seen: list[tuple[int, float, float]] = []
    counting = CountingLLM(_FakeInnerLLM())  # type: ignore[arg-type]
    counting.on_call = lambda call, ttft, total: seen.append((call, ttft, total))
    _ = [u async for u in counting.chat_stream()]
    assert [s[0] for s in seen] == [1, 2]
    assert seen[0][1] <= seen[0][2]


async def test_ttft_skips_local_tool_echoes():
    # TOOL success/error updates come from the local executor right
    # after the round boundary; ttft must wait for real model output
    # (TEXT/THOUGHT/TOOL "calling"), or every round reports 0.0.
    import asyncio

    class _ToolEchoLLM:
        async def chat_stream(self, *args, **kwargs):
            yield (UpdateType.TOOL, "ok", {"status": "success"})
            await asyncio.sleep(0.05)
            yield (UpdateType.TEXT, "hi", {})
            yield (UpdateType.USAGE, "", {"prompt_tokens": 1, "completion_tokens": 1})

    counting = CountingLLM(cast(Any, _ToolEchoLLM()))
    _ = [u async for u in counting.chat_stream()]
    ttft, total = counting.call_stats[0]
    assert ttft >= 0.05  # measured at the TEXT, not the instant tool echo
    assert total >= ttft


def test_disable_langfuse_tracing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_HOST", "http://x")
    monkeypatch.setenv("UNRELATED", "keep")
    from tank_backend.benchmarks.driver import disable_langfuse_tracing

    removed = disable_langfuse_tracing()
    # Ambient LANGFUSE_* vars may also be present — only assert ours left
    # the environment and non-Langfuse vars survive.
    assert "LANGFUSE_PUBLIC_KEY" in removed
    assert "LANGFUSE_HOST" in removed
    import os

    assert not [k for k in os.environ if k.startswith("LANGFUSE_")]
    assert os.environ["UNRELATED"] == "keep"


# ---------------------------------------------------------------------------
# TracedScreenshotTool
# ---------------------------------------------------------------------------


class _FakeScreenshotTool(BaseTool):
    def get_info(self):
        return ToolInfo(name="screenshot", description="shot", parameters=[])

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(
            content=[
                TextBlock(text="ok"),
                ImageBlock(
                    source="data:image/png;base64,aGVsbG8=", mime_type="image/png"
                ),
            ],
            display="shot",
        )


async def test_traced_screenshot_tool_archives_image(tmp_path):
    sink = TraceSink(tmp_path / "t")
    tool = TracedScreenshotTool(_FakeScreenshotTool(), lambda: sink)
    info = tool.get_info()
    assert info.name == "screenshot"
    result = await tool.execute(task="x")
    assert isinstance(result, ToolResult)
    assert not result.error
    assert sink.screenshot_count == 1
    sink.close()


async def test_traced_screenshot_tool_tolerates_no_trace():
    tool = TracedScreenshotTool(_FakeScreenshotTool(), lambda: None)
    result = await tool.execute()
    assert isinstance(result, ToolResult)
    assert not result.error


# ---------------------------------------------------------------------------
# SubAgentDriver step counting (delta streams must not count as steps)
# ---------------------------------------------------------------------------


class _StubRunner:
    """Emits the real output shape: many TOOL_CALLING deltas per call."""

    def __init__(self, tool_calls: int) -> None:
        self._tool_calls = tool_calls

    async def run_agent(self, agent_def, messages, **kwargs):
        for _ in range(self._tool_calls):
            for _ in range(8):  # streamed argument deltas
                yield AgentOutput(
                    type=AgentOutputType.TOOL_CALLING,
                    content="",
                    metadata={"name": "click", "status": "calling"},
                )
            yield AgentOutput(
                type=AgentOutputType.TOOL_EXECUTING,
                content="",
                metadata={"name": "click", "status": "executing"},
            )
            yield AgentOutput(
                type=AgentOutputType.TOOL_RESULT,
                content="Clicked",
                metadata={"name": "click", "status": "success"},
            )
        yield AgentOutput(type=AgentOutputType.TOKEN, content="done", metadata={})


async def _drive_with_stub(tool_calls: int, max_steps: int):
    from unittest.mock import MagicMock

    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.benchmarks.driver import SubAgentDriver

    agent_def = AgentDefinition(
        name="stub", description="", system_prompt="",
        disallowed_tools=frozenset(), toolset="computer_use", tool_filter=None,
        skills=(), background=False, token_budget=0, model=None,
    )
    from tank_backend.llm.llm import LLM

    class _FakeLLM:
        pass

    driver = SubAgentDriver(
        runner=cast(Any, _StubRunner(tool_calls)),
        agent_def=agent_def,
        llm=CountingLLM(cast(LLM, _FakeLLM())),
        tool_manager=MagicMock(),
    )
    with tempfile.TemporaryDirectory() as td:
        trace = TraceSink(Path(td) / "t")
        result = await driver.run("do it", trace, timeout_s=10, max_steps=max_steps)
        trace.close()
    return result


async def test_steps_count_executed_calls_not_deltas():
    """5 executed tool calls (8 argument deltas each) = 5 steps, not 40."""
    result = await _drive_with_stub(tool_calls=5, max_steps=30)
    assert result.steps == 5
    assert result.error is None
    assert result.timed_out is False
    # No LLM call was made by the stub — latency fields stay at zero.
    assert result.llm_calls == 0
    assert result.llm_total_s == 0.0


class _LlmCallingRunner(_StubRunner):
    """Stub runner that first makes one real chat_stream call."""

    def __init__(self, llm: CountingLLM) -> None:
        super().__init__(tool_calls=1)
        self._llm = llm

    async def run_agent(self, agent_def, messages, **kwargs):
        _ = [u async for u in self._llm.chat_stream()]
        async for out in super().run_agent(agent_def, messages, **kwargs):
            yield out


async def test_driver_result_carries_llm_latency():
    from unittest.mock import MagicMock

    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.benchmarks.driver import SubAgentDriver

    agent_def = AgentDefinition(
        name="stub", description="", system_prompt="",
        disallowed_tools=frozenset(), toolset="computer_use", tool_filter=None,
        skills=(), background=False, token_budget=0, model=None,
    )
    from tank_backend.llm.llm import LLM

    llm = CountingLLM(cast(LLM, _FakeInnerLLM()))
    driver = SubAgentDriver(
        runner=cast(Any, _LlmCallingRunner(llm)),
        agent_def=agent_def,
        llm=llm,
        tool_manager=MagicMock(),
    )
    with tempfile.TemporaryDirectory() as td:
        trace = TraceSink(Path(td) / "t")
        result = await driver.run("do it", trace, timeout_s=10, max_steps=10)
        llm_events = [
            json.loads(line)
            for line in (Path(td) / "t" / "trace.jsonl").read_text().splitlines()
            if '"llm_call"' in line
        ]
        trace.close()
    assert result.llm_calls == 2  # _FakeInnerLLM emits two USAGE round-trips
    assert result.llm_ttft_s >= 0.0
    assert result.llm_call_s > 0.0
    assert result.llm_total_s >= result.llm_call_s
    assert len(llm_events) == 2


async def test_max_steps_aborts_on_executed_calls():
    result = await _drive_with_stub(tool_calls=40, max_steps=5)
    assert result.steps == 6  # 5 allowed, the 6th triggers the abort
    assert "max_steps" in (result.error or "")


# ---------------------------------------------------------------------------
# Runner orchestration (fake driver)
# ---------------------------------------------------------------------------


class FakeDriver:
    """Scripted driver: decides success by touching a file, or stalls."""

    def __init__(self, behavior: str = "pass") -> None:
        self.behavior = behavior
        self.instruction: str | None = None

    async def run(self, instruction, trace, *, timeout_s, max_steps):
        self.instruction = instruction
        if self.behavior == "stall":
            # Simulates blowing the task timeout (real enforcement lives in
            # SubAgentDriver's wait_for; here we just report the outcome).
            return DriverResult(
                final_text="", steps=1, wall_s=float(timeout_s), tokens=1,
                screenshots=1, timed_out=True, error=f"timeout({timeout_s}s)",
            )
        trace.event("fake_output")
        return DriverResult(
            final_text="done",
            steps=3,
            wall_s=1.0,
            tokens=42,
            screenshots=2,
            timed_out=False,
            error=None,
        )


SUITE_YAML = """
name: smoke
agent: fake
defaults:
  timeout_s: 30
  max_steps: 10
"""

TASK_YAML = """
id: {tid}
category: file
difficulty: 1
platforms: [linux, macos]
instruction: "create {tid} marker"
setup: |
  rm -rf {work} && mkdir -p {work}
validator:
  kind: shell
  command: test -f {work}/{tid}.flag
teardown: |
  rm -rf {work}
"""


def _make_suite(tmp_path: Path) -> Path:
    suite_dir = tmp_path / "suite"
    (suite_dir / "tasks").mkdir(parents=True)
    (suite_dir / "suite.yaml").write_text(SUITE_YAML, encoding="utf-8")
    work = tmp_path / "bench-work"
    for tid in ("t1", "t2"):
        body = TASK_YAML.format(tid=tid, work=work)
        if tid == "t2":
            body += "\ntimeout_s: 1\n"
        (suite_dir / "tasks" / f"{tid}.yaml").write_text(body, encoding="utf-8")
    return suite_dir


async def test_run_suite_pass_setup_validate_report(tmp_path):
    suite_dir = _make_suite(tmp_path)
    # Driver behavior: after "running", create the flag the validator checks.
    work = tmp_path / "bench-work"

    class TouchFlagDriver(FakeDriver):
        async def run(self, instruction, trace, *, timeout_s, max_steps):
            await super().run(
                instruction, trace, timeout_s=timeout_s, max_steps=max_steps
            )
            import asyncio

            tid = "t1" if "t1" in instruction else "t2"
            proc = await asyncio.create_subprocess_exec(
                "bash", "-c", f"mkdir -p {work} && touch {work}/{tid}.flag"
            )
            await proc.wait()
            return DriverResult(
                "done", 3, 1.0, 42, 2, False, None,
                llm_calls=3, llm_ttft_s=1.5, llm_call_s=2.5, llm_total_s=7.5,
            )

    out = tmp_path / "out"
    report = await run_suite(
        suite_dir,
        lambda: TouchFlagDriver(),
        platform="linux",
        trials=2,
        out_dir=out,
        label="smoke",
    )
    assert report.total_trials == 4
    assert report.successes == 4
    assert (out / "report.md").exists()
    assert (out / "report.json").exists()
    trial_dir = out / "trials" / "t1" / "1"
    assert (trial_dir / "trace.jsonl").exists()
    assert (trial_dir / "result.json").exists()
    result_json = json.loads((trial_dir / "result.json").read_text())
    assert result_json["success"] is True
    assert result_json["llm_calls"] == 3
    assert result_json["llm_ttft_s"] == 1.5
    # teardown removed the workspace
    assert not work.exists()


async def test_run_suite_task_filter_runs_subset(tmp_path):
    import re

    suite_dir = _make_suite(tmp_path)
    out = tmp_path / "out-filtered"
    report = await run_suite(
        suite_dir,
        lambda: FakeDriver("pass"),
        platform="linux",
        trials=1,
        out_dir=out,
        label="filtered",
        task_filter=re.compile(r"^t1$"),
    )
    assert report.total_trials == 1
    assert list(report.tasks) == ["t1"]
    assert (out / "trials" / "t1" / "1" / "trace.jsonl").exists()
    assert not (out / "trials" / "t2").exists()


async def test_run_suite_validator_failure_recorded(tmp_path):
    suite_dir = _make_suite(tmp_path)
    out = tmp_path / "out"
    report = await run_suite(
        suite_dir,
        lambda: FakeDriver("pass"),  # never creates the flag
        platform="linux",
        trials=1,
        out_dir=out,
        label="fail-case",
    )
    assert report.total_trials == 2
    assert report.successes == 0
    rec = report.tasks["t1"]
    assert rec.trials == 1
    result = json.loads((out / "trials" / "t1" / "1" / "result.json").read_text())
    assert result["success"] is False
    assert "validator" in result["error"]


async def test_run_suite_timeout_passes_if_side_effects_landed(tmp_path):
    """A timed-out run whose validator passes is a success — the agent's
    closing narration isn't part of the task (A17: side effects only)."""
    suite_dir = _make_suite(tmp_path)
    work = tmp_path / "bench-work"

    class StallButSucceedDriver(FakeDriver):
        async def run(self, instruction, trace, *, timeout_s, max_steps):
            import asyncio

            # Side effect lands, then the agent stalls in its closing
            # narration until the timeout fires.
            proc = await asyncio.create_subprocess_exec(
                "bash", "-c", f"mkdir -p {work} && touch {work}/t1.flag"
            )
            await proc.wait()
            trace.event("fake_output")
            return DriverResult(
                final_text="", steps=5, wall_s=float(timeout_s),
                tokens=1, screenshots=1, timed_out=True,
                error=f"timeout({timeout_s}s)",
            )

    out = tmp_path / "out-timeout-pass"
    report = await run_suite(
        suite_dir,
        lambda: StallButSucceedDriver(),
        platform="linux",
        trials=1,
        out_dir=out,
        label="timeout-pass",
        task_filter=__import__("re").compile(r"^t1$"),
    )
    assert report.total_trials == 1
    assert report.successes == 1
    result = json.loads((out / "trials" / "t1" / "1" / "result.json").read_text())
    assert result["success"] is True
    assert result["timed_out"] is True


async def test_run_suite_timeout_fails_without_validator(tmp_path):
    suite_dir = _make_suite(tmp_path)
    # Keep only the 1s-timeout task to bound test duration
    for f in (suite_dir / "tasks").glob("t1.yaml"):
        f.unlink()
    out = tmp_path / "out"
    report = await run_suite(
        suite_dir,
        lambda: FakeDriver("stall"),
        platform="linux",
        trials=1,
        out_dir=out,
        label="timeout-case",
    )
    assert report.total_trials == 1
    assert report.successes == 0


def test_trial_record_defaults_roundtrip():
    rec = TrialRecord(
        task_id="a", trial=1, success=True, error=None,
        steps=1, wall_s=2.0, tokens=3, screenshots=4, timed_out=False,
    )
    assert rec.success is True


def test_shell_error_attributes():
    err = ShellError("boom", returncode=2, stdout="out", stderr="err")
    assert err.returncode == 2 and err.stdout == "out"


# ---------------------------------------------------------------------------
# IME pinning (macOS TIS via pyobjc; faked on this host)
# ---------------------------------------------------------------------------


def test_pin_ascii_input_source_noop_off_macos():
    from tank_backend.benchmarks import ime

    assert ime.pin_ascii_input_source() is False
    assert ime.save_current_input_source() is False
    assert ime.restore_saved_input_source() is False


async def test_launch_app_wrapper_repins_ime(monkeypatch):
    """launch_app is wrapped: success → settle delay → re-pin the IME."""
    from tank_backend.benchmarks import ime
    from tank_backend.benchmarks.driver import RepinImeAfterLaunchTool

    pins: list[bool] = []
    monkeypatch.setattr(ime, "pin_ascii_input_source", lambda: pins.append(True) or True)

    class _FakeLaunchTool(BaseTool):
        def get_info(self):
            return ToolInfo(name="launch_app", description="launch", parameters=[])

        async def execute(self, **kwargs: Any) -> ToolResult:
            return ToolResult(content="launched", display="Launched")

    tool = RepinImeAfterLaunchTool(_FakeLaunchTool())
    result = await tool.execute(app_name="Safari")
    assert isinstance(result, ToolResult)
    assert not result.error
    assert pins == [True]


async def test_launch_app_wrapper_skips_repin_on_error(monkeypatch):
    from tank_backend.benchmarks import ime
    from tank_backend.benchmarks.driver import RepinImeAfterLaunchTool

    pins: list[bool] = []
    monkeypatch.setattr(ime, "pin_ascii_input_source", lambda: pins.append(True) or True)

    class _FailingLaunchTool(BaseTool):
        def get_info(self):
            return ToolInfo(name="launch_app", description="launch", parameters=[])

        async def execute(self, **kwargs: Any) -> ToolResult:
            return ToolResult(content="nope", display="nope", error=True)

    tool = RepinImeAfterLaunchTool(_FailingLaunchTool())
    result = await tool.execute(app_name="Nope")
    assert isinstance(result, ToolResult)
    assert result.error
    assert pins == []


# ---------------------------------------------------------------------------
# Trial wall-time covers the whole trial, not just the agent segment
# ---------------------------------------------------------------------------


async def test_run_suite_records_full_trial_wall_time(tmp_path):
    suite_dir = _make_suite(tmp_path)
    out = tmp_path / "out-time"
    report = await run_suite(
        suite_dir,
        lambda: FakeDriver("pass"),
        platform="linux",
        trials=1,
        out_dir=out,
        label="timing",
    )
    assert report.total_trials == 2
    for task_id in ("t1", "t2"):
        result = json.loads((out / "trials" / task_id / "1" / "result.json").read_text())
        assert result["wall_s"] >= 0.0
