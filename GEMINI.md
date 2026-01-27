# GEMINI.md

This file provides specific context and instructions for the Gemini agent working on the Tank Voice Assistant project.

## Project Overview

**Tank** is a bilingual (Chinese/English) voice assistant that integrates:
- **Speech-to-Text (STT)**: OpenAI Whisper (local, continuous listening).
- **Text-to-Speech (TTS)**: Edge TTS (natural sounding, interruptible).
- **LLM**: OpenAI-compatible API (e.g., OpenRouter, OpenAI) for reasoning and conversation.
- **Tools**: Capability to execute function calls (weather, time, web search/scraping, calculator).

The core design philosophy emphasizes **responsiveness** and **interruption**. The assistant listens continuously and can be interrupted by the user at any time (during LLM processing or TTS playback).

## Architecture & Core Components

### 1. Main Entry Point (`main.py`)
- Handles CLI arguments (`--config`, `--check`, `--create-config`).
- Initializes `VoiceAssistant`.
- Runs the main async event loop.

### 2. Voice Assistant (`src/voice_assistant/assistant.py`)
- **Role**: Central orchestrator.
- **Key Features**:
    - Manages the `conversation_loop`.
    - Handles **interruption**: Cancels pending `current_llm_task` or `current_tts_task` when new speech is detected via `_handle_speech_interruption`.
    - Maintains conversation history.
    - Determines language for TTS based on content or detection.

### 3. Audio Processing
- **STT (`src/voice_assistant/audio/continuous_transcription.py`)**:
    - Uses a thread pool for blocking Whisper operations to avoid freezing the async loop.
    - Implements voice activity detection (VAD) with energy thresholds.
    - Streams audio in chunks.
- **TTS (`src/voice_assistant/audio/tts.py`)**:
    - Wraps `edge-tts`.
    - Async generation and playback.
    - Must be interruptible (handles `asyncio.CancelledError`).

### 4. LLM & Tools
- **LLM (`src/voice_assistant/llm/llm.py`)**:
    - Handles API communication.
    - Supports iterative tool calling loop.
- **Tool Manager (`src/voice_assistant/tools/manager.py`)**:
    - Registers tools (`src/voice_assistant/tools/`).
    - Converts Python methods to OpenAI function schemas.
    - Executes tools securely.
    - **Current Tools**: `Calculator`, `Weather`, `Time`, `WebSearch` (requires API key), `WebScraper`.

## Development Guidelines

### Package Management
- **Tool**: `uv` is the primary package manager.
- **Commands**:
    - Install dependencies: `uv sync`
    - Run tests: `uv run python -m pytest tests/`
    - Run app: `uv run python main.py` (or just `python main.py` if venv is active)

### Testing
- **Framework**: `pytest` with `pytest-asyncio`.
- **Location**: `tests/`
- **Conventions**:
    - Mock external APIs (LLM, Search) and hardware (Audio I/O) in tests.
    - Ensure async tests are properly marked or configured.
    - Run full suite before major commits.

### Code Style & Patterns
- **Async/Await**: The core system is asynchronous. Ensure strictly non-blocking code in the main thread.
- **Type Hinting**: Use `typing` (e.g., `List`, `Optional`, `Dict`) extensively.
- **Error Handling**:
    - Graceful degradation (e.g., if TTS fails, log it but don't crash).
    - Use `try/except` blocks around external service calls.
- **Logging**: Use `logging` module, not `print` (except for CLI user feedback).

## Context for Gemini

1.  **Environment Setup**:
    - Always assume `uv` is installed.
    - Check `.env` for configuration (but don't print secrets).
    - `LLM_API_KEY` is critical for functionality.

2.  **Modifying Code**:
    - When modifying `assistant.py`, be extremely careful with the interruption logic (`_handle_speech_interruption`).
    - When adding tools, inherit from `BaseTool` (`src/voice_assistant/tools/base.py`) and register in `ToolManager`.

3.  **Common Tasks**:
    - **Fixing Bugs**: Check logs first. Interruption logic and async race conditions are common sources of issues.
    - **Adding Features**: Follow the pattern: define interface -> implement -> add tests -> register.

4.  **Hardware Dependencies**:
    - Note that `sounddevice` and `whisper` require actual hardware or mocked interfaces in a CI/headless environment. Be mindful when running code that accesses audio devices.
