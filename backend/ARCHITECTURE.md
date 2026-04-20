# Backend Architecture

This document describes the architecture of the Tank Backend API Server.

## Overview

The backend is a FastAPI-based server organized into three layers:

1. **Audio Pipeline** (real-time, latency-critical) — processors chained via bounded queues with backpressure, event-driven interruption, and fan-out support
2. **Agent Orchestration** (stateful) — single agent with all tools, human-in-the-loop approval, conversation persistence
3. **LLM Transport** (thin wrapper) — raw `AsyncOpenAI` with retry, token counting, Langfuse tracing

Cross-cutting: Message Bus for decoupled observability, health monitoring, and alerting.

## Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 1: Audio Pipeline (GStreamer-inspired)                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ Audio In → [VAD] → [Q] → [ASR] ──┬──→ [ASR+Speaker Merger]   │ │
│  │                                    │                           │ │
│  │                          [Speaker ID]──┘                       │ │
│  │                                                                │ │
│  │ Audio Out ← [Playback] ← [Q] ← [TTS] ← [Echo Guard] ← Brain │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Layer 2: Agent Orchestration                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ AgentGraph → ChatAgent (all tools)                            │ │
│  │ Approval gates · Checkpointing · Streaming tokens to TTS      │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Layer 3: LLM Transport (Raw SDK)                                   │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ AsyncOpenAI (Langfuse-wrapped) · Retry · Token counting       │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Cross-cutting: Message Bus + Observers + Langfuse Observability    │
└─────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. API Layer (`src/tank_backend/api/`)

**FastAPI Routes**:
- `/ws/{session_id}` — WebSocket endpoint for real-time communication
- `/health` — Health check (simple or `?detail=true` for deep check)
- `/api/chat` — HTTP chat endpoint (optional)
- `/api/metrics` — Aggregated pipeline metrics
- `/api/metrics/{session_id}` — Per-session metrics
- `/api/approvals` — List pending tool approval requests
- `/api/approvals/{id}/respond` — Approve or reject a pending action
- `/api/speakers` — Speaker management (list, enroll, delete)

### 2. Pipeline Architecture (`src/tank_backend/pipeline/`)

The pipeline is a GStreamer-inspired processor chain with bounded queues, backpressure, and bidirectional events.

**Core Abstractions**:

| Component | File | Purpose |
|-----------|------|---------|
| `Processor` | `processor.py` | ABC for all pipeline stages — `async process(item) → AsyncIterator[tuple[FlowReturn, Any]]` |
| `AudioCaps` | `processor.py` | Format declaration (sample_rate, channels, dtype) for audio processors |
| `FlowReturn` | `processor.py` | Enum: `OK`, `EOS`, `FLUSHING`, `ERROR` — backpressure signals |
| `PipelineEvent` | `event.py` | Bidirectional control event (interrupt, flush, eos, qos) |
| `ThreadedQueue` | `queue.py` | Bounded queue with consumer thread — creates thread boundaries |
| `FanOutQueue` | `fan_out_queue.py` | Routes items to parallel branches (e.g., ASR + speaker ID) |
| `Bus` / `BusMessage` | `bus.py` | Thread-safe publish/subscribe message bus |
| `Pipeline` | `builder.py` | Assembled pipeline instance with lifecycle management |
| `PipelineBuilder` | `builder.py` | Fluent builder: `add()`, `fan_out()`, `build()` |

**Key Design Decisions**:
- **Queue = Thread Boundary**: Inserting a `ThreadedQueue` between two processors creates a new thread. Pipeline topology determines threading, not hardcoding.
- **Backpressure**: Bounded queues with `FlowReturn` propagation. When a queue is full, the upstream processor blocks.
- **Bidirectional Events**: Data flows downstream; control events (interrupt, flush) flow upstream from VAD to Playback.
- **Bus for Observability**: Decoupled from pipeline data flow. Any processor can post metrics/state changes; any observer can subscribe.

**Pipeline Data Flow**:
```
Audio frames
  → VADProcessor (voice activity detection, echo guard threshold switching)
  → ThreadedQueue
  → ASRProcessor (speech-to-text)
  → FanOutQueue ──┬── SpeakerIDProcessor (who is speaking)
                   └── ASRSpeakerMerger (combine transcript + speaker)
  → ThreadedQueue
  → BrainProcessor (LLM conversation via AgentGraph)
  → EchoGuard (filter self-echo from TTS output)
  → ThreadedQueue
  → TTSProcessor (text-to-speech + QoS feedback)
  → PlaybackProcessor (speaker output with fade-in/fade-out)
```

