# Architecture

This document describes the overall architecture of the Tank Voice Assistant monorepo.

## Monorepo Structure

```
tank/
├── backend/          # FastAPI server — pipeline, agents, ASR, TTS, LLM, tools
├── cli/              # Terminal UI client — Textual TUI, WebSocket
├── web/              # Web frontend — React/TypeScript, browser audio
├── macos/            # Native macOS app — Tauri 2/Rust, wraps web/
├── test/             # E2E tests — Cucumber + Playwright
├── ARCHITECTURE.md   # This file
├── CLAUDE.md         # AI assistant guidance (entry point)
└── README.md         # User-facing overview
```

Each sub-project is independently deployable with its own dependencies and tests.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          Clients                             │
│                                                              │
│  ┌──────────────────┐   ┌──────────────────────┐            │
│  │   CLI / TUI      │   │    Web Frontend       │            │
│  │  (Python/Textual) │   │  (React/TypeScript)   │            │
│  │ • Mic capture     │   │ • Browser mic (WebRTC)│            │
│  │ • VAD (Silero)    │   │ • Web Audio API       │            │
│  │ • Speaker output  │   │ • Voice + Chat modes  │            │
│  └────────┬──────────┘   └──────────┬────────────┘            │
│           │ WebSocket (binary+JSON)  │                        │
│           │   ┌──────────────────┐   │                        │
│           │   │ macOS App (Tauri)│───┘                        │
│           │   │ Wraps web/ as    │                            │
│           │   │ native .app      │                            │
│           │   └──────────────────┘                            │
└───────────┼──────────────────────────┼────────────────────────┘
            │                          │
            ▼                          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Backend (FastAPI)                           │
│                                                              │
│  Layer 1: Audio Pipeline (GStreamer-inspired)                 │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Audio In → [VAD] → [Q] → [ASR] → [Speaker ID]        │  │
│  │                                      ↓                 │  │
│  │ Audio Out ← [Playback] ← [TTS] ← [Echo Guard] ← Brain│  │
│  │                                                        │  │
│  │ Bounded queues · Backpressure · Bidirectional events   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Layer 2: Agent Orchestration                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ AgentGraph → ChatAgent (all tools)                    │  │
│  │ Approval gates · Checkpointing · Streaming to TTS     │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Layer 3: LLM Transport (Raw SDK)                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ AsyncOpenAI (Langfuse-wrapped) · Retry · Token count   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Cross-cutting: Message Bus + Observers + Langfuse           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Health monitoring · QoS feedback · Alerting · Metrics  │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Why Three Layers

- **Layer 1 (Audio Pipeline)** has hard real-time constraints — 20ms audio frames, interrupt within 10ms, backpressure on queues. It must never block on agent logic.
- **Layer 2 (Agent Orchestration)** is where intelligence lives — a single ChatAgent with all tools, managing conversation state, handling tool approval. Streams LLM tokens to TTS immediately (not batch them).
- **Layer 3 (LLM Transport)** is a thin wrapper — raw `AsyncOpenAI` with retry, token counting, and Langfuse tracing. No framework, no abstraction tax.

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
| Update | JSON `{type:"update", metadata}` | Thinking / tool call / approval steps |

### REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (simple or `?detail=true` for deep) |
| `/api/metrics` | GET | Aggregated pipeline metrics |
| `/api/approvals` | GET | List pending tool approvals |
| `/api/approvals/{id}/respond` | POST | Approve/reject tool execution |
| `/api/speakers` | GET | List enrolled speakers |

## Sub-project Summaries

### Backend (`backend/`)

- **Framework**: FastAPI + Uvicorn
- **Architecture**: Three-layer pipeline (audio, agent orchestration, LLM transport)
- **ASR**: Sherpa-ONNX (pluggable)
- **TTS**: Edge TTS (pluggable)
- **LLM**: OpenAI-compatible API via AsyncOpenAI (any provider)
- **Agents**: Chat, Search, Task, Code — with intent routing and approval gates
- **Tools**: Calculator, Weather, Time, WebSearch, WebScraper, Sandbox (Docker)
- **Observability**: Langfuse LLM tracing, Bus-based pipeline metrics, health monitoring, alerting
- **Persistence**: SQLite checkpointing for conversation history
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

### macOS (`macos/`)

- **Framework**: Tauri 2 (Rust)
- **Frontend**: Reuses `web/` (no own UI code)
- **Native**: macOS .app bundle with overlay title bar
- **Docs**: [macos/ARCHITECTURE.md](macos/ARCHITECTURE.md)

## Data Flow (Voice Conversation)

```
User speaks
    │
    ▼
[Client] Mic → VAD → Int16 PCM chunks → WebSocket (binary)
    │
    ▼
[Backend Pipeline]
    Audio frames → VADProcessor (echo guard threshold switching)
      → ThreadedQueue
      → ASRProcessor → transcript text
      → FanOutQueue ─┬─ SpeakerIDProcessor
                      └─ ASRSpeakerMerger
      → ThreadedQueue
      → BrainProcessor
          → Router (keyword/LLM intent classification)
          → Agent (Chat/Search/Task/Code)
          → Approval gate (if sensitive tool)
          → LLM streaming → tool calls → response text
      → EchoGuard (filter self-echo)
      → ThreadedQueue
      → TTSProcessor → audio chunks
      → PlaybackProcessor → WebSocket (binary)
    │
    ▼
[Client] PCM → Speaker playback
```

### Interruption Flow

```
User speaks during assistant response
    │
    ▼
VADProcessor detects speech → PipelineEvent(interrupt, UPSTREAM)
    → PlaybackProcessor: fade-out (no audio pop)
    → TTSProcessor: cancel generation
    → BrainProcessor: cancel LLM, save partial response
    → All ThreadedQueues: flush
```

## Development Setup

See [README.md](README.md) for quick start. Each sub-project has its own `DEVELOPMENT.md`:
- [backend/DEVELOPMENT.md](backend/DEVELOPMENT.md)
- [cli/DEVELOPMENT.md](cli/DEVELOPMENT.md)
- [web/DEVELOPMENT.md](web/DEVELOPMENT.md)
- [macos/DEVELOPMENT.md](macos/DEVELOPMENT.md)
