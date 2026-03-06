# Tank Backend

Backend API server for the Tank Voice Assistant with pluggable architecture.

## Features

- **FastAPI-based WebSocket server** - Real-time bidirectional communication
- **Speech recognition (ASR)** - Faster Whisper or Sherpa-ONNX
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
│   ├── tests/              # Tests (107 tests)
│   ├── .env                # Configuration
│   └── pyproject.toml      # Dependencies
├── contracts/              # Shared interfaces (TTSEngine ABC)
├── plugins/                # TTS plugins
│   ├── plugins.yaml        # Plugin configuration
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
# Required
LLM_API_KEY=your_api_key_here

# LLM Configuration
LLM_MODEL=anthropic/claude-3-5-nano
LLM_BASE_URL=https://openrouter.ai/api/v1

# Optional: Web Search
SERPER_API_KEY=your_serper_key

# ASR Configuration
WHISPER_MODEL_SIZE=base
ASR_ENGINE=whisper  # or sherpa

# TTS Configuration (via plugins/plugins.yaml)
# See plugins/plugins.yaml for TTS voice settings

# Speaker Identification (optional)
ENABLE_SPEAKER_ID=false
SPEAKER_MODEL_PATH=../models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx
SPEAKER_DB_PATH=../data/speakers.db
```

## Plugin System

The backend uses a pluggable architecture for TTS engines. Configure plugins in `plugins/plugins.yaml`:

```yaml
tts:
  plugin: tts-edge           # Plugin folder name
  config:
    voice_en: en-US-JennyNeural
    voice_zh: zh-CN-XiaoxiaoNeural
```

### Adding a New TTS Plugin

1. Create plugin directory: `plugins/tts-myplugin/`
2. Implement `TTSEngine` from `tank_contracts.tts`
3. Export `create_engine(config: dict)` function
4. Add to workspace in `backend/pyproject.toml`
5. Configure in `plugins/plugins.yaml`

See `plugins/tts-edge/` for reference implementation.

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
