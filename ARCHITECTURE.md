# Architecture

This document describes the overall architecture of the Tank Voice Assistant monorepo.

## Monorepo Structure

```
tank/
├── backend/          # FastAPI server — ASR, TTS, LLM, tools
├── cli/              # Terminal UI client — Textual TUI, WebSocket
├── web/              # Web frontend — React/TypeScript, browser audio
├── ARCHITECTURE.md   # This file
├── CLAUDE.md         # AI assistant guidance (entry point)
└── README.md         # User-facing overview
```

Each sub-project is independently deployable with its own dependencies and tests.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                        Clients                          │
│                                                         │
│  ┌──────────────────┐      ┌──────────────────────┐    │
│  │   CLI / TUI      │      │    Web Frontend       │    │
│  │  (Python/Textual)│      │  (React/TypeScript)   │    │
│  │                  │      │                       │    │
│  │ • Mic capture    │      │ • Browser mic (WebRTC)│    │
│  │ • VAD (Silero)   │      │ • Web Audio API       │    │
│  │ • Speaker output │      │ • Voice + Chat modes  │    │
│  └────────┬─────────┘      └──────────┬────────────┘    │
│           │  WebSocket (binary+JSON)  │                  │
└───────────┼───────────────────────────┼──────────────────┘
            │                           │
            ▼                           ▼
┌─────────────────────────────────────────────────────────┐
│                   Backend (FastAPI)                      │
│                                                         │
│  WebSocket /ws/{session_id}                             │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │   ASR    │  │  Brain   │  │   TTS    │  │ Tools  │ │
│  │ Whisper/ │→ │  (LLM +  │→ │ Edge TTS │  │ Calc   │ │
│  │ Sherpa   │  │  Tools)  │  │ + PCM    │  │ Weather│ │
│  └──────────┘  └──────────┘  └──────────┘  │ Search │ │
│                                             └────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Communication Protocol

### WebSocket: Client → Backend

| Frame type | Format | Description |
|------------|--------|-------------|
| Audio | Binary (Int16 PCM, 16 kHz) | Microphone audio stream |
| Text input | JSON `{type:"input", content}` | User typed message |
| Interrupt | JSON `{type:"interrupt"}` | Cancel current response |

### WebSocket: Backend → Client

| Frame type | Format | Description |
|------------|--------|-------------|
| Audio | Binary (Int16 PCM, 24 kHz) | TTS audio chunks |
| Signal | JSON `{type:"signal", content}` | `ready`, `processing_started`, `processing_ended` |
| Transcript | JSON `{type:"transcript", ...}` | ASR result (user speech) |
| Text | JSON `{type:"text", ...}` | Streamed LLM response |
| Update | JSON `{type:"update", metadata}` | Thinking / tool call steps |

## Sub-project Summaries

### Backend (`backend/`)

- **Framework**: FastAPI + Uvicorn
- **ASR**: faster-whisper or sherpa-onnx
- **TTS**: Edge TTS → MP3 → PCM (ffmpeg or pydub)
- **LLM**: OpenAI-compatible API (any provider)
- **Tools**: Calculator, Weather, Time, WebSearch, WebScraper
- **Docs**: [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md)

### CLI (`cli/`)

- **Framework**: Textual (TUI)
- **Audio**: sounddevice + silero-vad
- **Transport**: WebSocket client
- **Docs**: [cli/ARCHITECTURE.md](cli/ARCHITECTURE.md)

### Web (`web/`)

- **Framework**: React 19 + TypeScript
- **Audio**: Web Audio API + AudioWorklet
- **Transport**: Browser WebSocket
- **Docs**: [web/ARCHITECTURE.md](web/ARCHITECTURE.md)

## Data Flow (Voice Conversation)

```
User speaks
    │
    ▼
[Client] Mic → VAD → Int16 PCM chunks → WebSocket (binary)
    │
    ▼
[Backend] Audio buffer → ASR → transcript text
    │
    ▼
[Backend] Brain → LLM (streaming) → tool calls → final text
    │
    ▼
[Backend] TTS → MP3 → PCM chunks → WebSocket (binary)
    │
    ▼
[Client] PCM → Speaker playback
```

## Development Setup

See [README.md](README.md) for quick start. Each sub-project has its own `DEVELOPMENT.md`:
- [backend/DEVELOPMENT.md](backend/DEVELOPMENT.md)
- [cli/DEVELOPMENT.md](cli/DEVELOPMENT.md)
- [web/DEVELOPMENT.md](web/DEVELOPMENT.md)