#### Processors (`pipeline/processors/`)

| Processor | File | Input | Output |
|-----------|------|-------|--------|
| `VADProcessor` | `vad.py` | Audio frames | Speech segments. Emits `interrupt` events upstream on speech detection. Switches VAD threshold during playback (echo guard layer 1). |
| `ASRProcessor` | `asr.py` | Speech segments | Transcripts. Posts ASR latency metrics to Bus. |
| `SpeakerIDProcessor` | `speaker_id.py` | Audio segments | Speaker identity. |
| `ASRSpeakerMerger` | `asr_speaker_merger.py` | ASR + Speaker ID | Combined transcript with speaker name. |
| `BrainProcessor` | `brain.py` | Transcripts | LLM responses. Delegates to AgentGraph. Token counting, context summarization, QoS feedback, checkpointing. |
| `EchoGuard` | `echo_guard.py` | Transcripts | Filtered transcripts. Layer 2: compares ASR text against recent TTS output using token overlap. |
| `TTSProcessor` | `tts.py` | Text | Audio chunks. Posts QoS messages when queue fill exceeds threshold. |
| `PlaybackProcessor` | `playback.py` | Audio chunks | Speaker output. Handles interrupt with graceful fade-out. |

#### Echo Guard (Defense in Depth)

Prevents the assistant from hearing its own voice through the speakers:

- **Layer 1** (VAD threshold switching): During TTS playback, `VADProcessor` raises the VAD `speech_threshold` (default 0.85) so only loud/close speech triggers detection. Restores default on playback end.
- **Layer 2** (Self-echo text detection): `EchoGuard` maintains a sliding window of recent TTS text. Compares ASR transcripts against it using token overlap ratio. Discards if overlap > threshold (default 0.6).

Both layers are backend-only, platform-independent, and fail-open.

### 3. Agent Orchestration (`src/tank_backend/agents/`)

The Brain delegates to an AgentGraph that runs a single ChatAgent with access to all tools. The LLM decides which tools to call naturally — no routing overhead.

**Components**:

| Component | File | Purpose |
|-----------|------|---------|
| `Agent` | `base.py` | ABC: `async run(state, llm) → AsyncIterator[AgentOutput]` |
| `AgentState` | `base.py` | Shared state: messages, metadata, agent_history, turn counter |
| `AgentOutput` | `base.py` | Streaming output: TOKEN, THOUGHT, TOOL_CALLING, TOOL_EXECUTING, TOOL_RESULT, APPROVAL_NEEDED, HANDOFF, DONE |
| `ChatAgent` | `chat_agent.py` | Conversational agent with tool calling. All registered tools available. |
| `AgentGraph` | `graph.py` | Orchestrator: runs agent, streams outputs, tracks stats. Max 5 iterations. |
| `ApprovalManager` | `approval.py` | Async approval gate for sensitive tool calls |
| `ApprovalPolicy` | `approval.py` | Config-driven: `always_approve`, `require_approval`, `require_approval_first_time` |
| `create_agent` | `factory.py` | Factory function: agent type string → Agent instance |

**Agent Graph Flow**:
```
User message
  → ChatAgent (all tools, comprehensive system prompt)
  → Agent.run(state) streams:
      TOKEN → TTS immediately (no batching)
      TOOL_CALLING → check ApprovalPolicy
        → APPROVAL_NEEDED → pause, await user response
        → or auto-approve → TOOL_EXECUTING → TOOL_RESULT
      DONE → end turn
```

**Key Difference from LangGraph**: Tokens stream immediately via async generators. No batching, no superstep synchronization. Every token flows to TTS the moment it's produced.

#### Approval System

Tools can require human approval before execution. The approval flow:

1. Agent yields `AgentOutput(type=APPROVAL_NEEDED)` with tool name and args
2. `ApprovalManager` creates a pending request with timeout (120s default)
3. Client is notified via WebSocket
4. User approves/rejects via `POST /api/approvals/{id}/respond` or voice ("yes"/"no")
5. Agent resumes with the tool result or rejection notice

**Approval Policies** (configured in `config.yaml`):
- `always_approve` — no approval needed (weather, time, calculator)
- `require_approval` — always ask (run_command, persistent_shell)
- `require_approval_first_time` — ask once per session, then auto-approve (web_search)

