"""Tests for trace sink, runner orchestration, and driver pieces."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, cast

import pytest

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
    import hashlib

    shot = next(r for r in lines if r["kind"] == "screenshot")
    assert shot["sha256"] == hashlib.sha256((tmp_path / "trial1" / rel).read_bytes()).hexdigest()
    assert sink.screenshot_count == 1
    assert (tmp_path / "trial1" / rel).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# CountingLLM
# ---------------------------------------------------------------------------


async def test_trace_records_actual_sdk_image_hashes_without_image_data(tmp_path: Path) -> None:
    import base64
    import hashlib

    import httpx
    from openai import AsyncOpenAI

    trace = TraceSink(tmp_path)
    source = "data:image/png;base64," + base64.b64encode(b"controlled image").decode()
    trace.save_screenshot(source)
    body = {"id": "test", "object": "chat.completion", "created": 1, "model": "test",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "done"},
                         "finish_reason": "stop"}]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    http = httpx.AsyncClient(transport=transport,
                            event_hooks={"request": [trace.capture_request]})
    async with AsyncOpenAI(api_key="secret-test", base_url="https://offline.invalid/v1",
                           http_client=http) as client:
        await client.chat.completions.create(model="test", messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": source, "detail": "auto"}},
        ]}])
    trace.close()
    raw = (tmp_path / "trace.jsonl").read_text()
    events = [json.loads(line) for line in raw.splitlines()]
    request = next(e for e in events if e["kind"] == "http_request")
    assert request["image_sha256"] == [hashlib.sha256(b"controlled image").hexdigest()]
    assert "secret-test" not in raw and "data:image" not in raw


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
        assert ttft is not None and 0.0 <= ttft <= total
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
    assert ttft is not None and ttft >= 0.0
    assert total >= 0.05  # the cancelled in-flight round


async def test_counting_llm_reports_calls_via_callback():
    seen: list[tuple[int, float | None, float]] = []
    counting = CountingLLM(_FakeInnerLLM())  # type: ignore[arg-type]
    counting.on_call = lambda call, ttft, total: seen.append((call, ttft, total))
    _ = [u async for u in counting.chat_stream()]
    assert [s[0] for s in seen] == [1, 2]
    assert seen[0][1] is not None and seen[0][1] <= seen[0][2]


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
    assert ttft is not None and ttft >= 0.05  # measured at the TEXT, not the instant tool echo
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
    assert result.primitives == 5


async def test_driver_counts_completed_batch_members_and_non_gui_tools(tmp_path):
    from unittest.mock import MagicMock

    from tank_backend.agents.definition import AgentDefinition
    from tank_backend.benchmarks.driver import SubAgentDriver

    class Runner:
        async def run_agent(self, *args, **kwargs):
            yield AgentOutput(AgentOutputType.TOOL_EXECUTING, metadata={
                "name": "computer_batch", "arguments": '{"actions":[{}, {}, {}]}',
            })
            yield AgentOutput(AgentOutputType.TOOL_RESULT, "Batch: 1 of 3 actions (failed at 1)",
                              {"name": "computer_batch", "status": "error"})
            yield AgentOutput(AgentOutputType.TOOL_EXECUTING, metadata={"name": "bash"})
            yield AgentOutput(AgentOutputType.TOOL_RESULT, "ok",
                              {"name": "bash", "status": "success"})

    driver = SubAgentDriver(cast(Any, Runner()), AgentDefinition(name="stub", description="",
                           system_prompt=""), CountingLLM(MagicMock()), MagicMock())
    trace = TraceSink(tmp_path)
    try:
        result = await driver.run("task", trace, timeout_s=10, max_steps=15)
    finally:
        trace.close()
    assert result.steps == 2 and result.primitives == 1
    assert result.non_gui_tools == ("bash",)


async def test_gui_trial_rejects_shell_even_when_validator_passes(tmp_path):
    from tank_backend.benchmarks.runner import _run_trial
    from tank_backend.benchmarks.task import BenchTask

    class Driver:
        async def run(self, instruction, trace, **kwargs):
            assert "GUI" in instruction
            return DriverResult("done", 1, 0.01, 5, 0, False, non_gui_tools=("bash",))

    task = BenchTask("gui", "file", 1, ("linux",), "create file",
                     "printf '%s' '{\"assessment\":{\"business\":true,\"mouse_only\":true}}'",
                     gui_only=True)
    record = await _run_trial(Driver(), task, 1, tmp_path, {"BENCH_ASSETS_URL": ""})
    assert not record.success and record.error == "GUI-only task attempted non-GUI tools: bash"
    assert record.gui_only and record.non_gui_tools == ("bash",)
    assert record.assessment["business"] is False
    assert record.assessment["mouse_only"] is False


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
    assert result.llm_ttft_s is not None and result.llm_ttft_s >= 0.0
    assert result.llm_call_s > 0.0
    assert result.llm_total_s >= result.llm_call_s
    assert len(llm_events) == 2


async def test_max_steps_aborts_on_executed_calls():
    result = await _drive_with_stub(tool_calls=40, max_steps=5)
    assert result.steps == 5  # The 6th call is refused before it starts.
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


@pytest.mark.parametrize(
    "stop_case", ["none", "cleanup", "usage", "budget", "cancelled", "requests", "inputs", "zero"],
)
async def test_serial_batch_shares_durable_spend_and_refuses_replay(
    tmp_path, monkeypatch, stop_case,
):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from tank_backend.benchmarks import runner
    from tank_backend.benchmarks.batch import BatchTrial, run_batch
    from tank_backend.benchmarks.driver import SubAgentDriver
    from tank_backend.benchmarks.frozen_inputs import FrozenFile, FrozenInputs
    from tank_backend.benchmarks.request_budget import RequestLimits
    from tank_backend.benchmarks.spend_ledger import SpendLimit, TokenAllowance

    suite = _make_suite(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("offline fixture")
    import hashlib

    frozen = FrozenInputs(tuple(
        FrozenFile(path, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in (config_path, suite / "suite.yaml", *sorted((suite / "tasks").glob("*.yaml")))
    ))
    order = []
    controls = []

    def create(agent_name, config_path, *, request_limits, spend):
        controls.append(spend)

        class Driver:
            async def run(self, instruction, trace, *, timeout_s, max_steps):
                session = spend.start(trace)
                spend.ledger.reserve(agent_name, TokenAllowance(30, 20, 2, 5))
                saved = json.loads((tmp_path / "out" / "spend.jsonl").read_text().splitlines()[-1])
                assert saved["requests"][agent_name]["status"] == "pending"
                order.append(agent_name)
                if stop_case == "inputs":
                    config_path.write_text("changed after first trial")
                if stop_case == "cancelled":
                    raise asyncio.CancelledError()
                spend.ledger.settle(
                    agent_name, input_tokens=None if stop_case == "usage" else 3, output_tokens=2,
                )
                spend.finish(session)
                return DriverResult(
                    "done", 1, 0.1, 5, 0, False, None,
                    cleanup="unknown" if stop_case == "cleanup" else "confirmed",
                )

        return Driver()

    monkeypatch.setattr(SubAgentDriver, "create", create)
    monkeypatch.setattr(runner, "run_shell", AsyncMock(return_value=SimpleNamespace(stdout="")))
    for name in (
        "save_current_input_source", "pin_ascii_input_source", "restore_saved_input_source",
    ):
        monkeypatch.setattr(runner, name, lambda: None)
    entries = tuple(
        BatchTrial(key, suite, "t1", key, tmp_path / "config.yaml", "linux")
        for key in ("a", "b", "c")
    )
    async def invoke():
        return await run_batch(
            entries, out_dir=tmp_path / "out",
            batch_limit=SpendLimit(54 if stop_case == "budget" else 100, 1000),
            trial_limit=SpendLimit(60, 600), request_limits=RequestLimits(), contracts=(),
            batch_request_limit=0 if stop_case == "zero" else 1 if stop_case == "requests" else 3,
            frozen_inputs=frozen,
        )
    if stop_case in {"cancelled", "inputs"}:
        with pytest.raises(asyncio.CancelledError if stop_case == "cancelled" else ValueError):
            await invoke()
        result = json.loads((tmp_path / "out" / "batch-result.json").read_text())
    else:
        result = await invoke()
    expected_order = (
        ["a", "b", "c"] if stop_case == "none" else [] if stop_case == "zero" else ["a"]
    )
    assert order == expected_order
    assert len({id(c) for c in controls}) == (0 if stop_case == "zero" else 1)
    assert result["completed"] == {
        "none": ["a", "b", "c"], "budget": ["a", "b"], "cancelled": [],
        "cleanup": ["a"], "usage": ["a"],
        "requests": ["a"], "inputs": ["a"], "zero": [],
    }[stop_case]
    assert result["spend"]["batch"]["charged_tokens"] == {
        "none": 15, "budget": 5, "cancelled": 50, "cleanup": 5, "usage": 50,
        "requests": 5, "inputs": 5, "zero": 0,
    }[stop_case]
    assert result["spend"]["stop_reason"] == {
        "none": None, "budget": "batch_tokens", "cancelled": "batch_interrupted",
        "cleanup": "cleanup_unconfirmed", "usage": "unknown_usage",
        "requests": "batch_requests", "inputs": "frozen_inputs", "zero": "batch_requests",
    }[stop_case]
    assert result["spend"]["batch"]["admitted_requests"] == len(order)
    config_path.write_text("offline fixture")
    with pytest.raises(FileExistsError):
        await run_batch(
            entries, out_dir=tmp_path / "out", batch_limit=SpendLimit(100, 1000),
            trial_limit=SpendLimit(60, 600), request_limits=RequestLimits(), contracts=(),
            batch_request_limit=3, frozen_inputs=frozen,
        )
    assert order == expected_order

@pytest.mark.parametrize("invalid", ["empty", "duplicate", "key", "task", "platform"])
async def test_serial_batch_preflight_refuses_invalid_schedule(tmp_path, monkeypatch, invalid):
    from dataclasses import replace
    from unittest.mock import Mock

    from tank_backend.benchmarks.batch import BatchTrial, run_batch
    from tank_backend.benchmarks.driver import SubAgentDriver
    from tank_backend.benchmarks.frozen_inputs import FrozenInputs
    from tank_backend.benchmarks.request_budget import RequestLimits
    from tank_backend.benchmarks.spend_ledger import SpendLimit

    entry = BatchTrial("a", _make_suite(tmp_path), "t1", "a", tmp_path / "config", "linux")
    schedules = {
        "empty": (), "duplicate": (entry, entry), "key": (replace(entry, key="../escape"),),
        "task": (replace(entry, task_id="missing"),),
        "platform": (replace(entry, platform="missing"),),
    }
    create = Mock()
    monkeypatch.setattr(SubAgentDriver, "create", create)
    with pytest.raises(ValueError):
        await run_batch(
            schedules[invalid], out_dir=tmp_path / "out", batch_limit=SpendLimit(100, 1000),
            trial_limit=SpendLimit(60, 600), request_limits=RequestLimits(), contracts=(),
            batch_request_limit=3, frozen_inputs=FrozenInputs(()),
        )
    create.assert_not_called()
    assert not (tmp_path / "out").exists()



@pytest.mark.parametrize(
    "drift", ["config", "suite", "task", "asset", "env", "agent", "added_task", "uncovered",
              "assembly"],
)
async def test_batch_frozen_drift_prevents_trial_side_effects(tmp_path, monkeypatch, drift):
    import hashlib
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from tank_backend.benchmarks import runner
    from tank_backend.benchmarks.batch import BatchTrial, run_batch
    from tank_backend.benchmarks.driver import SubAgentDriver
    from tank_backend.benchmarks.frozen_inputs import FrozenFile, FrozenInputs
    from tank_backend.benchmarks.request_budget import RequestLimits
    from tank_backend.benchmarks.spend_ledger import SpendLimit

    suite = _make_suite(tmp_path)
    (suite / "assets").mkdir()
    (suite / "suite.yaml").write_text(SUITE_YAML + "\nassets_dir: assets\n")
    files = {
        "config": tmp_path / "config.yaml", "suite": suite / "suite.yaml",
        "task": suite / "tasks/t1.yaml", "asset": suite / "assets/index.html",
        "env": tmp_path / ".env", "agent": tmp_path / "agent.md",
    }
    for key in ("config", "asset", "env", "agent"):
        files[key].write_text("offline fixture")
    frozen = FrozenInputs(tuple(
        FrozenFile(path, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in (*files.values(), suite / "tasks/t2.yaml")
        if drift != "uncovered" or path != files["config"]
    ))
    if drift in files:
        with files[drift].open("a") as output:
            output.write("\n# changed\n")
    elif drift == "added_task":
        (suite / "tasks/t3.yaml").write_text(TASK_YAML.format(tid="t3", work=tmp_path / "work"))

    def assemble(*args, **kwargs):
        files["config"].write_text("changed during assembly")
        return Mock()

    create = Mock(side_effect=assemble if drift == "assembly" else None)
    desktop = Mock()
    monkeypatch.setattr(SubAgentDriver, "create", create)
    monkeypatch.setattr(runner, "save_current_input_source", desktop)
    monkeypatch.setattr(runner, "pin_ascii_input_source", desktop)
    monkeypatch.setattr(runner, "restore_saved_input_source", desktop)
    monkeypatch.setattr(runner, "LocalPageServer", Mock())
    monkeypatch.setattr(runner, "run_shell", AsyncMock(return_value=SimpleNamespace(stdout="")))
    with pytest.raises(ValueError, match="Frozen inputs"):
        await run_batch(
            (BatchTrial("a", suite, "t1", "a", files["config"], "linux"),),
            out_dir=tmp_path / "out", batch_limit=SpendLimit(100, 1000),
            trial_limit=SpendLimit(60, 600), request_limits=RequestLimits(), contracts=(),
            batch_request_limit=3, frozen_inputs=frozen,
        )
    assert create.call_count == (1 if drift == "assembly" else 0)
    desktop.assert_not_called()


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


def test_pin_ascii_input_source_noop_off_macos(monkeypatch):
    from tank_backend.benchmarks import ime

    monkeypatch.setattr(ime.sys, "platform", "linux")
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


def test_trace_preserves_webp_mime(tmp_path):
    import base64

    sink = TraceSink(tmp_path)
    path = sink.save_screenshot(
        "data:image/webp;base64," + base64.b64encode(b"RIFF0000WEBP").decode()
    )
    sink.close()
    assert path.endswith(".webp")
    assert (tmp_path / path).read_bytes() == b"RIFF0000WEBP"


async def test_cleanup_failure_stops_suite_before_validator_and_teardown(tmp_path):
    suite = _make_suite(tmp_path)
    calls = []

    class UncleanDriver(FakeDriver):
        async def run(self, instruction, trace, **kwargs):
            calls.append(instruction)
            return DriverResult("", 0, 0, 0, 0, False, "cleanup failed", cleanup="unconfirmed")

    out = tmp_path / "unclean"
    report = await run_suite(
        suite, UncleanDriver, platform="linux", trials=2, out_dir=out, label="unclean"
    )
    assert len(calls) == 1 and report.total_trials == 1
    assert report.metadata["aborted_cleanup"] is True
    entries = [
        json.loads(line) for line in (out / "trials/t1/1/trace.jsonl").read_text().splitlines()
    ]
    assert not any(e["kind"].startswith("validator_") for e in entries)


async def test_trial_capture_does_not_reuse_previous_success(tmp_path):
    import urllib.request

    suite = _make_suite(tmp_path)
    (suite / "assets").mkdir()
    (suite / "assets/index.html").write_text("hi")
    (suite / "suite.yaml").write_text("name: isolated\nassets: assets\nserver_port: 0\n")
    (suite / "tasks/t2.yaml").unlink()
    (suite / "tasks/t1.yaml").write_text("""id: t1
