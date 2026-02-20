# Web Frontend Architecture

This document describes the architecture of the Tank Web Frontend.

## Overview

The web frontend is a React/TypeScript SPA that provides:
- Voice mode: real-time audio streaming with animated UI
- Chat mode: text-based conversation with streaming responses
- WebSocket communication with the backend
- Browser-based audio capture and playback via Web Audio API

## Technology Stack

- **Framework**: React 19
- **Language**: TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS v4
- **Animation**: Framer Motion
- **Icons**: Lucide React
- **Markdown**: react-markdown + remark-gfm

## Directory Structure

```
web/src/
├── App.tsx                    # Root component, session management
├── main.tsx                   # Entry point
├── components/
│   └── Assistant/
│       ├── VoiceMode.tsx      # Animated voice interface
│       ├── ChatMode.tsx       # Chat message list + input
│       ├── MessageStep.tsx    # Individual message renderer
│       ├── ModeToggle.tsx     # Voice/Chat switch button
│       ├── Waveform.tsx       # Audio waveform animation
│       └── WeatherCard.tsx    # Weather tool result card
├── hooks/
│   └── useAssistant.ts        # Core state + WebSocket + audio logic
└── services/
    ├── websocket.ts           # VoiceAssistantClient class
    └── audio.ts               # AudioProcessor (mic capture + VAD)
```

## Core Components

### `App.tsx`

Root component. Generates a random `SESSION_ID`, calls `useAssistant`, and renders either `VoiceMode` or `ChatMode` based on current mode. Handles connection error overlay.

### `useAssistant` hook (`hooks/useAssistant.ts`)

The central state manager. Owns:
- `messages: ChatMessage[]` — conversation history
- `mode: 'voice' | 'chat'` — current UI mode
- `connectionStatus` — `connecting | connected | error | disconnected`
- `isAssistantTyping` / `isSpeaking` — UI state flags

On mount: creates `VoiceAssistantClient` and `AudioProcessor`, connects both, tears down on unmount.

Message handling logic:
- `signal` messages update connection/typing state
- `transcript` messages create user text entries
- `update` messages with `THOUGHT` metadata → thinking steps
- `update` messages with `TOOL_CALL/TOOL_RESULT` → tool steps
- `text` messages → assistant text (streamed, appended by `msg_id + turn`)
- Weather tool results generate an additional `WeatherCard` entry

### `VoiceAssistantClient` (`services/websocket.ts`)

Wraps the browser `WebSocket` API.

- **Binary frames** (ArrayBuffer): Int16 PCM audio from server → decoded to Float32 → scheduled via Web Audio API with gapless playback (`nextStartTime` pointer)
- **Text frames** (JSON): parsed as `WebsocketMessage`, forwarded to `onMessage` callback
- `sendAudio(Int16Array)` — sends raw PCM binary to server
- `sendMessage(type, content, metadata)` — sends JSON text frame
- Tracks `isSpeaking` via a timer that expires when scheduled audio ends

### `AudioProcessor` (`services/audio.ts`)

Handles microphone capture in the browser.

- Requests `getUserMedia` for audio
- Uses `AudioWorklet` (or `ScriptProcessor` fallback) for low-latency capture
- Resamples to 16 kHz Int16 PCM
- Sends chunks to server via `sendAudio` callback

## WebSocket Protocol

### Client → Server

| Frame | Format | Description |
|-------|--------|-------------|
| Audio | Binary (Int16 PCM) | Raw microphone audio at 16 kHz |
| Text input | JSON `{type:"input", content}` | User typed message |

### Server → Client

| Frame | Format | Description |
|-------|--------|-------------|
| Audio | Binary (Int16 PCM, 24 kHz) | TTS audio chunks |
| Signal | JSON `{type:"signal", content:"ready\|processing_started\|processing_ended"}` | Status signals |
| Transcript | JSON `{type:"transcript", content, is_user:true}` | ASR result |
| Text | JSON `{type:"text", content, msg_id, metadata}` | Streamed LLM text |
| Update | JSON `{type:"update", metadata:{update_type}}` | Thinking / tool steps |

## State Model

```typescript
interface ChatMessage {
  id: string;        // stepId = `${msgId}_${type}_${turn}[_index]`
  role: 'user' | 'assistant';
  type: 'text' | 'thinking' | 'tool' | 'weather';
  content: any;      // string for text/thinking, object for tool/weather
  msgId: string;
  isFinal?: boolean;
}
```

Streaming text/thinking messages are updated in-place by matching `id`. Tool messages are upserted by `id`. Weather cards are appended as separate entries.

## UI Modes

### Voice Mode

Full-screen animated interface showing:
- Waveform animation when assistant is speaking
- Idle animation when listening
- Connection status overlay

### Chat Mode

Scrollable message list with:
- User messages (right-aligned)
- Assistant text with Markdown rendering
- Collapsible thinking steps
- Tool call/result cards
- Weather cards
- Typing indicator
- Text input with send button
