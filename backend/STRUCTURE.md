# Backend Structure

Complete directory structure and organization of the Tank Backend.

## Directory Structure

```
backend/
├── core/                          # Main backend application
│   ├── src/tank_backend/         # Source code
│   │   ├── api/                  # FastAPI routes and WebSocket handlers
│   │   │   ├── router.py         # Main WebSocket endpoint
│   │   │   └── speakers.py       # Speaker management API
│   │   ├── audio/
│   │   │   ├── input/            # Audio input processing
│   │   │   │   ├── asr.py        # ASR engine abstraction
│   │   │   │   ├── asr_sherpa.py # Sherpa-ONNX ASR implementation
│   │   │   │   ├── vad.py        # Voice Activity Detection
│   │   │   │   ├── voiceprint.py # Speaker identification
│   │   │   │   └── ...
│   │   │   └── output/           # Audio output processing
│   │   │       ├── tts.py        # TTS engine abstraction
│   │   │       ├── playback_worker.py # Audio playback
│   │   │       └── ...
│   │   ├── core/                 # Core orchestration
│   │   │   ├── brain.py          # Conversation orchestrator
│   │   │   ├── assistant.py      # High-level coordinator
│   │   │   ├── events.py         # Event types
│   │   │   └── worker.py         # Worker base class
│   │   ├── llm/                  # LLM integration
│   │   │   └── llm.py            # LLM client with tool calling
│   │   ├── tools/                # Tool implementations
│   │   │   ├── base.py           # BaseTool abstract class
│   │   │   ├── manager.py        # Tool registration and execution
│   │   │   ├── calculator.py     # Calculator tool
│   │   │   ├── weather.py        # Weather tool
│   │   │   ├── time.py           # Time tool
│   │   │   ├── web_search.py     # Web search tool
│   │   │   └── web_scraper.py    # Web scraper tool
│   │   ├── plugin/               # Plugin system
│   │   │   ├── config.py         # Plugin configuration
│   │   │   └── loader.py         # Dynamic plugin loading
│   │   ├── config/               # Configuration management
│   │   │   └── settings.py       # Pydantic settings
│   │   ├── prompts/              # System prompts
│   │   │   └── system_prompt.txt # Default system prompt
│   │   └── main.py               # Application entry point
│   ├── tests/                    # Test suite (107 tests)
│   │   ├── test_brain.py
│   │   ├── test_assistant.py
│   │   ├── test_asr.py
│   │   ├── test_voiceprint*.py
│   │   └── ...
│   ├── .env                      # Configuration file (not in git)
│   ├── .env.example              # Example configuration
│   └── pyproject.toml            # Core dependencies
│
├── contracts/                     # Shared interfaces
│   ├── tank_contracts/
│   │   ├── __init__.py
│   │   └── tts.py                # TTSEngine ABC, AudioChunk
│   └── pyproject.toml
│
├── plugins/                       # TTS plugins
│   ├── plugins.yaml              # Plugin configuration
│   └── tts-edge/                 # Edge TTS plugin
│       ├── tts_edge/
│       │   ├── __init__.py
│       │   └── engine.py         # EdgeTTSEngine implementation
│       ├── tests/
│       │   └── test_engine.py    # Plugin tests (4 tests)
│       └── pyproject.toml
│
├── data/                         # Runtime data (not in git)
│   ├── speakers.db               # Speaker identification database
│   └── *.npy                     # Audio samples for testing
│
├── models/                       # ML models (not in git)
│   ├── sherpa-onnx-zipformer-en-zh/  # ASR model
│   └── speaker/                  # Speaker embedding models
│       └── *.onnx
│
├── scripts/                      # Utility scripts
│   ├── download_models.py        # Download ASR and speaker models
│   ├── manage_speakers.py        # Speaker database management
│   └── record_audio.py           # Record audio for testing
│
├── pyproject.toml                # Workspace configuration
├── uv.lock                       # Dependency lock file
├── .gitignore                    # Git ignore rules
│
├── README.md                     # Backend overview
├── ARCHITECTURE.md               # System architecture
├── DEVELOPMENT.md                # Development guide
├── CODING_STANDARDS.md           # Coding standards
├── TESTING.md                    # Testing guidelines
├── STRUCTURE.md                  # This file
└── PATH_UPDATE_SUMMARY.md        # Path migration details
```

## Component Organization