category: browser
difficulty: 1
platforms: [linux]
instruction: ${BENCH_ASSETS_URL}/index.html
validator:
  kind: shell
  command: test -s "$BENCH_CAPTURE"
""")

    class FirstOnlyDriver(FakeDriver):
        def __init__(self):
            self.calls = 0

        async def run(self, instruction, trace, **kwargs):
            self.calls += 1
            if self.calls == 1:
                url = instruction.removesuffix("index.html") + "click?name=first"
                urllib.request.urlopen(url, timeout=5).read()
            return DriverResult("done", 1, 0, 0, 0, False)

    out = tmp_path / "isolated"
    report = await run_suite(
        suite, FirstOnlyDriver, platform="linux", trials=2, out_dir=out, label="isolated"
    )
    assert report.total_trials == 2 and report.successes == 1


async def test_counting_locator_preserves_unknown_and_cancelled_calls():
    import asyncio

    from openai.types.chat import ChatCompletion

    class Inner:
        async def complete_response(self, **kwargs):
            if kwargs.get("cancel"):
                raise asyncio.CancelledError()
            return ChatCompletion(id="missing", object="chat.completion", created=0,
                                  model="test", choices=[])

    counter = CountingLLM(cast(Any, Inner()))
    locator = CountingLLM(cast(Any, Inner()), counter=counter)
    await locator.complete_response()
    try:
        await locator.complete_response(cancel=True)
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Cancellation must propagate")
    assert counter.total_tokens == 0  # known subtotal, paired with unknown_calls
    assert counter.unknown_calls == 2
    assert len(counter.call_stats) == 2
    assert all(ttft is None for ttft, _ in counter.call_stats)
    counter.reset()
    assert counter.unknown_calls == 0 and counter.call_stats == []


async def test_nested_locator_time_is_not_counted_twice(monkeypatch):
    from openai.types.chat import ChatCompletion
    from openai.types.completion_usage import CompletionUsage

    from tank_backend.benchmarks import driver as module

    now = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])

    class Inner:
        async def complete_response(self, **kwargs):
            now[0] += 7
            return ChatCompletion(id="g", object="chat.completion", created=0, model="test",
                                  choices=[], usage=CompletionUsage(prompt_tokens=4,
                                  completion_tokens=6, total_tokens=10))

        async def chat_stream(self, **kwargs):
            now[0] += 2
            yield UpdateType.TEXT, "plan", {}
            yield UpdateType.USAGE, "", {"prompt_tokens": 2, "completion_tokens": 3}
            await locator.complete_response()
            now[0] += 3
            yield UpdateType.USAGE, "", {"prompt_tokens": 2, "completion_tokens": 3}

    counter = CountingLLM(cast(Any, Inner()))
    locator = CountingLLM(cast(Any, Inner()), counter=counter)
    assert len([o async for o in counter.chat_stream()]) == 3
    assert counter.total_tokens == 20
    assert counter.call_stats == [(2, 2), (None, 7), (0, 3)]
    assert sum(elapsed for _, elapsed in counter.call_stats) == 12


@pytest.mark.parametrize("status_code", [200, 429, 502])
async def test_trace_archives_http_body_before_sdk_json_parsing(tmp_path, status_code):
    import httpx
    from openai import AsyncOpenAI, InternalServerError, RateLimitError

    trace = TraceSink(tmp_path)
    raw = b'{"choices": [broken provider JSON'
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(
            status_code, content=raw, headers={"content-type": "application/json"})),
        event_hooks={"request": [trace.capture_request], "response": [trace.capture_response]},
    ) as http:
        client = AsyncOpenAI(api_key="secret", base_url="https://offline.invalid/v1",
                             max_retries=0, http_client=http)
        exception = {200: json.JSONDecodeError, 429: RateLimitError, 502: InternalServerError}
        with pytest.raises(exception[status_code]):
            await client.chat.completions.create(model="locator", messages=[])
    trace.close()
    events = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]
    request = next(e for e in events if e["kind"] == "http_request")
    response = next(e for e in events if e["kind"] == "http_response")
    assert response["request_id"] == request["request_id"]
    assert response["body_state"] == "complete"
    assert response["status_code"] == status_code
    assert (tmp_path / response["file"]).read_bytes() == raw
    assert "secret" not in (tmp_path / "trace.jsonl").read_text()


@pytest.mark.parametrize("ending", ["complete", "read_error", "cancelled", "closed_early"])
async def test_trace_streams_without_prefetch_and_retains_partial_bytes(tmp_path, ending):
    import asyncio
    import hashlib

    import httpx

    seen = []

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            seen.append(1)
            yield b"data: first\n\n"
            if ending == "read_error":
                raise httpx.ReadError("private transport message")
            if ending == "cancelled":
                raise asyncio.CancelledError()
            seen.append(2)
            yield b"data: second\n\n"

    trace = TraceSink(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Chunks())),
        event_hooks={"request": [trace.capture_request], "response": [trace.capture_response]},
    ) as http:
        response = await http.send(http.build_request(
            "POST", "https://offline.invalid", json={"model": "planner", "stream": True}),
            stream=True)
        assert not seen  # Capturing must not wait for future chunks before SDK TTFT.
        chunks = response.aiter_raw()
        assert await anext(chunks) == b"data: first\n\n"
        assert seen == [1]
        if ending == "complete":
            assert b"".join([chunk async for chunk in chunks]) == b"data: second\n\n"
        elif ending != "closed_early":
            exception = httpx.ReadError if ending == "read_error" else asyncio.CancelledError
            with pytest.raises(exception):
                await anext(chunks)
        await response.aclose()
    trace.close()
    events = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]
    records = [e for e in events if e["kind"] == "http_response"]
    assert len(records) == 1
    record = records[0]
    assert record["body_state"] == ending
    raw = b"data: first\n\n" + (b"data: second\n\n" if ending == "complete" else b"")
    assert (tmp_path / record["file"]).read_bytes() == raw
    assert record["bytes"] == len(raw)
    assert record["sha256"] == hashlib.sha256(raw).hexdigest()
    assert "private transport message" not in (tmp_path / "trace.jsonl").read_text()


async def test_trace_close_marks_missing_responses_and_freezes_inflight_archive(tmp_path):
    import httpx

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"first"
            yield b"late"

    trace = TraceSink(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Chunks())),
        event_hooks={"request": [trace.capture_request], "response": [trace.capture_response]},
    ) as http:
        response = await http.send(http.build_request(
            "POST", "https://offline.invalid", json={"model": "planner"}), stream=True)
        chunks = response.aiter_raw()
        assert await anext(chunks) == b"first"
        # A request cancelled before response headers must remain explicitly unknown.
        missing = http.build_request("POST", "https://offline.invalid", json={"model": "locator"})
        await trace.capture_request(missing)
        trace.close()
        before = (tmp_path / "trace.jsonl").read_bytes()
        assert [chunk async for chunk in chunks] == [b"late"]
        await response.aclose()
        # Late headers for the missing request cannot reopen a completed trial.
        await trace.capture_response(httpx.Response(200, content=b"late", request=missing))
        trace.close()
    assert (tmp_path / "trace.jsonl").read_bytes() == before
    records = [json.loads(line) for line in before.splitlines()]
    responses = [r for r in records if r["kind"] == "http_response"]
    assert {r["body_state"] for r in responses} == {"trace_closed", "no_response"}
    captured = next(r for r in responses if r["file"])
    assert (tmp_path / captured["file"]).read_bytes() == b"first"
    assert next(r for r in responses if r["body_state"] == "no_response")["status_code"] is None


@pytest.mark.parametrize("preloaded", [False, True])
async def test_trace_labels_compressed_and_already_decoded_bodies(tmp_path, preloaded):
    import gzip

    import httpx

    payload = b'{"usage": null, "choices": []}'
    compressed = gzip.compress(payload, mtime=0)

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield compressed[:5]
            yield compressed[5:]

    def respond(request):
        headers = {"content-type": "application/json", "content-encoding": "gzip",
                   "set-cookie": "private-header"}
        return (httpx.Response(200, headers=headers, content=compressed) if preloaded else
                httpx.Response(200, headers=headers, stream=Chunks()))

    trace = TraceSink(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), event_hooks={
        "request": [trace.capture_request], "response": [trace.capture_response],
    }) as http:
        response = await http.post("https://offline.invalid", json={"model": "locator"})
        assert response.content == payload
    trace.close()
    raw = (tmp_path / "trace.jsonl").read_text()
    records = [json.loads(line) for line in raw.splitlines()]
    record = next(r for r in records if r["kind"] == "http_response")
    assert record["content_type"] == "application/json"
    assert record["content_encoding"] == "gzip"
    assert record["body_representation"] == ("httpx_decoded" if preloaded else "httpx_raw")
    assert (tmp_path / record["file"]).read_bytes() == (payload if preloaded else compressed)
    assert "private-header" not in raw
