# Backend Testing Guidelines

This document provides testing guidelines for the Tank Backend API Server.

For cross-cutting principles, see [../TESTING.md](../TESTING.md).

## Framework

- **Framework**: `pytest` with `pytest-asyncio`
- **Location**: `tests/`
- **Config**: `pyproject.toml` — `asyncio_mode = "auto"`

## Testing Commands

```bash
uv run pytest                                    # All tests
uv run pytest -v                                 # Verbose
uv run pytest tests/test_brain.py               # Specific file
uv run pytest tests/test_brain.py::test_name    # Specific test
uv run pytest --cov=src/tank_backend            # With coverage
uv run pytest --cov=src/tank_backend --cov-report=html
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
