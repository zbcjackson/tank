# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tank is a voice assistant that supports both Chinese and English, combining speech recognition (OpenAI Whisper), text-to-speech (Edge TTS), and LLM integration for natural conversation. The assistant can execute tools like calculations, weather queries, web searches, and more through function calling.

## Development Methodology

**Follow Test-Driven Development (TDD):**
- Write tests BEFORE implementing any logic changes
- Run tests frequently throughout development
- Ensure all tests pass before committing changes
- Maintain high test coverage for critical components

**Testing Workflow:**
1. Write a failing test that describes the desired behavior
2. Implement the minimal code needed to make the test pass
3. Refactor the code while keeping tests green
4. Run the full test suite to ensure no regressions

**Key Testing Practices:**
- Test all tool functionality and edge cases
- Mock external dependencies (API calls, file system operations)
- Use async tests for async components
- Test error conditions and exception handling
- Verify configuration validation and defaults

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

### Testing
```bash
# Run all tests
uv run python -m pytest tests/

# Run with coverage
uv run python -m pytest tests/ --cov=src/voice_assistant

# Run specific test file
uv run python -m pytest tests/test_tools.py

# Run tests in watch mode during development
uv run python -m pytest tests/ --watch
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

## Key Technical Patterns

### Tool System
- Tools use declarative parameter schemas with type validation
- ToolManager automatically converts tools to OpenAI function calling format
- LLM handles iterative tool calling until completion
- Tool results are properly formatted as tool messages in conversation history

### Continuous Listening System
- Always-on voice activity detection with configurable energy thresholds
- Automatic speech segmentation: starts recording on speech, stops after 2 seconds of silence
- Real-time interruption: any detected speech immediately cancels current LLM/TTS tasks
- Non-blocking audio processing with 100ms chunk granularity
- Thread-pool transcription to avoid blocking the event loop

### Task Interruption Pattern
- All long-running tasks (LLM completion, TTS generation/playback) are cancellable
- Speech detection triggers immediate interruption of current operations
- Graceful task cleanup with proper resource management
- Conversation state preservation across interruptions

### Language Handling
- Automatic language detection from speech input
- Context-aware TTS voice selection (Chinese vs English)
- System prompt supports bilingual responses

### Error Handling
- Graceful degradation when components fail
- Comprehensive logging throughout the system
- User-friendly error messages in multiple languages

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

## Import Rules (Critical)

Within `src/voice_assistant/`, always use **relative imports** when referencing other modules in the same package tree.

- **Do**:
  - `from ...core.shutdown import StopSignal`
  - `from ..audio.input import AudioInput`
- **Do not**:
  - `from voice_assistant.core.shutdown import StopSignal`
  - `import voice_assistant.audio.input`