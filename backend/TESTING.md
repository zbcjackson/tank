# Backend Testing Guidelines

This document provides testing guidelines for the Tank Backend API Server.

For cross-cutting principles, see [../TESTING.md](../TESTING.md).

## Framework

- **Framework**: `pytest` with `pytest-asyncio`
- **Location**: `core/tests/`, `contracts/*/tests/`, `plugins/*/tests/`
- **Config**: workspace 根目录 `pyproject.toml` — `asyncio_mode = "auto"`

从 `backend/` 执行 `uv run pytest` 会运行整个 workspace 的测试。统一配置使用
`--import-mode=importlib`，并将 `core/tests` 加入测试 helper 的导入路径。
插件测试目录不添加 `__init__.py`：同名 `tests` 包会让不同插件的测试模块冲突，
即使 importlib 模式也可能重复收集另一个插件的测试。

## Testing Commands

```bash
uv run pytest                                    # All tests
uv run pytest -v                                 # Verbose
uv run pytest core/tests/test_brain.py          # Specific file
uv run pytest core/tests/test_brain.py::test_name # Specific test
uv run pytest --cov=core/src/tank_backend       # With coverage
uv run pytest --cov=core/src/tank_backend --cov-report=html
```

## TDD Workflow

1. Write a failing test describing the desired behavior
2. Implement the minimal code to make it pass
3. Refactor while keeping tests green
4. Run the full suite before committing

## What to Mock

Always mock:
- **LLM API** (`httpx.AsyncClient`, `openai.AsyncOpenAI`)
- **Audio hardware** (`sounddevice.InputStream`, `sounddevice.play`)
- **ML model loading** (Whisper, Silero VAD)
- **External APIs** (web search, weather)
- **System time** — use fixed timestamps
- **Langfuse** — mock or disable via env vars
- **Docker sandbox** — mock subprocess calls for code execution tools

Use real implementations for:
- Pure logic (tool calculations, text processing, echo detection)
- Data structures and event types (Bus, BusMessage, AgentState)
- Pipeline primitives (ThreadedQueue, FlowReturn)
- Approval policy logic (no I/O)
- Fast, deterministic components (< 100ms)

## Key Patterns

### Async Tests

All async tests run automatically with `asyncio_mode = "auto"`:

```python
async def test_brain_processes_input():
    brain = Brain(config=mock_config)
    result = await brain.process_input("hello")
    assert result is not None
```

### Mocking LLM

```python
from unittest.mock import AsyncMock, patch

async def test_llm_call():
    with patch("tank_backend.llm.llm.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = make_completion("Hello!")

        llm = LLM(config)
        result = await llm.complete([{"role": "user", "content": "hi"}])
        assert result == "Hello!"
```

### Mocking Audio Hardware

```python
from unittest.mock import patch, MagicMock

def test_mic_capture():
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__ = MagicMock(return_value=mock_stream.return_value)
        mock_stream.return_value.__exit__ = MagicMock(return_value=False)
        # Test mic component without real hardware
```

### Mocking Whisper

```python
with patch("tank_backend.audio.input.asr_whisper.WhisperModel") as mock_model_cls:
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (
        [MagicMock(text="hello world")],
        MagicMock(language="en", language_probability=0.99)
    )
    mock_model_cls.return_value = mock_model
    asr = WhisperASR(config)
    text, lang, conf = asr.transcribe(audio_data, 16000)
    assert text == "hello world"
```

### Generating Audio Test Data

```python
import numpy as np

def make_audio_frame(sample_rate=16000, duration_ms=20, frequency=440):
    n = int(sample_rate * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n)
    return (0.3 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)

def make_silence(sample_rate=16000, duration_ms=20):
    return np.zeros(int(sample_rate * duration_ms / 1000), dtype=np.float32)
```

### Fixed Timestamps

```python
BASE_TIME = 1000.0  # Fixed, not time.time()

frames = [
    AudioFrame(data=make_audio_frame(), timestamp_s=BASE_TIME + i * 0.02)
    for i in range(10)
]
```

### Module Constant for Patch Targets

