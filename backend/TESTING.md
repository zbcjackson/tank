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

Use real implementations for:
- Pure logic (tool calculations, text processing)
- Data structures and event types
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
└── test_api.py                    # FastAPI routes / WebSocket
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
