# Tank Backend Core

Main application code for the Tank Voice Assistant backend.

## Overview

This is the core backend application that provides:
- FastAPI WebSocket server for real-time communication
- Speech recognition (ASR) with Faster Whisper or Sherpa-ONNX
- Text-to-Speech (TTS) via pluggable architecture
- LLM integration with tool calling
- Speaker identification (optional)
- Audio streaming and processing

## Directory Structure

```
core/
├── src/tank_backend/
│   ├── api/                # FastAPI routes and WebSocket handlers
│   ├── audio/
│   │   ├── input/         # ASR, VAD, speaker identification
│   │   └── output/        # TTS, audio playback
│   ├── core/              # Brain, Assistant, event system
│   ├── llm/               # LLM client with tool calling
│   ├── tools/             # Tool implementations
│   ├── plugin/            # Plugin loader
│   ├── config/            # Configuration management
│   └── prompts/           # System prompts
├── tests/                 # Test suite (107 tests)
├── .env                   # Configuration file
└── pyproject.toml         # Dependencies
```

## Installation

```bash
# From backend/ directory
cd backend
uv sync

# Or from backend/core/ directory
cd backend/core
uv sync
```

## Running

```bash
# From backend/core/ directory
cd backend/core
uv run tank-backend

# With auto-reload (development)
uv run tank-backend --reload

# With custom host/port
uv run tank-backend --host 0.0.0.0 --port 8000

# Create example config
uv run tank-backend --create-config
```

## Configuration

Create `core/.env` from `core/.env.example`:

```env
# Required
LLM_API_KEY=your_api_key_here

# LLM Configuration
LLM_MODEL=anthropic/claude-3-5-nano
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000

# ASR Configuration
WHISPER_MODEL_SIZE=base
ASR_ENGINE=whisper  # or sherpa
SHERPA_MODEL_DIR=../models/sherpa-onnx-zipformer-en-zh

# Audio Configuration
SAMPLE_RATE=16000
CHUNK_SIZE=1600

# Optional: Web Search
SERPER_API_KEY=your_serper_key

# Optional: Speaker Identification
ENABLE_SPEAKER_ID=false
SPEAKER_MODEL_PATH=../models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx
SPEAKER_DB_PATH=../data/speakers.db
SPEAKER_THRESHOLD=0.6
SPEAKER_DEFAULT_USER=Unknown

# Logging
LOG_LEVEL=INFO
```

## Development

### Running Tests

```bash
cd backend/core

# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/tank_backend --cov-report=html

# Run specific test file
uv run pytest tests/test_brain.py

# Run with verbose output
uv run pytest -v
```

### Code Quality

```bash
# Lint
uv run ruff check src/ tests/

# Auto-fix issues
uv run ruff check --fix src/ tests/

# Format
uv run ruff format src/ tests/
```

### Adding a New Tool

1. Create tool file in `src/tank_backend/tools/`
2. Inherit from `BaseTool`
3. Implement `get_parameters()` and `execute()`
4. Tool is auto-registered by `ToolManager`

Example:

```python
from .base import BaseTool

class MyTool(BaseTool):
    name = "my_tool"
    description = "What this tool does"

    def get_parameters(self) -> dict:
        return {
            "param1": {
                "type": "string",
                "description": "Parameter description"
            }
        }

    def execute(self, param1: str) -> str:
        # Implementation
        return result
```

## Architecture

### Core Components

- **Brain** (`core/brain.py`) - Conversation orchestrator, manages LLM calls and tool execution
- **Assistant** (`core/assistant.py`) - High-level coordinator for audio + brain
- **AudioInput** (`audio/input/`) - ASR, VAD, speaker identification
- **AudioOutput** (`audio/output/`) - TTS, audio playback
- **LLM** (`llm/llm.py`) - LLM client with streaming and tool calling
- **ToolManager** (`tools/manager.py`) - Tool registration and execution
- **PluginLoader** (`plugin/loader.py`) - Dynamic plugin loading

### Data Flow

```
Audio Input → VAD → ASR → Brain → LLM + Tools → TTS → Audio Output
                                    ↓
                            Speaker Identification
```

## Plugin System

The core application loads TTS plugins dynamically from `../plugins/`:

1. Reads `../plugins/plugins.yaml` for configuration
2. Loads plugin module specified in config
3. Calls `create_engine(config)` to instantiate TTS engine
4. Uses `TTSEngine` interface from `tank_contracts.tts`

See `plugin/loader.py` for implementation details.

## Testing

All tests use mocked external dependencies (LLM, audio hardware, ML models):

```bash
# Run all tests (107 tests)
uv run pytest

# Run specific test category
uv run pytest tests/test_brain*.py
uv run pytest tests/test_asr.py
uv run pytest tests/test_voiceprint*.py

# Run with coverage
uv run pytest --cov=src/tank_backend --cov-report=html
open htmlcov/index.html
```

Test coverage: 107 tests, all passing ✅

## Documentation

- [../ARCHITECTURE.md](../ARCHITECTURE.md) - Overall architecture
- [../DEVELOPMENT.md](../DEVELOPMENT.md) - Development guide
- [../CODING_STANDARDS.md](../CODING_STANDARDS.md) - Coding standards
- [../TESTING.md](../TESTING.md) - Testing guidelines

## API

### WebSocket Protocol

**Endpoint**: `ws://localhost:8000/ws/{session_id}`

**Client → Server**:
- Binary frames: Int16 PCM audio (16 kHz)
- JSON frames: `{"type": "input", "content": "..."}`

**Server → Client**:
- Binary frames: Int16 PCM audio (24 kHz)
- JSON frames: signals, transcripts, text, updates

See `api/router.py` for full protocol implementation.

## Deployment

```bash
# Production mode
cd backend/core
uv run uvicorn tank_backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info
```