```python
MODULE = "tank_backend.audio.output.tts_engine_edge"

with patch(f"{MODULE}.shutil.which", return_value=None), \
     patch(f"{MODULE}.edge_tts") as mock_et:
    ...
```

### Shared Mock Helpers

```python
def make_llm_completion(content: str):
    """Build a minimal mock ChatCompletion."""
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = None
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage.prompt_tokens = 10
    completion.usage.completion_tokens = 5
    return completion
```

### Async Stream Collection

```python
async def collect_chunks(engine, text, **kwargs):
    chunks = []
    async for chunk in engine.generate_stream(text, **kwargs):
        chunks.append(chunk)
    return chunks
```

## Test Organization

```
tests/
├── conftest.py                    # Shared fixtures (config, audio helpers)
├── test_brain.py                  # Brain / conversation logic
├── test_llm.py                    # LLM client
├── test_tools.py                  # Tool execution
├── test_asr.py                    # ASR components
├── test_tts_engine_edge.py        # TTS engine
├── test_segmenter.py              # VAD + segmenter
├── test_api.py                    # FastAPI routes / WebSocket
├── test_pipeline.py               # Pipeline primitives (Bus, Queue, FlowReturn)
├── test_processors.py             # Individual processor tests
├── test_agents.py                 # Agent orchestration (AgentGraph)
├── test_approval.py               # Approval system (policy, manager, API)
├── test_echo_guard.py             # Echo guard (Layer 2 text detection)
├── test_checkpointer.py           # Conversation persistence
└── test_observers.py              # Observer tests (latency, health, alerting)
```

## Testing Pipeline Components

### Testing Processors

Test `process()` in isolation with mock inputs — no real audio or LLM:

```python
from tank_backend.pipeline.processor import FlowReturn

async def test_echo_guard_detects_self_echo():
    guard = EchoGuard(config={"similarity_threshold": 0.6, "window_seconds": 10.0})
    guard.record_tts("The weather today is sunny and warm")

    # Simulate ASR transcript that echoes TTS
    result = guard.is_echo("the weather today is sunny and warm")
    assert result is True

async def test_echo_guard_passes_new_speech():
    guard = EchoGuard(config={"similarity_threshold": 0.6, "window_seconds": 10.0})
    guard.record_tts("The weather today is sunny and warm")

    result = guard.is_echo("what time is it")
    assert result is False
```

### Testing the Bus

```python
from tank_backend.pipeline.bus import Bus, BusMessage

def test_bus_delivers_to_subscribers():
    bus = Bus()
    received = []
    bus.subscribe("metric", lambda msg: received.append(msg))

    bus.post(BusMessage(type="metric", source="test", payload={"value": 42}, timestamp=1000.0))
    bus.poll()

    assert len(received) == 1
    assert received[0].payload["value"] == 42
```

### Testing ThreadedQueue

```python
from tank_backend.pipeline.queue import ThreadedQueue

def test_queue_backpressure():
    q = ThreadedQueue(name="test", maxsize=2)
    assert q.push("a") == FlowReturn.OK
    assert q.push("b") == FlowReturn.OK
    # Queue is full — next push should indicate backpressure
```

## Testing Agents

### Testing Agents

Mock the LLM and tool manager — test the agent's streaming output:

```python
from unittest.mock import AsyncMock, MagicMock
from tank_backend.agents.base import AgentState, AgentOutputType

async def test_chat_agent_streams_tokens():
    mock_llm = AsyncMock()
    mock_tool_manager = MagicMock()
    agent = ChatAgent(llm=mock_llm, tool_manager=mock_tool_manager)

    state = AgentState(messages=[{"role": "user", "content": "hi"}])
    outputs = [o async for o in agent.run(state, mock_llm)]

    assert any(o.type == AgentOutputType.TOKEN for o in outputs)
```

### Testing Approval System

