# CLAUDE.md - Backend

This file provides guidance to Claude Code when working with the Tank Backend API Server.

**Required Reading**: At the start of each session working on backend code, you MUST read:
- @ARCHITECTURE.md [ARCHITECTURE.md](ARCHITECTURE.md) - Backend architecture and components
- @CODING_STANDARDS.md [CODING_STANDARDS.md](CODING_STANDARDS.md) - Backend coding standards
- @DEVELOPMENT.md [DEVELOPMENT.md](DEVELOPMENT.md) - Backend development commands
- @TESTING.md [TESTING.md](TESTING.md) - Backend testing guidelines

## Verification Checklist

After making changes, you MUST run ALL of these steps in order. Do NOT skip any step.

```bash
# 1. Unit/integration tests
cd backend && uv run pytest core/tests/ -q

# 2. Lint
uv run ruff check core/src/

# 3. Type check on changed files (catches .get() on dataclasses, wrong attribute access, etc.)
#    Run pyright on the files you modified — not the whole codebase (pre-existing errors exist).
uv run pyright path/to/changed_file1.py path/to/changed_file2.py

# 4. Check the running dev server for reload errors
#    The dev server is started via `../scripts/dev.sh` (tmux session "tank").
#    If not already running, start it first:
#    ../scripts/dev.sh
#    After changes, uvicorn auto-reloads. You MUST check for errors:
tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"

# 5. E2E tests (Cucumber + Playwright)
#    Requires backend + web frontend running (the tmux "tank" session has both).
#    See test/TESTING.md for details.
cd /Users/zbcjackson/src/tank/test && pnpm test
```

Steps 4 and 5 are critical. Unit tests mock most dependencies, so they miss runtime errors like calling `.get()` on a dataclass or passing the wrong type to a constructor. The dev server and e2e tests exercise the full stack with real objects: server startup → WebSocket session → Brain._build_agent_graph → LLM pipeline. If any step shows errors, fix them before considering the task done.

## Project Overview

Tank Backend is a FastAPI-based server that provides:
- Speech recognition (ASR) via pluggable engines (Sherpa-ONNX, ElevenLabs)
- Text-to-Speech (TTS) via pluggable engines (Edge TTS, ElevenLabs)
- Speaker identification via pluggable engines (Sherpa-ONNX)
- LLM integration for conversation and tool calling
- WebSocket API for real-time communication
- Tool execution framework (calculator, weather, web search, etc.)

## Plugin System

The plugin system uses a lifecycle-managed architecture:
- `PluginManager` (manager.py) — discovery, loading, registration, validation
- `ExtensionRegistry` (registry.py) — manifest catalog keyed by `"plugin:ext"`, on-demand instantiation
- `AppConfig` (config.py) — reads config.yaml, validates slot refs against registry
- `plugins.yaml` — auto-generated plugin inventory (per-plugin/extension enable/disable)
- `config.yaml` — slot assignment (`extension: plugin:ext`) and runtime config

Startup flow: `PluginManager.load_all()` → `AppConfig(registry=registry)` → `registry.instantiate()` → engines passed to AudioInput/AudioOutput via constructor injection.

AudioInput and AudioOutput do NOT load plugins themselves — they receive pre-built engines.

## Technology Stack

- **Framework**: FastAPI + Uvicorn
- **Language**: Python 3.10+
- **Package Manager**: uv
- **ASR**: faster-whisper, sherpa-onnx
- **TTS**: edge-tts
- **LLM**: OpenAI-compatible API
- **Audio**: sounddevice, pydub, silero-vad

## Development Notes

- Use `--reload` flag for auto-reload during development: `uv run tank-backend --reload`