### 4. LLM Integration (`src/tank_backend/llm/`)

**LLM Client** (`llm.py`):
- OpenAI-compatible API via `AsyncOpenAI`
- Multiple named profiles (default, summarization) in `config.yaml`
- Streaming responses with real-time token delivery
- Bounded tool iterations (`MAX_TOOL_ITERATIONS = 10`)
- Retry with exponential backoff (`MAX_RETRY_ATTEMPTS = 3`) on transient errors
- Optional Langfuse auto-tracing via monkey-patched `AsyncOpenAI`

**Token Management**:
- `tiktoken`-based token counting
- `max_history_tokens` config (default 8000)
- Automatic context summarization when history exceeds threshold
- Fallback to message-count truncation if summarization fails

### 5. Observability (`src/tank_backend/observability/` + `pipeline/observers/`)

**Two-layer observability strategy**:

1. **Pipeline layer** — Bus + observers for real-time pipeline health
2. **LLM layer** — Langfuse for deep LLM tracing (token usage, cost, prompts, tool calls)

**Observers** (`pipeline/observers/`):

| Observer | File | Purpose |
|----------|------|---------|
| `LatencyObserver` | `latency.py` | Per-stage timing metrics |
| `InterruptLatencyObserver` | `interrupt_latency.py` | VAD trigger → full silence latency |
| `TurnTracker` | `turn_tracking.py` | Conversation turn metrics |
| `MetricsCollector` | `metrics_collector.py` | Aggregated performance metrics + Langfuse trace IDs |
| `HealthMonitor` | `health_monitor.py` | Pipeline health checks from Bus messages |
| `AlertingObserver` | `alerting.py` | Anomaly detection: latency spikes, error rates, queue saturation |

**Langfuse Integration** (`observability/langfuse_client.py`):
- Conditional initialization from env vars (`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`)
- Auto-patches `AsyncOpenAI` for zero-code tracing
- Async/non-blocking — no impact on voice latency
- Self-hostable via Docker

**Health Monitoring** (`pipeline/health.py`):

- `HealthAggregator` — registers named health checks, runs all, returns unified status
- Per-component health: `healthy | degraded | unhealthy`
- Queue health: size, stuck detection, consumer alive status
- Processor health: running status, consecutive failures, last error
- Exposed via `GET /health?detail=true` (returns HTTP 503 if unhealthy)

**QoS Feedback**:
- TTSProcessor posts `"qos"` bus messages when queue fill exceeds threshold
- BrainProcessor subscribes: skips tool calls when TTS is overloaded
- Graceful degradation under load

### 6. Persistence (`src/tank_backend/persistence/`)

**Checkpointer** (`checkpointer.py`):
- SQLite with WAL mode for concurrent reads
- `save(session_id, history)` — upserts conversation state
- `load(session_id)` — restores conversation on reconnect
- `list_sessions()` — all saved sessions with timestamps
- `delete(session_id)` — cleanup

**Brain Integration**:
- On WebSocket connect: loads checkpoint for `session_id` if persistence is enabled
- After each turn: auto-checkpoints conversation history
- Configurable via `config.yaml` (`persistence.enabled`, `persistence.db_path`)

### 7. Tool System (`src/tank_backend/tools/`)

**Core Types** (`base.py`):

```python
@dataclass(frozen=True, slots=True)
class ToolResult:
    content: str          # What the LLM sees (full data, json.dumps'd)
    display: str = ""     # What the UI shows (human-friendly summary)
    error: bool = False   # Whether this is an error result
```

- `BaseTool` — Abstract base with `get_info()` → `ToolInfo` and `execute()` → `ToolResult | str`
- `ToolGroup` — Groups tools that share construction dependencies (e.g. `FileToolGroup`, `WebToolGroup`)
- `ApprovalCallback` — Protocol for per-path approval in file tools

**Tool Result Flow**:

```
tool.execute() → ToolResult | str
    ↓
llm.py: _tool_result_to_str(result) → (llm_content, ui_display)
    ↓
LLM gets llm_content (full data, never truncated)
UI gets ui_display (concise summary for tool card)
```

- `ToolResult.content` is always the complete data (typically `json.dumps` of structured result)
- `ToolResult.display` is a human-friendly summary for the UI (falls back to truncated content)
- Plain `str` return is for tools that produce text directly (e.g. skill instructions)
- `_tool_result_to_str()` in `llm.py` handles the conversion — single source of truth

