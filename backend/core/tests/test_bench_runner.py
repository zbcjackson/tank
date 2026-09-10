"""Tests for trace sink, runner orchestration, and driver pieces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
            return DriverResult("done", 3, 1.0, 42, 2, False, None)

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
    assert json.loads((trial_dir / "result.json").read_text())["success"] is True
    # teardown removed the workspace
    assert not work.exists()


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
