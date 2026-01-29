# Architecture

This document describes the architecture and core components of the Tank Voice Assistant project.

## Project Overview

Tank is a bilingual (Chinese/English) voice assistant that integrates:
- **Speech-to-Text (STT)**: OpenAI Whisper (local, continuous listening)
- **Text-to-Speech (TTS)**: Edge TTS (natural sounding, interruptible)
- **LLM**: OpenAI-compatible API (e.g., OpenRouter, OpenAI) for reasoning and conversation
- **Tools**: Capability to execute function calls (weather, time, web search/scraping, calculator)

## Main Entry Point

**`main.py`**:
- Handles CLI arguments (`--config`, `--check`, `--create-config`)
- Initializes `VoiceAssistant`
- Runs the main async event loop

## Core Components

### VoiceAssistant

**Location**: `src/voice_assistant/assistant.py`

**Role**: Central orchestrator with continuous operation

**Key Features**:
- Always-listening conversation flow with real-time interruption
- Manages the `conversation_loop`
- Task management system that cancels LLM and TTS operations when speech detected
- Handles **interruption**: Cancels pending `current_llm_task` or `current_tts_task` when new speech is detected via `_handle_speech_interruption`
- Seamless switching between listening, processing, and speaking states
- Maintains conversation history and language detection across sessions
- Determines language for TTS based on content or detection

### LLM

**Location**: `src/voice_assistant/llm/llm.py`

**Description**: OpenAI-compatible API integration with automatic tool calling

**Features**:
- Supports any OpenAI-compatible endpoint (OpenRouter, OpenAI, custom)
- Handles API communication
- Implements iterative tool calling workflow
- Supports iterative tool calling loop
- Handles multiple tool calls per conversation turn
- Returns aggregated usage statistics

### ToolManager

**Location**: `src/voice_assistant/tools/manager.py`

**Description**: Tool execution framework

**Features**:
- Auto-registers available tools on initialization
- Registers tools (`src/voice_assistant/tools/`)
- Converts tools to OpenAI function calling format
- Converts Python methods to OpenAI function schemas
- Handles tool execution from LLM function calls
- Executes tools securely
- Supports conditional tool registration (e.g., WebSearchTool requires API key)

## Audio Processing

### ContinuousTranscriber (STT)

**Location**: `src/voice_assistant/audio/continuous_transcription.py`

**Description**: Always-on speech detection and transcription

**Features**:
- Uses a thread pool for blocking Whisper operations to avoid freezing the async loop
- Continuous voice activity detection using energy thresholds
- Implements voice activity detection (VAD) with energy thresholds
- Automatic speech start/end detection with 2-second silence timeout
- Real-time audio streaming with 100ms chunks
- Streams audio in chunks
- Interruption callback system for stopping other tasks when speech detected
- Non-blocking transcription using thread pool execution

### EdgeTTSSpeaker (TTS)

**Location**: `src/voice_assistant/audio/tts.py`

**Description**: Interruptible text-to-speech using Microsoft Edge TTS

**Features**:
- Wraps `edge-tts`
- Multiple voice options for Chinese and English
- Async generation and playback
- Async audio playback with interruption support
- Must be interruptible (handles `asyncio.CancelledError`)
- Process management for audio playback termination
- Graceful handling of TTS generation interruption

## Configuration System

### VoiceAssistantConfig

**Location**: `src/voice_assistant/config/settings.py`

**Description**: Centralized configuration management

**Features**:
- Environment variable loading with validation
- Default values for all settings
- Support for custom config file paths

### Configuration Requirements

- `LLM_API_KEY`: Required for any LLM provider
- `SERPER_API_KEY`: Optional, enables web search functionality
- All other settings have sensible defaults

## Available Tools

All tools inherit from `BaseTool` (`src/voice_assistant/tools/base.py`) and are automatically registered:

- **Calculator**: Mathematical computations
- **Weather**: Weather information (mock data for demo)
- **Time**: Current date/time queries
- **WebSearch**: Real-time web search (requires SERPER_API_KEY)
- **WebScraper**: Web content extraction

## System Characteristics

- The system uses continuous listening with real-time speech interruption
- All async tasks are designed to be cancellable for responsive interaction
- Voice activity detection uses energy-based thresholds (configurable)
- The assistant maintains context across interrupted conversations
- Both Chinese and English are first-class supported languages