**ToolManager** (`manager.py`):
- Organizes tools via `ToolGroup` instances (`DefaultToolGroup`, `WebToolGroup`, `FileToolGroup`, `SandboxToolGroup`, `SkillToolGroup`)
- Converts tools to OpenAI function schemas via `get_openai_tools()`
- Executes tool calls from LLM via `execute_openai_tool_call()`
- Integrates `NetworkAccessPolicy`, `ServiceCredentialManager`, `ToolApprovalPolicy`

**Available Tools**:
- `calculator.py` — Mathematical calculations
- `weather.py` — Weather information (OpenWeatherMap)
- `time.py` — Current date/time
- `web_search.py` — Real-time web search (requires SERPER_API_KEY)
- `web_fetch.py` — Web content extraction with content-type routing (HTML, PDF, JSON, RSS, etc.)
- `file_read.py`, `file_write.py`, `file_edit.py`, `file_delete.py` — File operations with access policy
- `file_list.py`, `file_search.py` — Directory listing and content search (ripgrep)
- `run_command.py` — Run a command in Docker sandbox
- `persistent_shell.py` — Persistent shell session in Docker sandbox
- `manage_process.py` — Process management in sandbox
- `skill_tools.py` — Skill management (use, list, create, install, reload, search)

### 8. Plugin System (`src/tank_backend/plugin/`)

The plugin system manages the full lifecycle of pluggable engines (ASR, TTS, speaker identification).

**Components**:
- `manager.py` — `PluginManager`: discovery, loading, registration, validation
- `registry.py` — `ExtensionRegistry`: manifest catalog keyed by `"plugin:ext"`
- `config.py` — `AppConfig`: reads `config.yaml`, validates slot refs against registry
- `manifest.py` — reads `[tool.tank]` from plugin `pyproject.toml`

**Startup Flow**:
```
PluginManager.load_all()
  ├── plugins.yaml missing? → discover_plugins() → generate_plugins_yaml()
  ├── Read plugins.yaml → PluginEntry list
  └── For each enabled plugin/extension: registry.register(plugin, manifest)

Assistant.__init__()
  ├── registry = PluginManager().load_all()
  ├── app_config = AppConfig(registry=registry)   ← validates extension refs
  ├── Build Pipeline via PipelineBuilder
  ├── Create AgentGraph with ChatAgent
  └── Wire processors, bus, observers
```

### 9. Configuration (`src/tank_backend/config/`)

All runtime configuration lives in `backend/core/config.yaml`. Secrets stay in `.env`.

**Config Sections**:
- `llm` — Named LLM profiles (default, summarization)
- `echo_guard` — VAD threshold switching + self-echo text detection
- `asr` / `tts` / `speaker` — Plugin slot assignments
- `sandbox` — Docker sandbox settings for code execution tools
- `agents` — Agent definitions (type, llm_profile)
- `approval_policies` — Tool approval tiers
- `brain` — Conversation processing (max_history_tokens)
- `persistence` — Session checkpointing (enabled, db_path)
- `observability` — Langfuse host configuration

## System Characteristics

### Async Architecture

- All I/O operations are async
- Pipeline uses `ThreadedQueue` for true CPU parallelism
- Event-driven communication via Bus
- Cancellable tasks for interruption support

### Interruption Handling

Bidirectional event-based interruption replaces the old single `threading.Event`:

1. VAD detects speech → emits `PipelineEvent(type="interrupt", direction=UPSTREAM)`
2. Each processor handles independently:
   - Playback: graceful fade-out (no audio pop)
   - TTS: cancel generation, flush queue
   - Brain: cancel LLM task, save partial response
3. VAD emits `PipelineEvent(type="flush", direction=DOWNSTREAM)` to drain all queues
4. `InterruptLatencyObserver` tracks time from VAD trigger to full silence

### Language Support

- Automatic language detection from speech
- Context-aware TTS voice selection
- Bilingual system prompts
- Seamless Chinese/English switching

## Directory Structure

