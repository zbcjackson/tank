# CLAUDE.md - Backend

This file provides guidance to Claude Code when working with the Tank Backend API Server.

**Required Reading**: At the start of each session working on backend code, you MUST read:
- @ARCHITECTURE.md [ARCHITECTURE.md](ARCHITECTURE.md) - Backend architecture and components
- @CODING_STANDARDS.md [CODING_STANDARDS.md](CODING_STANDARDS.md) - Backend coding standards
- @DEVELOPMENT.md [DEVELOPMENT.md](DEVELOPMENT.md) - Backend development commands
- @TESTING.md [TESTING.md](TESTING.md) - Backend testing guidelines

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