```python
from tank_backend.agents.approval import ApprovalPolicy, ApprovalManager

def test_approval_policy():
    policy = ApprovalPolicy(
        always_approve={"weather", "time"},
        require_approval={"run_command"},
        require_approval_first_time={"web_search"},
    )
    assert not policy.needs_approval("weather")
    assert policy.needs_approval("run_command")
    assert policy.needs_approval("web_search")

async def test_approval_manager_resolves():
    manager = ApprovalManager()
    request = ApprovalRequest(tool_name="run_command", tool_args={}, description="Run code")

    # Simulate approval in background
    import asyncio
    async def approve_later():
        await asyncio.sleep(0.01)
        pending = manager.get_pending()
        manager.resolve(pending[0].id, approved=True)

    asyncio.create_task(approve_later())
    result = await manager.request_approval(request)
    assert result.approved is True
```

## Testing Observability

### Testing Observers

```python
from tank_backend.pipeline.bus import Bus, BusMessage
from tank_backend.pipeline.observers.latency import LatencyObserver

def test_latency_observer_tracks_metrics():
    bus = Bus()
    observer = LatencyObserver(bus)

    # Simulate processor start/end
    observer.on_processor_start("asr", 1000.0)
    observer.on_processor_end("asr", 1000.050, 50.0)

    bus.poll()
    # Verify metric was posted to bus
```

### Testing Health Monitoring

```python
from tank_backend.pipeline.health import HealthAggregator

async def test_health_aggregator():
    aggregator = HealthAggregator()
    aggregator.register("llm", lambda: {"status": "healthy"})
    aggregator.register("asr", lambda: {"status": "degraded", "detail": "high latency"})

    result = await aggregator.check_all()
    assert result["status"] == "degraded"  # worst of all components
```

## Testing FastAPI Routes

```python
from fastapi.testclient import TestClient
from tank_backend.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

async def test_websocket():
    with client.websocket_connect("/ws/test-session") as ws:
        ws.send_json({"type": "text", "content": "hello"})
        data = ws.receive_json()
        assert data["type"] in ("signal", "text")
```

## Performance Targets

- Unit tests: < 1 second each
- Integration tests: < 2 seconds each
- Full suite: < 30 seconds total

## Quality Checklist

- [ ] LLM, audio hardware, and ML models are mocked
- [ ] Tests verify observable behavior, not internals
- [ ] No access to private methods or internal attributes
- [ ] Fixed timestamps used instead of `time.time()`
- [ ] Audio data generated programmatically (numpy)
- [ ] Async tests run without real I/O
- [ ] Each test completes in < 2 seconds
- [ ] Shared helpers used to avoid duplication (MODULE constant, `make_*`, `collect_*`)
- [ ] Pipeline processors tested in isolation (mock upstream/downstream)
- [ ] Agent tests mock LLM and verify streaming output types
- [ ] Approval tests verify policy logic and async resolve flow
- [ ] Observer tests verify Bus message delivery
- [ ] Tool tests verify `ToolResult` return types and content completeness

## Tool Testing

### Unit Tests

Every tool must verify:
1. `execute()` returns `ToolResult` (not dict) on success and error paths
2. `ToolResult.content` contains all data the LLM needs (parse with `json.loads`)
3. `ToolResult.display` is a concise human-readable summary
4. `ToolResult.error` is `True` for error paths, `False` for success

```python
async def test_my_tool_success():
    tool = MyTool()
    result = await tool.execute(param="value")

    assert isinstance(result, ToolResult)
    assert not result.error

    data = json.loads(result.content)
    assert "expected_key" in data
    assert data["expected_key"] == "expected_value"

    assert len(result.display) < 300  # Concise summary
```

### Integration Tests

Test that tool results flow correctly to the LLM via `_tool_result_to_str()`:

```python
from tank_backend.llm.llm import _tool_result_to_str

def test_tool_result_extraction():
    result = ToolResult(
        content='{"key": "value"}',
        display="Summary",
    )
    llm_content, ui_display = _tool_result_to_str(result)
    assert llm_content == '{"key": "value"}'  # LLM sees full data
    assert ui_display == "Summary"             # UI sees summary
```

### Mocking Patterns

```python
# Mock a tool that returns ToolResult
tm = MagicMock()
tm.execute_openai_tool_call = AsyncMock(
    return_value=ToolResult(
        content='{"result": 42}',
        display="Result: 42",
    )
)

# Mock a skill tool that returns str
tm.execute_openai_tool_call = AsyncMock(
    return_value="SKILL ACTIVATED: test\nInstructions here"
)
```

