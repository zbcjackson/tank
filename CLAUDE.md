# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Required Reading**: At the start of each session, you MUST read the following files:
- [CODING_STANDARDS.md](CODING_STANDARDS.md) - Coding standards and design principles
- [TESTING.md](TESTING.md) - Testing guidelines and TDD workflow

## Project Overview

Tank is a voice assistant that supports both Chinese and English, combining speech recognition (OpenAI Whisper), text-to-speech (Edge TTS), and LLM integration for natural conversation. The assistant can execute tools like calculations, weather queries, web searches, and more through function calling.

## Development Methodology

See [CODING_STANDARDS.md](CODING_STANDARDS.md) for coding standards and design principles.
See [TESTING.md](TESTING.md) for testing guidelines and TDD workflow.

## Development Commands

### Setup and Installation
```bash
# Install dependencies
uv sync

# Create example configuration
python main.py --create-config
```

### Running the Application
```bash
# Start the voice assistant
python main.py

# Check system status
python main.py --check

# Use custom config file
python main.py --config /path/to/custom/.env
```

## Architecture Overview

### Core Components

**VoiceAssistant** (`src/voice_assistant/assistant.py`): Main orchestrator with continuous operation:
- Always-listening conversation flow with real-time interruption
- Task management system that cancels LLM and TTS operations when speech detected
- Seamless switching between listening, processing, and speaking states
- Maintains conversation history and language detection across sessions

**LLM** (`src/voice_assistant/llm/llm.py`): OpenAI-compatible API integration with automatic tool calling:
- Supports any OpenAI-compatible endpoint (OpenRouter, OpenAI, custom)
- Implements iterative tool calling workflow
- Handles multiple tool calls per conversation turn
- Returns aggregated usage statistics

**ToolManager** (`src/voice_assistant/tools/manager.py`): Tool execution framework:
- Auto-registers available tools on initialization
- Converts tools to OpenAI function calling format
- Handles tool execution from LLM function calls
- Supports conditional tool registration (e.g., WebSearchTool requires API key)

### Audio Processing

**ContinuousTranscriber** (`src/voice_assistant/audio/continuous_transcription.py`): Always-on speech detection and transcription
- Continuous voice activity detection using energy thresholds
- Automatic speech start/end detection with 2-second silence timeout
- Real-time audio streaming with 100ms chunks
- Interruption callback system for stopping other tasks when speech detected
- Non-blocking transcription using thread pool execution

**EdgeTTSSpeaker** (`src/voice_assistant/audio/tts.py`): Interruptible text-to-speech using Microsoft Edge TTS
- Multiple voice options for Chinese and English
- Async audio playback with interruption support
- Process management for audio playback termination
- Graceful handling of TTS generation interruption

### Configuration System

**VoiceAssistantConfig** (`src/voice_assistant/config/settings.py`): Centralized configuration management
- Environment variable loading with validation
- Default values for all settings
- Support for custom config file paths

### Available Tools

All tools inherit from `BaseTool` (`src/voice_assistant/tools/base.py`) and are automatically registered:

- **Calculator**: Mathematical computations
- **Weather**: Weather information (mock data for demo)
- **Time**: Current date/time queries
- **WebSearch**: Real-time web search (requires SERPER_API_KEY)
- **WebScraper**: Web content extraction

### Configuration Requirements
- `LLM_API_KEY`: Required for any LLM provider
- `SERPER_API_KEY`: Optional, enables web search functionality
- All other settings have sensible defaults

## Development Notes

- The system uses continuous listening with real-time speech interruption
- All async tasks are designed to be cancellable for responsive interaction
- Voice activity detection uses energy-based thresholds (configurable)
- The assistant maintains context across interrupted conversations
- Both Chinese and English are first-class supported languages
- Test coverage includes voice activity detection, interruption, and async task management
