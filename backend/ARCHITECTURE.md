# Backend Architecture

This document describes the architecture of the Tank Backend API Server.

## Overview

The backend is a FastAPI-based server that handles:
- Real-time audio processing (ASR + TTS)
- LLM conversation with tool calling
- WebSocket communication with clients
- Audio streaming and playback

## Core Components

### 1. API Layer (`src/tank_backend/api/`)

**FastAPI Routes**:
- `/ws` - WebSocket endpoint for real-time communication
- `/health` - Health check endpoint
- `/api/chat` - HTTP chat endpoint (optional)

**WebSocket Protocol**:
- Client → Server: Audio frames, text messages, control signals
- Server → Client: Audio chunks, text responses, status updates

### 2. Brain (`src/tank_backend/core/brain.py`)

**Role**: Central orchestrator for conversation logic

**Responsibilities**:
- Manages conversation history
- Coordinates LLM calls with tool execution
- Handles language detection and switching
- Processes user input and generates responses

**Key Methods**:
- `process_input(text, language)` - Process user text input
- `_call_llm_with_tools()` - LLM call with iterative tool execution
- `_execute_tools()` - Execute tool calls from LLM

### 3. Assistant (`src/tank_backend/core/assistant.py`)

**Role**: High-level coordinator for audio + brain

**Responsibilities**:
- Manages audio input/output pipelines
- Coordinates ASR → Brain → TTS flow
- Handles interruption and cancellation
- Maintains session state

**Key Features**:
- Async event-driven architecture
- Cancellable tasks for responsiveness
- Queue-based communication between components

### 4. Audio Processing

#### ASR (Automatic Speech Recognition)

**Location**: `src/tank_backend/audio/input/`

**Components**:
- `asr.py` - ASR engine abstraction
- `asr_whisper.py` - Faster-whisper backend
- `asr_sherpa.py` - Sherpa-ONNX backend
- `segmenter.py` - Voice Activity Detection + utterance segmentation
- `perception.py` - Audio perception thread (ASR + future voiceprint)

**Data Flow**:
```
Audio frames → Segmenter (VAD) → Utterance → Perception (ASR) → Brain
```

**Features**:
- Multi-language support (auto-detect)
- Streaming recognition
- Energy-based VAD with configurable thresholds

#### TTS (Text-to-Speech)

**Location**: `src/tank_backend/audio/output/`

**Components**:
- `tts.py` - TTS engine abstraction
- `tts_engine_edge.py` - Edge TTS backend
- `speaker.py` - Audio playback handler
- `playback.py` - PCM streaming playback

**Data Flow**:
```
Text → TTS Engine → MP3 chunks → Decoder → PCM chunks → Playback
```

**Features**:
- Streaming generation for low latency
- Interruptible playback
- MP3 → PCM decoding (ffmpeg or pydub)
- Fade-in/fade-out to avoid audio pops

### 5. LLM Integration (`src/tank_backend/llm/`)

**LLM Client** (`llm.py`):
- OpenAI-compatible API integration
- Supports any provider (OpenAI, OpenRouter, Gemini, etc.)
- Handles streaming responses
- Manages conversation history
- Implements iterative tool calling loop

**Features**:
- Automatic tool call detection and execution
- Multi-turn tool calling support
- Usage statistics tracking
- Error handling and retries

### 6. Tool System (`src/tank_backend/tools/`)

**ToolManager** (`manager.py`):
- Auto-registers tools on initialization
- Converts tools to OpenAI function schemas
- Executes tool calls from LLM
- Handles conditional tool registration (e.g., web search requires API key)

**Available Tools**:
- `calculator.py` - Mathematical calculations
- `weather.py` - Weather information
- `time.py` - Current date/time
- `web_search.py` - Real-time web search (requires SERPER_API_KEY)
- `web_scraper.py` - Web content extraction

**Tool Pattern**:
```python
class MyTool(BaseTool):
    name = "my_tool"
    description = "Tool description"

    def get_parameters(self) -> dict:
        return {
            "param1": {"type": "string", "description": "..."}
        }

    def execute(self, param1: str) -> str:
        # Implementation
        return result
```

### 7. Configuration (`src/tank_backend/config/`)

**Settings** (`settings.py`):
- Environment-based configuration
- Pydantic validation
- Default values for all settings
- Support for custom config file paths

**Key Settings**:
- `LLM_API_KEY` - Required for LLM provider
- `LLM_MODEL` - Model identifier
- `LLM_BASE_URL` - API endpoint
- `WHISPER_MODEL_SIZE` - ASR model size
- `TTS_VOICE_EN/ZH` - Voice selection
- `SERPER_API_KEY` - Optional, for web search

## System Characteristics

### Async Architecture

- All I/O operations are async
- Event-driven communication via queues
- Cancellable tasks for interruption support
- Thread pools for CPU-intensive operations (ASR)

### Interruption Handling

- Speech detection cancels pending LLM/TTS tasks
- Graceful task cleanup
- Conversation state preservation
- Real-time responsiveness

### Language Support

- Automatic language detection from speech
- Context-aware TTS voice selection
- Bilingual system prompts
- Seamless Chinese/English switching

## API Protocol

### WebSocket Message Types

**Client → Server**:
```json
{"type": "audio", "data": "<base64>", "sample_rate": 16000}
{"type": "text", "content": "user message"}
{"type": "interrupt"}
```

**Server → Client**:
```json
{"type": "audio", "data": "<base64>"}
{"type": "text", "content": "assistant response"}
{"type": "status", "status": "listening|processing|speaking"}
{"type": "error", "message": "error description"}
```

## Deployment

### Development
```bash
uv run tank-backend
```

### Production
```bash
uv run uvicorn tank_backend.main:app --host 0.0.0.0 --port 8000
```

### Docker (Future)
```bash
docker build -t tank-backend .
docker run -p 8000:8000 tank-backend
```

## Performance Considerations

- ASR runs in thread pool to avoid blocking event loop
- TTS streaming reduces first-byte latency
- Audio chunking (100ms) for real-time processing
- Model caching (Whisper, VAD) for fast startup
- WebSocket for low-latency communication

## Security Considerations

- API key validation
- Input sanitization for tool execution
- Rate limiting (future)
- CORS configuration for web clients
- WebSocket authentication (future)