## Integration Testing Requirements

Every feature must have integration tests that cover the **seams between components** — not just individual units in isolation. Unit tests with mocks can pass while the real system is broken at the integration points.

### What Integration Tests Must Cover

For each feature, test the full flow across component boundaries:

1. **Input → Processing → Output** — verify the end-to-end path produces the expected result
2. **Error paths** — verify failures are recorded/reported correctly across boundaries
3. **State synchronization** — verify that state changes in one component are visible to others

### Policy & Approval System (`test_policy_integration.py`)

| Test | What it verifies |
|------|-----------------|
| Gate + file tool REQUIRE_APPROVAL | `ToolApprovalPolicy` evaluates file tools, gate parks the call |
| Gate + file tool DENY | Gate hard-blocks, tool never executes |
| Gate + network tool | Same three-way flow for web_fetch/web_search |
| AlwaysApproveResolver + file tool | Autonomous `always_approve` executes file writes |
| AlwaysDenyResolver + file tool | Autonomous `always_deny` blocks file writes |
| InteractiveResolver parks all tools | Interactive mode parks command, file, and network tools |
| DENY ignores resolver | Hard blocks can't be overridden by any resolver |
| Policy routing per tool type | Command → CommandSecurityPolicy, file → FileAccessPolicy, etc. |

### Cron Job System (`test_jobs_integration.py`)

| Test | What it verifies |
|------|-----------------|
| Trigger → execute → deliver → history | Full end-to-end: output file created, run history recorded |
| Trigger via scheduler | `scheduler.trigger_job()` runs the full flow |
| Timeout enforcement | `asyncio.TimeoutError` recorded as status="timeout" |
| Failure recording | Exceptions recorded as status="failed" with error message |
| Seed sync + APScheduler | Seed file creates job AND registers APScheduler schedule |
| Seed removal + APScheduler | Removing from seed deletes from DB AND APScheduler |
| manage_jobs create → sync | Tool creates job AND syncs to APScheduler |
| manage_jobs delete → sync | Tool deletes job AND removes APScheduler schedule |
| manage_jobs disable → sync | Tool disables job AND removes APScheduler schedule |
| Approval mode → resolver | `always_deny` builds AlwaysDenyResolver, `always_approve` builds AlwaysApproveResolver |

### Writing New Integration Tests

When adding a new feature, ask these questions to identify missing integration tests:

1. **Does component A's output feed into component B?** → Test A→B together
2. **Does a state change in A need to be visible in B?** → Test the sync
3. **Does the feature have an approval/policy gate?** → Test all three verdicts (ALLOW, REQUIRE_APPROVAL, DENY)
4. **Does the feature have error/timeout paths?** → Test that errors are recorded across boundaries
5. **Can the feature be triggered from multiple entry points?** → Test each entry point (REST API, voice tool, seed file)

### Anti-patterns to Avoid

- **Mocking the boundary you're testing** — if you mock `_run_agent` to test timeout, you bypass the `asyncio.timeout()` inside it. Mock at a lower level or raise the expected exception directly.
- **Testing only the happy path** — DENY and REQUIRE_APPROVAL paths are where bugs hide.
- **Testing components in isolation when the bug is at the seam** — the `ApprovalCallback` was `None` for years because no integration test verified file tools actually got a working callback.

## Plugin subagents and N2 SDK

`core/tests/test_subagent.py` exercises the generic contract and the real
AgentTool → Supervisor → Runner seam, including missing grants, scoped approval,
terminal errors, cleanup quarantine and lock-wait timeouts. It needs no yutori
import. `plugins/agent-n2-sdk/tests` uses yutori 0.9.29 with fake computer/completions
for callback events, retries, usage, cancellation and cleanup; no paid API or
host input. Install all workspace packages before running all plugin tests:
`uv sync --all-packages --all-groups`, then `uv run --no-sync pytest`.

