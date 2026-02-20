# CLI Architecture

This document describes the architecture of the Tank CLI/TUI Client.

## Overview

The CLI is a terminal-based client that provides:
- Textual-based TUI (Terminal User Interface)
- Local audio capture and playback
- WebSocket client for backend communication
- Real-time conversation display

## Technology Stack

- **Framework**: Textual (TUI framework)
- **Language**: Python 3.10+
- **Package Manager**: uv
- **Audio**: sounddevice, pydub, silero-vad
- **WebSocket**: websockets library

## Core Components

### 1. Main Entry Point (`src/tank_cli/main.py`)

**Responsibilities**:
- Parse CLI arguments
- Initialize configuration
- Launch TUI application
- Handle graceful shutdown

**CLI Arguments**:
- `--server` - Backend server address (default: localhost:8000)
- `--config` - Custom config file path
- `--check` - Check system status

### 2. TUI Application (`src/tank_cli/tui/app.py`)

**Role**: Main Textual application

**Responsibilities**:
- Manage UI layout and components
- Handle user input (keyboard, mouse)
- Coordinate audio and WebSocket handlers
- Display conversation history

**UI Components**:
- Header: Status and connection info
- Conversation: Message history display
- Footer: Input controls and status

### 3. WebSocket Client (`src/tank_cli/cli/client.py`)

**Role**: Communication with backend server

**Responsibilities**:
- Establish and maintain WebSocket connection
- Send audio frames to backend
- Receive audio chunks and text from backend
- Handle connection errors and reconnection

**Message Protocol**:
```json
// Client → Server
{"type": "audio", "data": "<base64>", "sample_rate": 16000}
{"type": "text", "content": "user message"}
{"type": "interrupt"}

// Server → Client
{"type": "audio", "data": "<base64>"}
{"type": "text", "content": "assistant response"}
{"type": "status", "status": "listening|processing|speaking"}
```

### 4. Audio Input (`src/tank_cli/audio/input/`)

**Components**:
- `mic.py` - Microphone capture
- `segmenter.py` - Voice Activity Detection
- `handler.py` - Audio input handler

**Data Flow**:
```
Microphone → Audio frames → VAD → Segments → WebSocket
```

**Features**:
- Continuous audio capture
- Energy-based VAD
- Automatic speech segmentation
- Configurable sample rate and chunk size

### 5. Audio Output (`src/tank_cli/audio/output/`)

**Components**:
- `playback.py` - Audio playback
- `handler.py` - Audio output handler

**Data Flow**:
```
WebSocket → Audio chunks → Decoder → PCM → Speaker
```

**Features**:
- Streaming playback
- Interruptible audio
- Buffer management

### 6. UI Components (`src/tank_cli/tui/ui/`)

**Header** (`header.py`):
- Connection status
- Server address
- Current mode (listening/processing/speaking)

**Conversation** (`conversation.py`):
- Message history display
- Auto-scroll to latest message
- User/Assistant message styling
- Markdown rendering

**Footer** (`footer.py`):
- Input controls
- Status indicators
- Keyboard shortcuts help

### 7. Configuration (`src/tank_cli/config/`)

**Settings** (`settings.py`):
- Server connection settings
- Audio configuration
- UI preferences
- Keyboard shortcuts

**Key Settings**:
- `SERVER_HOST` - Backend server host
- `SERVER_PORT` - Backend server port
- `SAMPLE_RATE` - Audio sample rate
- `CHUNK_SIZE` - Audio chunk size

## System Characteristics

### Async Architecture

- All I/O operations are async
- Event-driven UI updates
- Non-blocking audio processing
- Concurrent WebSocket and audio handling

### Real-time Responsiveness

- Low-latency audio streaming
- Immediate UI updates
- Smooth scrolling and animations
- Keyboard shortcut handling

### Error Handling

- Graceful connection failures
- Automatic reconnection attempts
- User-friendly error messages
- Fallback to text-only mode

## UI Layout

```
┌─────────────────────────────────────────┐
│ Header: Status | Server | Mode          │
├─────────────────────────────────────────┤
│                                         │
│ Conversation:                           │
│   User: Hello                           │
│   Assistant: Hi! How can I help?        │
│   User: What's the time?                │
│   Assistant: It's 2:30 PM               │
│                                         │
│                                         │
├─────────────────────────────────────────┤
│ Footer: [Space] Talk | [Q] Quit         │
└─────────────────────────────────────────┘
```

## Keyboard Shortcuts

- `Space` - Push to talk (hold to record)
- `Enter` - Send text message
- `Ctrl+C` / `Q` - Quit application
- `Ctrl+L` - Clear conversation
- `↑/↓` - Scroll conversation history

## Connection Flow

1. **Startup**:
   - Load configuration
   - Initialize audio devices
   - Connect to backend WebSocket

2. **Connected**:
   - Start audio capture
   - Display conversation UI
   - Handle user input

3. **Disconnected**:
   - Show error message
   - Attempt reconnection
   - Fallback to text-only mode

4. **Shutdown**:
   - Close WebSocket connection
   - Stop audio devices
   - Save conversation history (future)

## Performance Considerations

- Audio processing in separate thread
- UI updates batched for smooth rendering
- Message history pagination (future)
- Efficient WebSocket message handling

## Future Enhancements

- Conversation history persistence
- Multiple conversation sessions
- Voice activity visualization
- Custom themes and styling
- Plugin system for extensions