```
src/tank_backend/
├── api/                          # FastAPI routes
│   ├── server.py                 # Health, metrics endpoints
│   ├── router.py                 # WebSocket handler
│   ├── approvals.py              # Approval REST API
│   └── metrics.py                # Metrics endpoint
├── agents/                       # Agent orchestration (Layer 2)
│   ├── base.py                   # Agent ABC, AgentState, AgentOutput
│   ├── graph.py                  # AgentGraph orchestrator
│   ├── approval.py               # ApprovalManager + ApprovalPolicy
│   ├── factory.py                # Agent factory
│   └── chat_agent.py             # Single conversational agent (all tools)
├── pipeline/                     # Pipeline architecture (Layer 1)
│   ├── processor.py              # Processor ABC, AudioCaps, FlowReturn
│   ├── event.py                  # PipelineEvent, EventDirection
│   ├── queue.py                  # ThreadedQueue (bounded, backpressure)
│   ├── fan_out_queue.py          # FanOutQueue (parallel branches)
│   ├── bus.py                    # Bus, BusMessage (pub/sub)
│   ├── builder.py                # PipelineBuilder, Pipeline
│   ├── health.py                 # HealthAggregator, component health types
│   ├── processors/               # Concrete processors
│   │   ├── vad.py                # Voice Activity Detection
│   │   ├── asr.py                # Speech-to-text
│   │   ├── speaker_id.py         # Speaker identification
│   │   ├── asr_speaker_merger.py # Combine ASR + speaker
│   │   ├── brain.py              # LLM conversation (bridges to Layer 2)
│   │   ├── echo_guard.py         # Self-echo detection (Layer 2)
│   │   ├── tts.py                # Text-to-speech + QoS
│   │   └── playback.py           # Audio output
│   └── observers/                # Bus subscribers
│       ├── latency.py            # Per-stage timing
│       ├── interrupt_latency.py  # Interrupt responsiveness
│       ├── turn_tracking.py      # Conversation turn metrics
│       ├── metrics_collector.py  # Aggregated metrics
│       ├── health_monitor.py     # Health checks
│       └── alerting.py           # Anomaly detection + alerts
├── llm/                          # LLM transport (Layer 3)
│   └── llm.py                    # AsyncOpenAI wrapper, retry, token counting
├── observability/                # LLM tracing
│   ├── langfuse_client.py        # Langfuse initialization
│   └── trace.py                  # Trace ID generation
├── persistence/                  # Conversation persistence
│   └── checkpointer.py           # SQLite checkpointer
├── tools/                        # Tool system
├── plugin/                       # Plugin system
├── config/                       # Settings
├── audio/                        # Legacy audio components
│   ├── input/                    # ASR engines, segmenter
│   └── output/                   # TTS engines, playback
└── core/                         # Core types and events
```

## API Protocol

### WebSocket Message Types

**Client → Server**:
```json
{"type": "audio", "data": "<base64>", "sample_rate": 16000}
{"type": "input", "content": "user message"}
{"type": "interrupt"}
```

**Server → Client**:
```json
{"type": "audio", "data": "<base64>"}
{"type": "text", "content": "...", "msg_id": "...", "metadata": {...}}
{"type": "signal", "content": "ready|processing_started|processing_ended"}
{"type": "transcript", "content": "...", "is_user": true}
{"type": "update", "metadata": {"update_type": "THOUGHT|TOOL_CALL|TOOL_RESULT|APPROVAL_NEEDED"}}
{"type": "error", "message": "error description"}
```

### REST API

```
GET  /health                           # Simple or detailed health check
GET  /api/metrics                      # Aggregated metrics
GET  /api/metrics/{session_id}         # Per-session metrics
GET  /api/approvals?session_id=...     # List pending approvals
POST /api/approvals/{id}/respond       # Approve/reject tool execution
GET  /api/speakers                     # List enrolled speakers
POST /api/speakers/enroll              # Enroll new speaker
DELETE /api/speakers/{id}              # Delete speaker
```

## Deployment

### Development
```bash
uv run tank-backend --reload
```

### Production
```bash
uv run uvicorn tank_backend.main:app --host 0.0.0.0 --port 8000
```

## Performance Considerations

- Pipeline uses real threads (via `ThreadedQueue`) for CPU-bound work — no hidden `asyncio.to_thread()`
- Bounded queues provide backpressure — prevents unbounded memory growth
- TTS streaming with QoS feedback — graceful degradation under load
- Token counting via `tiktoken` — prevents context window overflow
- Auto-summarization — keeps conversation history within token budget
- Langfuse tracing is async/non-blocking — no voice latency impact
- Echo guard is platform-independent — protects all clients equally

## Security Considerations

- API key validation
- Tool approval gates for sensitive operations (code execution, web scraping)
- Input sanitization for tool execution
- Docker sandbox isolation for code execution
- CORS configuration for web clients
- Approval timeout (120s) prevents stuck requests
