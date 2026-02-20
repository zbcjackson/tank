# CLAUDE.md - Backend

This file provides guidance to Claude Code when working with the Tank Backend API Server.

**Required Reading**: At the start of each session working on backend code, you MUST read:
- @ARCHITECTURE.md [ARCHITECTURE.md](ARCHITECTURE.md) - Backend architecture and components
- @CODING_STANDARDS.md [CODING_STANDARDS.md](CODING_STANDARDS.md) - Backend coding standards
- @DEVELOPMENT.md [DEVELOPMENT.md](DEVELOPMENT.md) - Backend development commands
- @TESTING.md [TESTING.md](TESTING.md) - Backend testing guidelines

## Project Overview

Tank Backend is a FastAPI-based server that provides:
- Speech recognition (ASR) via Whisper/Sherpa-ONNX
- Text-to-Speech (TTS) via Edge TTS
- LLM integration for conversation and tool calling
- WebSocket API for real-time communication
- Tool execution framework (calculator, weather, web search, etc.)

## Technology Stack

- **Framework**: FastAPI + Uvicorn
- **Language**: Python 3.10+
- **Package Manager**: uv
- **ASR**: faster-whisper, sherpa-onnx
- **TTS**: edge-tts
- **LLM**: OpenAI-compatible API
- **Audio**: sounddevice, pydub, silero-vad