The existing chat.feature includes isolated-process SDK dispatch scenarios using
`test/support/n2-sdk-dispatch.py`. They verify approvals, persisted status, stop,
activity frame conversion and completion/failure notifications. Existing live
client scenarios cover transport separately. Fake tests do not establish physical
macOS input cleanup, Linux support or benchmark success; these remain real-machine
acceptance items in the active SDK plan.

Benchmark regression tests verify per-trial capture/token isolation, rejection of
stale tabs/late requests, correct PNG/WebP MIME, tool-call step boundaries,
smoke exclusion and suite abortion after unconfirmed cleanup.

## macOS coordinate chain

`core/tests/test_computer_use_macos.py` covers backing-to-logical sizing, crop
and upscale pixels, image serialization through the actual OpenAI SDK HTTP
boundary, fragmented SSE arguments and final Quartz event coordinates. Only OS
and HTTP boundaries are mocked. Recorded synthetic model replies are replayed
without network calls; malformed replies must not inject mouse events.

For opt-in real desktop calibration, run from backend:
`uv run --no-sync python scripts/calibrate_macos_coordinates.py --output /tmp/tank-calibration-new`.
Use a fresh output directory, grant Screen Recording and Accessibility to the
host application, and leave the mouse idle. It opens its own target window,
checks visible target pixels before clicking, records down/up events and cursor
positions, and restores the cursor. Full desktop PNG stays local; do not upload
it as part of synthetic-only model tests. Only the main display is supported.

See [coordinate investigation](../docs/research/macos-coordinate-chain.md) for
conversion contracts, synthetic-model evidence and limits of the acceptance.

The macOS calc-open validator has unit and real-shell integration tests in
`core/tests/test_calc_validator.py`; only osascript is substituted in the shell
test. `test_bench_task.py` checks platform-specific strict/GUI-only scoring.
Real verification used the actual benchmark trial runner with deterministic
Calculator keyboard input: 5×7 fails, 7×8 passes, and setup clears prior results.
The result checker needs macOS Accessibility and permission for System Events.

`core/tests/test_grounding_probe.py` verifies the coordinate-hypothesis scorer.
`scripts/probe_grounding_contract.py` is an opt-in paid model diagnostic using
only generated calculator images; it never captures the desktop or executes
model actions. `--point-only` isolates tool schema from the original bbox schema.
Use fresh output directories; compare repeated images and positions rather than
inferring one global correction factor from a single response.

The same probe accepts `--model` (request-only model override on the configured
provider; does not edit production configuration), `--prompt-style agent|minimal|formula|bbox`,
`--thinking default|on|off`, `--high-resolution`, `--plain-json`, and
`--case-set all|hard|holdout`. `bbox` requests native `bbox_2d` JSON without
tools; it is a diagnostic, not a production coordinate protocol. The hard set
contains four existing images targeting 7; the holdout set uses new 1600×900
and 900×1600 images, two new placements, and AC/7. Responses are saved as raw
SSE and buffered before SDK parsing, so these runs are not latency benchmarks.
The HTTP hook verifies every transmitted PNG hash. Tests cover actual SDK
serialization of provider parameters and images, JSON/fenced JSON decoding,
and replay a captured malformed provider response through SDK, LLM and tool
rejection. Format decoding never repairs invalid JSON or executes model actions.

`scripts/probe_grounding_matrix.py` extends this with Qwen, DeepSeek and GPT via
OpenRouter, request-only provider selection, integer point/pixel/bbox protocols,
nullable-schema controls, strict flags, crop/resize/history/marker/shuffle and
agent/tool-context controls. It uses the actual OpenAI SDK without Tank's agent
loop; `full-tools` includes production desktop tool schemas but executes none.
Every SDK HTTP request is checked against the bound PNG hashes and their order.
Native DashScope replay has a separate, tested payload adapter. Its artifact
script checks payload image bytes before HTTP serialization, not via that SDK hook.

