# Tank Backend

Backend API server for the Tank Voice Assistant with pluggable architecture.

## Features

- **FastAPI-based WebSocket server** - Real-time bidirectional communication
- **Speech recognition (ASR)** - Pluggable architecture (Sherpa-ONNX default)
- **Pluggable TTS** - Edge TTS (default), extensible via plugin system
- **LLM integration** - OpenAI-compatible API (OpenAI, OpenRouter, Gemini, etc.)
- **Tool calling** - Calculator, weather, time, web search, web scraper
- **Speaker identification** - Optional voiceprint recognition
- **Real-time audio streaming** - Low-latency audio processing

## Architecture

```
backend/
├── core/                    # Main application
│   ├── src/tank_backend/   # Source code
│   ├── tests/              # Tests (123 tests)
│   ├── config.yaml         # LLM profiles + plugin config
│   ├── .env                # Secrets (API keys)
│   └── pyproject.toml      # Dependencies
├── contracts/              # Shared interfaces (StreamingASREngine, TTSEngine ABCs)
├── plugins/                # ASR and TTS plugins
│   ├── asr-sherpa/        # Sherpa-ONNX streaming ASR plugin
│   └── tts-edge/          # Edge TTS plugin
├── data/                   # Runtime data (speakers.db)
├── models/                 # ML models (Whisper, Sherpa, speaker models)
└── scripts/                # Utility scripts
```

## Installation

```bash
cd backend

# Install all workspace dependencies
uv sync

# Install dev dependencies
uv sync --group dev
```

## Usage

```bash
# From backend/core/ directory
cd core
uv run tank-backend

# With custom host/port
uv run tank-backend --host 0.0.0.0 --port 8000

# Create example config
uv run tank-backend --create-config

# With auto-reload (development)
uv run tank-backend --reload
```

## Configuration

Copy `core/.env.example` to `core/.env` and configure:

```env
# Required — referenced by core/config.yaml via ${LLM_API_KEY}
LLM_API_KEY=your_api_key_here

# Optional: Web Search
SERPER_API_KEY=your_serper_key

# LLM profiles, ASR, and TTS are configured in core/config.yaml

# Speaker Identification (optional)
ENABLE_SPEAKER_ID=false
SPEAKER_MODEL_PATH=../models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx
SPEAKER_DB_PATH=../data/speakers.db
```

## LLM Configuration

LLM settings are defined as named profiles in `core/config.yaml`:

```yaml
llm:
  default:
    api_key: ${LLM_API_KEY}          # resolved from .env at load time
    model: anthropic/claude-3-5-nano
    base_url: https://openrouter.ai/api/v1
    temperature: 0.7
    max_tokens: 10000
    extra_headers:
      HTTP-Referer: "http://localhost:3000"
      X-Title: "Tank Voice Assistant"
    stream_options: true
```

Add more profiles (e.g. `fast`, `local`) under the `llm:` key for future agent/subagent use.

## Plugin System

The backend uses a pluggable architecture for ASR and TTS engines. Configure plugins in `core/config.yaml`:

```yaml
asr:
  plugin: asr-sherpa           # Plugin folder name
  config:
    model_dir: ../models/sherpa-onnx-zipformer-en-zh
    num_threads: 4
    sample_rate: 16000

tts:
  plugin: tts-edge             # Plugin folder name
  config:
    voice_en: en-US-JennyNeural
    voice_zh: zh-CN-XiaoxiaoNeural
```

### Adding a New Plugin

1. Create plugin directory: `plugins/<slot>-<name>/`
2. Implement the contract from `tank_contracts` (`StreamingASREngine` or `TTSEngine`)
3. Export `create_engine(config: dict)` function
4. Add to workspace in `backend/pyproject.toml`
5. Configure in `core/config.yaml`

See `plugins/asr-sherpa/` or `plugins/tts-edge/` for reference implementations.

## Development

```bash
# Run tests (from backend/core/)
cd core
uv run pytest

# Run tests with coverage
uv run pytest --cov=src/tank_backend --cov-report=html

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Test all plugins (from backend/)
cd ..
uv run pytest core/tests/ plugins/tts-edge/tests/
```

## API

### WebSocket Endpoint

`ws://localhost:8000/ws/{session_id}`

### Message Protocol

**Client → Server:**
- Audio frames (binary Int16 PCM, 16 kHz)
- Text input: `{"type": "input", "content": "..."}`
- Interrupt: `{"type": "interrupt"}`

**Server → Client:**
- Audio chunks (binary Int16 PCM, 24 kHz)
- Signals: `{"type": "signal", "content": "ready|processing_started|processing_ended"}`
- Transcript: `{"type": "transcript", "content": "...", "is_user": true}`
- Text: `{"type": "text", "content": "...", "msg_id": "...", "metadata": {...}}`
- Updates: `{"type": "update", "metadata": {"update_type": "THOUGHT|TOOL"}}`

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development guide
- [CODING_STANDARDS.md](CODING_STANDARDS.md) - Coding standards
- [TESTING.md](TESTING.md) - Testing guidelines
- [STRUCTURE.md](STRUCTURE.md) - Directory structure
- [PATH_UPDATE_SUMMARY.md](PATH_UPDATE_SUMMARY.md) - Path migration details

## Testing

```bash
cd core
uv run pytest              # 107 tests
uv run pytest -v           # Verbose
uv run pytest --cov        # With coverage
```

All tests pass: ✅ 107/107

## Deployment

```bash
# Production mode
cd core
uv run uvicorn tank_backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4
```
