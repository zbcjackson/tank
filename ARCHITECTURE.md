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

### Audio Input Pipeline (Mic → Segmenter → Perception)

**Locations**:
- `src/voice_assistant/audio/input/mic.py` – microphone capture
- `src/voice_assistant/audio/input/segmenter.py` – VAD + utterance segmentation
- `src/voice_assistant/audio/input/asr.py` – ASR (Automatic Speech Recognition)
- `src/voice_assistant/audio/input/perception.py` – Perception thread (ASR + future voiceprint)

**Data flow**: Mic → frames_queue → UtteranceSegmenter → utterance_queue → Perception → brain_input_queue + display_queue

**ASR** (faster-whisper):
- Multi-language with auto-detect
- Model loaded once (default `base`), cached by Hugging Face
- Input: pcm (float32) + sample_rate; output: (text, language, confidence)

**Perception**:
- Consumes complete Utterances from segmenter (one per user utterance)
- Runs ASR and (future) voiceprint in parallel; puts BrainInputEvent into brain_input_queue and DisplayMessage (speaker, text) into display_queue for UI

### Audio Output (TTS and playback)

**Locations**:
- `src/voice_assistant/audio/output/types.py` – AudioOutputRequest, AudioChunk
- `src/voice_assistant/audio/output/tts.py` – TTSEngine Protocol (no edge_tts dependency)
- `src/voice_assistant/audio/output/tts_engine_edge.py` – Edge TTS backend (only file that imports edge_tts)
- `src/voice_assistant/audio/output/playback.py` – play_stream (PCM to sounddevice)
- `src/voice_assistant/audio/output/speaker.py` – SpeakerHandler

**Description**: Interruptible text-to-speech via abstract TTSEngine; Edge TTS backend streams MP3, decodes to PCM, plays through sounddevice.

**Features**:
- Data class `AudioOutputRequest` (content, language, voice) in audio_output_queue
- TTSEngine Protocol for TTS abstraction; EdgeTTSEngine implements it with edge_tts + pydub
- SpeakerHandler (queue worker with event loop) consumes requests, calls TTS generate_stream and play_stream
- Streaming: generate and play PCM chunks for lower latency
- Interruptible: interrupt_event stops TTS stream and playback

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