The matrix defaults to integer fields. `found=false` requires all zeros in this
explicit protocol; nullable controls require all nulls. No string coercion,
coordinate-unit guessing, duplicate JSON keys or inverted boxes are accepted.
Host code computes box centers and reverses crop/resize transforms; hit scores
use the rendered rounded-button mask separately from center distance. Unit tests
cover these contracts and real SDK serialization; paid calls remain opt-in.
`--max-tokens` sets the probe output budget (default 4000; reasoning may consume
this budget). `--thinking on|off` overrides the thinking setting for every variant;
without it, only the `no-thinking` variant disables thinking. These are diagnostic
request overrides, not production profile changes. DeepSeek sends the SDK
`extra_body={"thinking": {"type": "disabled"}}` for `--thinking off`.
CLI-to-HTTP tests verify independent budget/thinking controls, default behavior,
unchanged images and coordinate schemas, and retention of token-limit failures.
See the [protocol isolation results](../docs/research/macos-coordinate-chain.md#2026-09-19-跨提供方与严格协议隔离)
for model scores and the limits of synthetic, static-screen acceptance.


`core/tests/test_subagent.py` also sends the built-in desktop agent through the
real Runner → LLMAgent → OpenAI SDK with a fake HTTP transport. It checks the
final system prompt for self-delegation conflicts and checks clarification
instructions against the actual serialized tool schemas (missing, available,
allowlisted, excluded and named-toolset cases). `test_prompt_assembler.py`
retains main-agent delegation while shared security stays available to both.
These tests make no model requests or desktop actions and do not measure model
success rates.


M1 input/evidence regressions cover explicit macOS `type_text(mode="paste")`,
invalid-mode zero input, default IME compatibility and paste → Enter batch
semantics. Calculator tests run the actual shell validator through the trial
runner and preserve strict failures alongside separate business/mouse evidence.
They reject answer-only insertion, old-trial evidence and unfinished input.
Trace tests use the real SDK with fake HTTP to verify image hashes without
storing credentials or image bytes in request events. Additional regressions
cover ASCII text under a non-ASCII input source, native input-source reference
release and shifted physical keys (`shift+8`). The
[M1 acceptance report](benchmarks/computer_use/reports/20260920-m1-acceptance/README.md)
records real TextEdit/Calculator input, verified cleanup, local screenshot review
and synthetic prompt-only A/B. Generic pixel grading remains `unknown`: local
OCR misreads some isolated digits, and independent visual review is kept separate.
Unit tests and saved-image SDK replay do not establish real-model closed-loop
accuracy or live screenshot freshness.


M2 opt-in frame-coordinate tests extend `test_computer_use_common.py` and
`test_computer_use_macos.py`: immutable PNG identity, actual crop/window mapping,
strict image-point rejection, display/session/window freshness, batch frame
binding, and cancellation during validation. Real SDK HTTP tests compare the
transmitted PNG hash with the observation and exercise fragmented image-coordinate
responses through ToolManager to Quartz. Legacy interfaces remain covered.
`calibrate_macos_coordinates.py --coordinate-space image --window --output <new-dir>`
uses its own window and checks nine real click targets, release events and cursor
restoration. The [M2 report](benchmarks/computer_use/reports/20260920-m2-observation/README.md)
records 9/9 hits with zero per-axis error and the initial rejected full-screen
attempt. Scene checks are conservative and do not prove dynamic-UI reliability,
model accuracy, physical drag/scroll or the M6 stop/cleanup matrix.


M3 shared-adapter regressions extend `core/tests/test_grounding_probe.py` with
actual LLMProfile → LLM → SDK HTTP serialization for Qwen, DeepSeek and OpenRouter,
image/hash/size binding, image-to-M2 mapping, distinct explicit outcomes, invalid
configuration, and refusal/truncation rejection. Ten archived M3 responses replay
through the production adapter with request/image checks (only the documented
unique-match prompt delta is allowed); malformed
arrays remain failures and legal misses retain their scores. Floating distance
comparisons allow only arithmetic roundoff. Cancellation propagates and a 429
causes exactly one HTTP request (wrapper and SDK retries both disabled).

The matrix now rejects `finish_reason=length` even with syntactically complete
tool arguments, retaining raw arguments and usage. This is tested via real SDK
HTTP, not a mock completion. Existing LLM retry/profile/trace tests cover the
unchanged `complete()` text API. M4 planner dispatch and shared accounting are covered by the split-mode tests
below; physical cancellation remains M6 acceptance work. These tests use no paid
model calls or desktop actions.

`run_grounding_holdout.py` consumes a frozen request schedule with the production
adapter, verifies image/source/body hashes, preserves raw HTTP before parsing,
and never reads scoring truth. It defaults to a fake transport; `--live` requires
a reviewed price manifest. `test_grounding_probe.py` covers visible-mask rounding
and occlusion, invalid-response refusal scoring, request/token reservations,
429/no retry, timeout, cancellation, missing usage and retained truncations.
Unknown usage retains the full request reservation and stops the batch. Real
model quality is scored separately after execution, never inferred from mocks.


The legacy found prompt now requires exactly one unambiguous match; duplicates
must abstain. SDK tests cover the transmitted rule and point/pixel/bbox integer
and nullable sentinels. Historical manifests remain immutable: old-source
holdout freezes fail validation after the prompt change. HTTP failure tests use
temporary current-contract freezes rather than rewriting historical evidence.


M4 `core/tests/test_computer_locate.py` exercises actual Runner → LLMAgent →
ToolManager → GroundingAdapter → SDK, replacing only HTTP and macOS boundaries.
It verifies current-image bytes, absence of planner history in locator requests,
same-model and separate-profile selection, reference-only actions, single shared
accounting, refusal/invalid/truncated responses, unknown usage, scene/frame/window
changes, retry/backend-switch limits, drag references and batch failure feedback.
Cancellation/deadline tests interrupt HTTP and stop input at frame validation.
The existing `chat.feature` runs selected dispatch/stop contracts through Cucumber;
these isolated scenarios reuse pytest and do not claim browser/WS dispatch coverage.
No paid model call or physical desktop event occurs in these tests.

On this host, full pytest needs the installed Opus library search path:
`uv run --no-sync env DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/opus/1.6.1/lib pytest`.
This is an environment setting, not an audio-code workaround.


M5 benchmark split-mode regressions extend `test_computer_locate.py` through
`SubAgentDriver.create` → real Runner/SDK with fake HTTP/macOS. Same-model and
separate-profile cases check four token budgets, current image bytes, initial
and feedback screenshot archives, actual request count, GUI classification and
single accounting of planner plus locator usage. `test_bench_runner.py` also
checks missing/cancelled locator usage and excludes nested locator time from
planner intervals. These are measurement-contract tests, not paid A/B/C/D
results. Integrated B and batch accounting now have the additional coverage below.


M5 integrated cases in `test_computer_locate.py` exercise actual streamed SDK
requests through Runner and the benchmark driver: four protocols × host restoration
on/off × single/batch × complete/truncated/duplicate-key replies. Successful cases
use exactly one model and archive initial/feedback images; truncated/duplicate
arguments stop before input while retaining usage. Missing/ambiguous/invalid/stale
or changed-frame batches stop before typing. Schema pairing verifies that host
restoration changes no tool schema, adapted locations share GroundingAdapter, and
batch schemas preserve the tool allowlist. Config tests preserve split defaults
and reject unsupported integrated locator/fallback/strict settings. These fake
HTTP/OS checks do not establish real model effectiveness or a frozen A/B/C/D run.

M5 raw-response tests in `test_bench_runner.py` run the real HTTPX/OpenAI SDK
boundaries against fake transports. They retain malformed JSON and 429/502 bodies
before SDK errors, verify incremental streaming without prefetch, preserve partial
read-error/cancelled/early-close bodies, label compressed versus already-decoded
bytes, and finalize missing/in-flight responses when a trace closes. Late bytes
and headers cannot alter a closed trace. `test_computer_locate.py` also verifies
request/response pairing through `SubAgentDriver.create` for shared and independent
locator profiles. These checks do not establish semantic failure attribution,
physical cleanup, live request budgets or model effectiveness.

Split-locator outcome tests add structured rejection coverage for refusals, wrong
tools, zero/multiple choices and duplicate JSON fields, plus SDK connection-failure
accounting and context reset. Existing tests now check stages for stale/changed
frames, invalid output, truncation, unknown usage, budget stops and cancellation.
The real benchmark create/Runner/SDK path joins outcome, usage and HTTP attempt IDs
for both shared and independent locator profiles, and leaves planner requests
unassociated. Reported model statuses and parsed coordinates remain unscored;
these offline tests do not prove target-selection or coordinate correctness.

M5 request admission tests add 13 real create/Runner/SDK cases with fake HTTP/OS
for legacy, integrated and independent-locator split modes. They cover planner,
locator and shared limits, zero allowance, 429/503 failures without retries, exact
admitted request/trace counts, fresh allowances on driver reuse and late requests
from closed trial contexts. Refused requests cannot supply new actions, and cleanup
remains unknown. Seven `test_request_budget.py` cases cover counter validation,
latched/closed budgets and rejection of unsupported engine/extension transports.
`test_llm_retry.py` adds a real SDK 429 regression proving one HTTP attempt with
both retry layers disabled. These tests do not establish token/cost reservations,
batch-wide enforcement, real model effectiveness or physical desktop cleanup.

`core/tests/test_spend_ledger.py` includes 61 reservation/persistence cases without
model HTTP or desktop operations. They cover trial/batch token and cost limits, exact boundaries,
known-usage release, unknown/partial/invalid-usage retention, observed bound
violations, duplicate settlement/IDs, serial lifecycle, unfinished-request closure,
cross-trial spending, integer monetary arithmetic and detached JSON snapshots.
Persistence cases use real files and process exit, inject fsync failures, verify
pending reservations survive exit, and refuse reopening an existing journal.
These test the offline ledger API only; HTTP integration has the additional
coverage below. Actual provider bounds/prices and physical stopping remain unverified.

`test_spend_http.py` includes 58 cases through real LLM/SDK/HTTP hooks or request
contract validation. They check pre-transport reservation/refusal, fragmented SSE
without prefetch, settlement before tool execution, raw usage validation despite
SDK coercion, missing/inconsistent/over-bound usage, cancellation and read failures.
Contract tests reject mismatched parameters, malformed JSON and missing evidence.
The 13 create/Runner/SDK request-gate cases in `test_computer_locate.py` also run
with spend control enabled, covering legacy/integrated/split and independent
locator clients, 429/503 without retry, shared accounting and driver reuse.
Model HTTP and desktop boundaries are fake. Synthetic ceilings/prices exercise the gate;
they do not establish usable input bounds for the proposed live M5 batch.

The 22 serial-batch cases in `test_bench_runner.py` use the real suite orchestration
with fake drivers/shell/IME boundaries. They verify explicit order, one shared
durable ledger, no replay of an existing directory, cancellation accounting,
budget/unknown-usage/unconfirmed-cleanup stops and invalid schedule preflight.
The HTTP cases also cover durable reservation visibility at transport entry,
sync failure causing zero HTTP sends/tool actions, and driver context cleanup
when final journal sync fails. No test establishes automatic recovery, a global
desktop lock or machine power-loss durability.

Batch count cases verify persisted admission across trial boundaries, no refund
for zero-token settlement, invalid limits, zero HTTP sends at a zero ceiling,
and no next driver after exhaustion. Existing separate-locator cases also assert
shared batch counts for both SDK clients, including HTTP failures and driver reuse.
Eight `test_comparison_freeze.py` cases check file hashes, inventory changes,
required coverage and invalid pins. Batch regressions reject changed config,
suite/task, assets, `.env`, explicitly pinned agent files, added tasks, missing
config pins and mutations during driver construction or between trials.
The initial construction-drift red test omitted IME isolation and reached a host
API (connection errors); all IME/page-server/shell boundaries were then isolated
before the passing run. This is not physical cleanup or desktop-effect evidence.


### M5 resolved comparison configuration

`test_comparison_freeze.py` adds 31 cases: seven production-parser round trips,
16 resolved-drift/credential cases, refusal before client/tool construction, and
seven generated-config → real driver/Runner/SDK checks. SDK HTTP transport is
mocked; screenshot, click and Quartz boundaries explicitly reject host access.
The SDK checks compare model, tool schemas and generation settings with the
exported first request. Existing export tests additionally verify deterministic
runtime files and absence of credentials. These are offline contract tests, not
physical desktop cleanup or live model acceptance.