### Core Application (`core/`)

The main backend application with all business logic:

- **API Layer** - FastAPI routes and WebSocket handlers
- **Audio Processing** - ASR, TTS, VAD, speaker identification
- **Core Logic** - Brain (conversation orchestrator), Assistant (coordinator)
- **LLM Integration** - OpenAI-compatible API client with tool calling
- **Tools** - Extensible tool system for LLM function calling
- **Plugin System** - Dynamic loading of TTS engines
- **Configuration** - Pydantic-based settings management

### Contracts (`contracts/`)

Shared abstract base classes and interfaces:

- **TTSEngine** - Abstract base class for TTS implementations
- **AudioChunk** - Data class for audio chunks

Plugins implement these interfaces to integrate with the core application.

### Plugins (`plugins/`)

Pluggable TTS engines:

- **plugins.yaml** - Configuration file specifying active plugins
- **tts-edge/** - Edge TTS plugin (default)
- Future: Add more TTS engines (CosyVoice, VITS, etc.)

Each plugin:
1. Implements `TTSEngine` from `tank_contracts.tts`
2. Exports `create_engine(config: dict)` function
3. Has its own `pyproject.toml` and tests
4. Is registered in workspace `backend/pyproject.toml`

### Data (`data/`)

Runtime data (excluded from git):

- **speakers.db** - SQLite database for speaker identification
- **\*.npy** - Audio samples for testing speaker identification

### Models (`models/`)

ML models (excluded from git):

- **sherpa-onnx-zipformer-en-zh/** - Sherpa-ONNX ASR model
- **speaker/** - Speaker embedding models (3D-Speaker, WeSpeaker)

Download with: `uv run python scripts/download_models.py`

### Scripts (`scripts/`)

Utility scripts for development and management:

- **download_models.py** - Download ASR and speaker models
- **manage_speakers.py** - Enroll, list, delete speakers
- **record_audio.py** - Record audio samples for testing

## Running Commands

### From `backend/` directory:

```bash
cd backend

# Sync workspace (installs all dependencies)
uv sync

# Run backend
cd core && uv run tank-backend

# Test everything (core + plugins)
uv run pytest core/tests/ plugins/tts-edge/tests/

# Lint core
cd core && uv run ruff check src/ tests/
```

### From `backend/core/` directory:

```bash
cd backend/core

# Run backend
uv run tank-backend

# Run with auto-reload
uv run tank-backend --reload

# Test core only
uv run pytest

# Lint
uv run ruff check src/ tests/
```

## Path Resolution

All paths in the code use relative paths from `backend/core/`:

- `../data/speakers.db` → `backend/data/speakers.db`
- `../models/sherpa-onnx-zipformer-en-zh` → `backend/models/sherpa-onnx-zipformer-en-zh`
- `../plugins/plugins.yaml` → `backend/plugins/plugins.yaml`

The plugin loader searches upward from the current file to find `plugins/plugins.yaml`, so it works from:
- `backend/core/` directory ✅
- `backend/` directory ✅
- Project root ✅

## Workspace Configuration

The `backend/pyproject.toml` defines a uv workspace:

```toml
[tool.uv.workspace]
members = [
    "core",
    "contracts",
    "plugins/tts-edge",
]
```

This allows:
- Shared dependency resolution across all components
- Single `uv sync` command to install everything
- Consistent versions across the workspace

## Benefits of This Structure

1. **Self-contained** - Everything backend-related is in one directory
2. **Clear separation** - Backend, CLI, and Web are independent siblings
3. **Easier deployment** - Deploy just the `backend/` directory
4. **Plugin architecture** - Easy to add new TTS engines without modifying core
5. **Workspace management** - Single dependency lock file for all components
6. **Path simplicity** - All backend components are close together

## Migration Notes

This structure was created from the original flat structure:

- `tank/contracts/` → `tank/backend/contracts/`
- `tank/plugins/` → `tank/backend/plugins/`
- `tank/backend/src/` → `tank/backend/core/src/`
- `tank/backend/tests/` → `tank/backend/core/tests/`
- `tank/backend/pyproject.toml` → `tank/backend/core/pyproject.toml`

All imports and paths have been updated to reflect the new structure.

---

**Status**: ✅ Complete and tested
**Tests**: 107/107 passing (core) + 4/4 passing (plugins)
**Date**: 2026-03-06
