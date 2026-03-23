# Pipeline Architecture Roadmap

> **Status: ✅ ALL PHASES COMPLETED** — All 9 phases (0–8) have been implemented. The three-layer architecture (audio pipeline, agent orchestration, LLM transport) is fully operational with health monitoring, alerting, approval gates, echo guard, conversation persistence, and Langfuse observability. See [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md) for the current architecture documentation.

## Executive Summary

After researching Pipecat (frame-based async pipeline framework), GStreamer (the gold standard for media pipelines), LangGraph (stateful agent orchestration), LLM observability platforms, and LLM framework alternatives (LangChain, LlamaIndex, etc.), the conclusion is: **evolve Tank into a three-layer architecture — audio pipeline (GStreamer-inspired), agent orchestration (LangGraph-inspired but custom-built), and observability (Langfuse) — keeping the direct OpenAI SDK as the LLM transport layer.**

Tank's multi-threaded, queue-based design is fundamentally sound for the audio pipeline. But the Brain layer needs to evolve beyond a single-LLM processor into a proper agent orchestration layer that supports multiple specialized agents, human-in-the-loop approval, conversation persistence, and stateful workflows. Rather than adopting LangGraph wholesale (its batched streaming and checkpoint-per-superstep overhead conflict with voice latency requirements), we borrow its key ideas — state graphs, conditional routing, checkpointing — and implement them within our pipeline architecture.

### Functionality Continuity Map

Two critical real-time features — speech interruption and audio noise cancellation — must be tracked across the migration. This table shows when each feature breaks, restores, and improves:

```
Phase    │ Speech Interruption              │ ANC (Noise/Echo Cancellation)
─────────┼──────────────────────────────────┼──────────────────────────────────
Phase 0  │ ✅ Unchanged (old threading.Event)│ ❌ Not implemented (current state)
Phase 1  │ ✅ Unchanged (wrappers delegate)  │ ❌ Not implemented
Phase 2  │ ⚠️  RISK WINDOW during 2.1-2.2   │ ❌ Not implemented
         │ ✅ Restored at 2.3 (event-based)  │
         │    Better: ordered propagation,  │
         │    graceful fade-out, partial    │
         │    response saved, <20ms latency │
Phase 3  │ ✅ Working                        │ ✅ NEW: Defense-in-depth echo guard
         │                                  │    Layer 1: VAD threshold (backend)
         │                                  │    Layer 2: Self-echo text detection
         │                                  │    No backend signal-level AEC/ANC
Phase 4  │ ✅ Working                        │ ✅ Working
Phase 5  │ ✅ Working + observable           │ ✅ Working + observable
         │    (InterruptLatencyObserver)     │    (echo discard metrics on Bus)
Phase 6  │ ✅ Working — cancel token         │ ✅ Working (Layer 1 independent)
         │    propagates to AgentGraph      │
Phase 7  │ ✅ Working — interrupt cancels    │ ✅ Working
         │    pending approval requests     │
Phase 8  │ ✅ Production-grade              │ ✅ Production-grade
```

**Interruption downtime: 0 seconds** — achieved by implementing Phase 2.1, 2.2, 2.3 behind a version flag and activating all three atomically. See "Minimizing Downtime" in Part 5.

**Echo guard has no downtime risk** — VAD threshold switching and self-echo text detection are backend-only, platform-independent, and fail-open (if detection fails, audio passes through as before). Disabled via config.

---

## Part 1: Research Findings

### Three Architectures Compared

#### GStreamer (Gold Standard — 25+ years)
- **Model**: Multi-threaded, queue-based pipeline with typed elements
- **Key insight**: Queue elements create thread boundaries — pipeline topology determines threading
- **Strengths**: Caps negotiation, FlowReturn backpressure, bidirectional events, pad probes for safe dynamic modification, clock synchronization, plugin registry with autoplugging
- **Weakness**: Massive complexity (C/GObject), overkill for voice-only pipelines

#### Pipecat (~2 years, startup-stage)
- **Model**: Single async event loop, frame-push pipeline
- **Key insight**: Everything is a `FrameProcessor` — universal composability
- **Strengths**: 50+ AI service integrations, clean Python API, observer pattern for metrics, context summarization
- **Weaknesses**: CPU-bound work still uses threads (hidden behind `asyncio.to_thread()`), frame object overhead, linear pipeline only (no fan-out/fan-in), interruption is frame-based (slower than event-based)

#### Tank (Current)
- **Model**: Multi-threaded workers with queue-based communication
- **Key insight**: Specialized workers (Brain, ASR, TTS) run in parallel threads, coordinated by Assistant
- **Strengths**: True parallelism for CPU-bound work, plugin system with registry, streaming perception, low-latency audio pipeline, clear separation of concerns
- **Weaknesses**: Hardcoded thread topology, unbounded queues (no backpressure), single `threading.Event` for interruption (crude), no composability (adding a stage requires queue plumbing), no observability beyond logging

#### LangGraph (Stateful Agent Orchestration)
- **Model**: Pregel-inspired state graph — nodes are computation steps, edges are control flow, shared typed state flows through the graph
- **Key insight**: Agent workflows are cyclic state machines (think → act → observe → think), not linear pipelines
- **Strengths**: Stateful multi-agent coordination, human-in-the-loop via `Interrupt`, checkpointing/persistence across sessions, conditional routing, time-travel debugging, explicit control flow for tool calling
- **Weaknesses**: Streaming is batched (not true token-by-token — dealbreaker for voice), checkpoint-per-superstep adds I/O overhead, pulls in `langchain-core` dependency, assumes it owns the execution loop

### What Each Does Best

| Capability | Best Implementation | Why |
|------------|-------------------|-----|
| Threading model | GStreamer | Queue = thread boundary, topology-driven |
| Backpressure | GStreamer | FlowReturn propagates upstream |
| Composability | Pipecat | Universal FrameProcessor abstraction |
| Control flow | GStreamer | Bidirectional events (upstream + downstream) |
| Dynamic modification | GStreamer | Pad probes — race-condition-free |
| Service ecosystem | Pipecat | 50+ pre-built AI integrations |
| Plugin system | Tank | Registry + config-based, superior to both |
| Streaming ASR | Tank | StreamingPerception is more sophisticated |
| Observability | Pipecat | Observer pattern for latency/turn tracking |
| Context management | Pipecat | Auto-summarization when history is too long |
| Format safety | GStreamer | Caps negotiation catches mismatches at link time |
| CPU parallelism | Tank/GStreamer | Real threads, not hidden behind async |
| Multi-agent orchestration | LangGraph | State graph with conditional routing, shared state |
| Human-in-the-loop | LangGraph | Interrupt + checkpoint + resume pattern |
| Conversation persistence | LangGraph | Checkpointing to database, session resumption |
| Agent workflow control | LangGraph | Explicit cycles, branching, conditional edges |

### Why NOT Replace with Pipecat

1. Tank's multi-threaded architecture is fundamentally sound — Pipecat's async model still uses threads for CPU-bound work, just hides them
2. Tank's plugin system is superior — Pipecat hardcodes service integrations
3. Tank's streaming pipeline is more optimized — Pipecat's frame overhead adds latency
4. Migration cost is high — full rewrite with new bugs, no architectural gain
5. Pipecat's linear pipeline can't do fan-out/fan-in (e.g., parallel ASR + speaker ID)

### Why NOT Adopt GStreamer Directly

1. Massive complexity for a voice-only pipeline (no video sync needed)
2. C/GObject learning curve — Python bindings are clunky
3. No AI/LLM service integrations
4. No conversation context management
5. Overkill: we don't need seek, codec negotiation, buffer pools, or the full state machine

### Why NOT Replace LLM Layer with LangChain

Tank's LLM integration is ~370 lines across `llm.py` + `manager.py` using the raw `AsyncOpenAI` SDK. It already handles streaming, iterative tool calling, and multi-provider support (via OpenRouter). LangChain would add:

1. **Massive dependency bloat** — 50+ transitive deps vs our single `openai` package
2. **Abstraction tax on streaming** — LangChain wraps every token in `AIMessageChunk → ToolCallChunk → AgentAction → AgentStep`, adding latency in the voice-critical hot path
3. **Breaking changes** — LangChain's API has changed significantly across v0.1 → v0.2 → v0.3 (LCEL paradigm shift)
4. **Impedance mismatch** — LangChain assumes it owns the execution loop; our `Brain` owns it (interrupt checking, UI posting, history management)
5. **Tool calling already solved** — `ToolManager.get_openai_tools()` + iterative loop in `chat_stream()` does exactly what LangChain's `AgentExecutor` does, in 1/10th the code

What we actually need (context summarization, token counting, retry logic) is ~60 lines of utility code, not a framework.

### Why NOT Adopt LangGraph Wholesale

LangGraph solves real problems we'll need: multi-agent coordination, human-in-the-loop, conversation persistence. But adopting it as-is conflicts with voice assistant requirements:

1. **Batched streaming** — LangGraph's event stream delivers tokens in chunks, not individually. For a voice assistant where every token must hit TTS immediately, this adds perceptible latency
2. **Checkpoint-per-superstep overhead** — LangGraph writes to database at every node execution. For rapid-fire voice turns, this is unnecessary I/O
3. **Dependency weight** — Pulls in `langchain-core` + checkpoint drivers + pydantic v2 + tenacity + jsonpatch
4. **Execution loop ownership** — LangGraph assumes it owns the loop; our pipeline's `BrainProcessor` needs to own it (for interrupt checking, Bus posting, streaming to TTS)
5. **Overkill for current state** — Single-agent voice chat doesn't need a state graph framework

**Strategy: Borrow LangGraph's ideas, implement them within our architecture.**

What to borrow:
- **State graph concept** — Agent workflows as nodes + conditional edges + shared state
- **Interrupt + checkpoint + resume** — For human-in-the-loop approval before sensitive tool calls
- **Conversation persistence** — Checkpoint conversation state to SQLite/PostgreSQL for session resumption
- **Conditional routing** — Route user intent to specialized agents (math agent, search agent, task agent)
- **Multi-agent shared state** — Agents read/write to a common state object with merge semantics

### LLM Observability Landscape

Researched 6 major platforms for LLM-specific observability:

| Tool | Architecture | Self-Hosted | License | Dashboard | Latency Overhead |
|------|-------------|-------------|---------|-----------|-----------------|
| **Langfuse** | SDK (OpenAI wrapper) | Yes (Docker) | MIT | Rich (traces, cost, prompts, evals) | Minimal (async) |
| **Helicone** | Proxy (Cloudflare edge) | Yes | Apache 2.0 | Good (cost, latency, errors) | ~8ms P50 |
| **Phoenix (Arize)** | OpenTelemetry | Yes | Open-source | Rich (traces, evals, embeddings) | Minimal |
| **OpenLIT** | OpenTelemetry | Yes | Apache 2.0 | Rich (custom dashboards, GPU) | Minimal |
| **Traceloop/OpenLLMetry** | OpenTelemetry | Yes | Apache 2.0 | Backend-dependent | Minimal |
| **Lunary** | SDK (async) | Yes | Open-source | Good (cost, prompts, A/B testing) | Minimal |

**Recommendation: Langfuse** — best fit for Tank because:
- Drop-in OpenAI wrapper (`from langfuse.openai import openai`) — minimal code change to `llm.py`
- MIT license, fully self-hostable via Docker
- Async/non-blocking — critical for voice latency
- Rich dashboard: token usage, cost tracking, conversation traces, latency breakdown, prompt versioning
- Works with any OpenAI-compatible API (our OpenRouter setup)
- ClickHouse backend proven at scale

**Alternative: OpenTelemetry path** (Phoenix/OpenLIT/Traceloop) — better if we want vendor-agnostic telemetry that also covers pipeline metrics. More setup, but follows the emerging GenAI semantic conventions standard.

**Two-layer observability strategy:**
1. **Pipeline layer** — Internal Bus + observers (latency, turn tracking, queue depth) → exposed via `/api/metrics`
2. **LLM layer** — Langfuse for deep LLM tracing (token usage, cost, prompts, tool calls, conversation history)

These complement each other: the Bus handles real-time pipeline health; Langfuse handles LLM analytics and debugging.

---

## Part 2: Improvement Inventory

### From GStreamer — Borrow These Patterns

| # | Pattern | Current Tank Gap | Impact |
|---|---------|-----------------|--------|
| G1 | Queue-as-thread-boundary | Hardcoded thread-per-component | High |
| G2 | FlowReturn backpressure | Unbounded queues | High |
| G3 | Bidirectional events | Single `threading.Event` | Medium-High |
| G4 | Message Bus | `ui_queue` is ad-hoc | Medium |
| G5 | Caps-like format declaration | Manual sample rate matching | Medium |
| G6 | Pad probes (safe dynamic swap) | Stop/reconfigure/restart | Low-Medium |

### From Pipecat — Borrow These Patterns

| # | Pattern | Current Tank Gap | Impact |
|---|---------|-----------------|--------|
| P1 | Universal Processor abstraction | Specialized classes, no composability | High |
| P2 | Observer pattern for metrics | Logging only | Medium |
| P3 | Context summarization | Conversation history grows unbounded | Medium |
| P4 | Smart turn detection | Silero VAD + silence timeout only | Medium |
| P5 | Audio filters (noise cancellation) | No pre-processing before ASR | Low-Medium |

### Tank-Native Improvements

| # | Improvement | Current Gap | Impact |
|---|------------|-------------|--------|
| T1 | Config-driven pipeline topology | Hardcoded in `assistant.py` | High |
| T2 | Graceful degradation on overload | No QoS feedback | Medium |
| T3 | Pipeline health monitoring | No metrics collection | Medium |
| T4 | Hot-reload of processors | Requires full restart | Low |

### Speech Interruption Improvements

| # | Improvement | Current Gap | Impact |
|---|------------|-------------|--------|
| I1 | Bidirectional event-based interruption | Single `threading.Event` polled independently by each worker | High |
| I2 | Ordered propagation (Playback → TTS → Brain) | No ordering guarantee — workers react at their own poll rate | High |
| I3 | Queue flush at thread boundaries | Manual `queue.queue.clear()` with mutex — racy, misses `audio_chunk_queue` | High |
| I4 | Graceful playback fade-out on interrupt | `CallbackAbort` causes hard stop with audible click/pop | Medium |
| I5 | Partial response preservation | Interrupted LLM output is lost — not saved to conversation history | Medium |
| I6 | Interrupt latency observability | No measurement of time from VAD detection to full silence | Medium |

### Audio Noise Cancellation (ANC) Improvements

| # | Improvement | Current Gap | Impact |
|---|------------|-------------|--------|
| A1 | Noise filter processor (RNNoise/noisereduce) | No audio pre-processing before VAD/ASR | Medium-High |
| A2 | Acoustic Echo Cancellation (AEC) | No self-speech suppression — assistant's own voice triggers VAD/ASR when using speakers | High |
| A3 | AEC reference signal from playback | No mechanism to feed TTS output back as AEC reference | High |
| A4 | Configurable filter chain | No way to insert/reorder audio filters without code changes | Medium |

### LLM Layer Improvements (Keep Raw SDK, Add Utilities)

| # | Improvement | Current Gap | Impact |
|---|------------|-------------|--------|
| L1 | Langfuse integration for LLM tracing | No LLM observability (logging only) | High |
| L2 | Context summarization | History grows unbounded, truncated by message count not tokens | High |
| L3 | Token counting (tiktoken) | No token awareness, truncation is message-count-based | Medium |
| L4 | Retry with exponential backoff | No retry on transient LLM failures | Medium |
| L5 | Bounded tool iterations | `while True` loop has no max iteration guard | Medium |
| L6 | Multiple LLM profiles per task | Single model for all tasks (conversation, summarization, tool use) | Low-Medium |

### Observability & Dashboard Improvements

| # | Improvement | Current Gap | Impact |
|---|------------|-------------|--------|
| O1 | Langfuse self-hosted deployment | No LLM analytics dashboard | High |
| O2 | Pipeline metrics via Bus → `/api/metrics` | No pipeline metrics endpoint | High |
| O3 | Conversation history viewer (Langfuse traces) | No way to review past conversations | Medium |
| O4 | Token usage & cost dashboard (Langfuse) | No cost tracking | Medium |
| O5 | Per-session trace linking (pipeline ↔ LLM) | Pipeline and LLM are unlinked | Medium |
| O6 | Alerting on anomalies (latency spikes, error rates) | No alerting | Low-Medium |

---

## Part 3: New Architecture Design

### Design Principles

1. **Queue = Thread Boundary** (from GStreamer): Thread topology is determined by where you place queues, not by hardcoding threads per component
2. **Universal Processor** (from Pipecat): Every pipeline stage implements the same interface — composable, swappable, testable
3. **Bidirectional Events** (from GStreamer): Data flows downstream, control events flow both directions
4. **Backpressure by Default** (from GStreamer): Bounded queues with FlowReturn propagation
5. **Bus for Observability** (from GStreamer + Pipecat): Decoupled message bus for metrics, UI updates, and diagnostics
6. **Plugin-Driven** (Tank native): Processors are discovered and instantiated via the existing plugin registry
7. **Three-Layer Separation**: Audio pipeline (real-time, latency-critical) → Agent orchestration (stateful, multi-agent) → LLM transport (raw SDK, streaming)
8. **Agent Graph for Brain** (from LangGraph): The Brain is not a single LLM call — it's a state graph of agents with conditional routing, shared state, and human-in-the-loop checkpoints

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Tank Architecture                                 │
│                                                                          │
│  Layer 1: Audio Pipeline (GStreamer-inspired)                            │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  Audio In → [VAD] → [Q] → [ASR] → [Speaker] ──┐                  │  │
│  │                                                  │                  │  │
│  │  Audio Out ← [Playback] ← [Q] ← [TTS] ← ──────┤                  │  │
│  │                                                  │                  │  │
│  │  Concerns: real-time, latency-critical,          │                  │  │
│  │  multi-threaded, backpressure, interruption       │                  │  │
│  └──────────────────────────────────────────────────┼──────────────┘  │
│                                                      │                  │
│  Layer 2: Agent Orchestration (LangGraph-inspired)   │                  │
│  ┌──────────────────────────────────────────────────┼──────────────┐  │
│  │                                                  ▼                │  │
│  │  ┌─────────┐    ┌──────────────┐    ┌─────────────────────┐     │  │
│  │  │ Router  │───→│ Agent Graph  │───→│ Response Assembler  │     │  │
│  │  │ (intent │    │              │    │ (streams tokens to  │     │  │
│  │  │  detect)│    │  ┌────────┐  │    │  TTS immediately)   │     │  │
│  │  └─────────┘    │  │ Chat   │  │    └─────────────────────┘     │  │
│  │                  │  │ Agent  │  │                                 │  │
│  │  State:          │  ├────────┤  │    Checkpoints:                │  │
│  │  ├─ messages     │  │ Search │  │    ├─ After each turn          │  │
│  │  ├─ tool_results │  │ Agent  │  │    ├─ Before sensitive tools   │  │
│  │  ├─ agent_id     │  ├────────┤  │    └─ On session end           │  │
│  │  ├─ pending_     │  │ Task   │  │                                 │  │
│  │  │  approval     │  │ Agent  │  │    Human-in-the-loop:          │  │
│  │  └─ metadata     │  ├────────┤  │    ├─ Tool approval gate       │  │
│  │                  │  │ Code   │  │    ├─ Content review gate      │  │
│  │                  │  │ Agent  │  │    └─ Escalation gate          │  │
│  │                  │  └────────┘  │                                 │  │
│  │                  └──────────────┘                                 │  │
│  │                                                                   │  │
│  │  Concerns: stateful workflows, multi-agent routing,               │  │
│  │  human approval, conversation persistence, tool orchestration     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  Layer 3: LLM Transport (Raw SDK)                                        │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  AsyncOpenAI (Langfuse-wrapped) → any OpenAI-compatible API       │  │
│  │  Concerns: streaming, token counting, retry, cost tracking        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  Cross-cutting: Message Bus + Langfuse Observability                     │
└─────────────────────────────────────────────────────────────────────────┘
```

**Why three layers matter:**

- **Layer 1 (Audio Pipeline)** has hard real-time constraints — 20ms audio frames, interrupt within 10ms, backpressure on queues. It must never block on agent logic.
- **Layer 2 (Agent Orchestration)** is where intelligence lives — routing to the right agent, managing conversation state, handling tool approval. It can tolerate 100ms+ latency for routing decisions, but must stream LLM tokens to TTS immediately (not batch them).
- **Layer 3 (LLM Transport)** is a thin wrapper — raw `AsyncOpenAI` with retry, token counting, and Langfuse tracing. No framework, no abstraction tax.

The critical interface is between Layer 1 and Layer 2: the `BrainProcessor` sits in the audio pipeline but delegates to the agent graph. It must stream tokens from the agent graph to TTS without buffering.

### Core Abstractions

```
┌─────────────────────────────────────────────────────────────────┐
│                        Pipeline                                  │
│                                                                  │
│  ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐ │
│  │Processor │───→│  Threaded │───→│Processor │───→│Processor │ │
│  │  (VAD)   │    │   Queue   │    │  (ASR)   │    │(Speaker) │ │
│  └──────────┘    └───────────┘    └──────────┘    └──────────┘ │
│       │               ↑ ↓              │               │        │
│       │          [thread boundary]     │               │        │
│       │                                │               │        │
│       ├── handle_event() ←─────────────┤               │        │
│       │   (upstream: interrupt)        │               │        │
│       │                                │               │        │
│       └── process() ──────────────────→┘               │        │
│           (downstream: data)                           │        │
│                                                        │        │
│  ┌─────────────────────────────────────────────────────┘        │
│  │                                                              │
│  │  ┌───────────┐    ┌──────────┐    ┌───────────┐             │
│  └─→│  Threaded │───→│Processor │───→│  Threaded │──→ Output   │
│     │   Queue   │    │  (Brain) │    │   Queue   │             │
│     └───────────┘    └──────────┘    └───────────┘             │
│          ↑ ↓              │               ↑ ↓                   │
│     [thread boundary]     │          [thread boundary]          │
│                           │                                     │
│                           ↓                                     │
│                    ┌──────────┐    ┌──────────┐                 │
│                    │Processor │───→│Processor │──→ Output       │
│                    │  (TTS)   │    │(Playback)│                 │
│                    └──────────┘    └──────────┘                 │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     Message Bus                           │   │
│  │  (metrics, UI updates, errors, state changes)             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Processor Interface

```python
class FlowReturn(Enum):
    OK = "ok"
    EOS = "eos"
    FLUSHING = "flushing"
    ERROR = "error"

@dataclass
class AudioCaps:
    """Format declaration for audio processors."""
    sample_rate: int
    channels: int = 1
    dtype: str = "float32"

@dataclass
class Event:
    """Bidirectional control event."""
    type: str          # "interrupt", "eos", "flush", "qos"
    direction: str     # "upstream" or "downstream"
    source: str        # processor name that originated the event
    metadata: dict = field(default_factory=dict)

class Processor(ABC):
    """Universal processor — the building block of the pipeline."""

    name: str
    input_caps: AudioCaps | None = None   # None = non-audio input
    output_caps: AudioCaps | None = None  # None = non-audio output

    @abstractmethod
    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        """Process input, yield (flow_return, output) pairs."""
        pass

    def handle_event(self, event: Event) -> bool:
        """Handle control event. Return True if consumed."""
        return False  # default: propagate

    async def start(self):
        """Called when pipeline starts."""
        pass

    async def stop(self):
        """Called when pipeline stops."""
        pass
```

### ThreadedQueue (Thread Boundary)

```python
class ThreadedQueue:
    """A bounded queue that spawns a consumer thread.
    Inserting a ThreadedQueue between two processors creates a thread boundary.
    maxsize provides backpressure — push() blocks when full.
    """

    def __init__(self, name: str, maxsize: int = 10):
        self.name = name
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._consumer_thread: threading.Thread | None = None
        self._downstream: Processor | None = None
        self._stop = threading.Event()

    def link(self, downstream: Processor):
        self._downstream = downstream

    def push(self, item: Any) -> FlowReturn:
        """Push item. Blocks if full (backpressure). Returns FlowReturn."""
        if self._stop.is_set():
            return FlowReturn.FLUSHING
        try:
            self._queue.put(item, timeout=0.1)
            return FlowReturn.OK
        except queue.Full:
            return FlowReturn.OK  # retry on next call

    def start(self):
        self._consumer_thread = threading.Thread(
            target=self._run, name=f"tq-{self.name}", daemon=True
        )
        self._consumer_thread.start()

    def _run(self):
        loop = asyncio.new_event_loop()
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=0.1)
                async for flow, output in self._downstream.process(item):
                    if flow != FlowReturn.OK:
                        break
            except queue.Empty:
                continue
        loop.close()

    def flush(self):
        """Drain queue on interrupt."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
```

### Message Bus

```python
class Message:
    """Bus message — posted by any processor, consumed by subscribers."""
    type: str          # "metric", "ui_update", "error", "state_change"
    source: str        # processor name
    payload: Any
    timestamp: float

class Bus:
    """Thread-safe message bus for decoupled communication."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._queue: queue.Queue = queue.Queue()

    def post(self, message: Message):
        """Thread-safe: called from any streaming thread."""
        self._queue.put(message)

    def subscribe(self, msg_type: str, handler: Callable):
        self._subscribers[msg_type].append(handler)

    def poll(self):
        """Called from application thread to dispatch messages."""
        while not self._queue.empty():
            msg = self._queue.get_nowait()
            for handler in self._subscribers.get(msg.type, []):
                handler(msg)
            for handler in self._subscribers.get("*", []):
                handler(msg)
```

### Observer Protocol

```python
class PipelineObserver(Protocol):
    """Observer for pipeline metrics and events."""

    def on_processor_start(self, name: str, timestamp: float): ...
    def on_processor_end(self, name: str, timestamp: float, duration_ms: float): ...
    def on_latency(self, stage: str, latency_ms: float): ...
    def on_turn_start(self, turn_id: str, timestamp: float): ...
    def on_turn_end(self, turn_id: str, timestamp: float): ...
    def on_error(self, source: str, error: Exception): ...

class LatencyObserver:
    """Tracks end-to-end and per-stage latency."""

    def __init__(self, bus: Bus):
        self.bus = bus
        self._stage_starts: dict[str, float] = {}

    def on_processor_start(self, name: str, timestamp: float):
        self._stage_starts[name] = timestamp

    def on_processor_end(self, name: str, timestamp: float, duration_ms: float):
        self.bus.post(Message(
            type="metric",
            source=name,
            payload={"stage": name, "duration_ms": duration_ms},
            timestamp=timestamp,
        ))
```

### Pipeline Builder (Config-Driven)

```python
# config.yaml — pipeline topology
pipeline:
  stages:
    - name: vad
      processor: vad:silero
      config:
        threshold: 0.5
        min_speech_ms: 250

    - name: asr
      processor: asr-sherpa:asr
      thread_boundary: true        # ← inserts ThreadedQueue before this stage
      queue_size: 10
      config:
        model: vosk-model-small-cn

    - name: speaker_id
      processor: speaker-sherpa:speaker
      config:
        threshold: 0.6

    - name: brain
      processor: core:brain
      thread_boundary: true
      queue_size: 5
      config:
        llm_profile: default
        max_history_tokens: 8000
        summarize_at: 6000         # ← auto-summarize when history exceeds this

    - name: tts
      processor: tts-edge:tts
      thread_boundary: true
      queue_size: 5
      config:
        voice_en: en-US-JennyNeural
        voice_zh: zh-CN-XiaoxiaoNeural

    - name: playback
      processor: core:playback
      config:
        fade_ms: 10

  bus:
    observers:
      - latency
      - turn_tracking
```

### Context Summarization (from Pipecat)

```python
class BrainProcessor(Processor):
    """LLM conversation processor with auto-summarization."""

    async def _maybe_summarize(self):
        token_count = self._count_tokens(self.history)
        if token_count > self.config.summarize_at:
            # Keep system prompt + last N messages, summarize the rest
            to_summarize = self.history[1:-5]
            summary = await self.llm.summarize(to_summarize)
            self.history = [
                self.history[0],                    # system prompt
                {"role": "system", "content": f"Previous conversation summary: {summary}"},
                *self.history[-5:],                  # recent messages
            ]
            self.bus.post(Message(
                type="metric",
                source="brain",
                payload={"event": "context_summarized", "old_tokens": token_count,
                         "new_tokens": self._count_tokens(self.history)},
                timestamp=time.time(),
            ))
```

### Agent Graph (from LangGraph — custom implementation)

The Brain evolves from a single LLM call into a state graph of specialized agents.

```python
# --- Agent State ---

@dataclass
class AgentState:
    """Shared state flowing through the agent graph."""
    messages: list[dict]                    # conversation history
    current_agent: str = "router"           # which agent is active
    tool_results: list[dict] = field(default_factory=list)
    pending_approval: ApprovalRequest | None = None  # human-in-the-loop
    metadata: dict = field(default_factory=dict)
    session_id: str = ""
    trace_id: str = ""

@dataclass
class ApprovalRequest:
    """Pending human approval for a sensitive action."""
    action: str              # "execute_code", "send_email", "delete_file"
    description: str         # human-readable description
    tool_name: str
    tool_args: dict
    agent: str               # which agent requested approval
    checkpoint_id: str       # for resuming after approval

# --- Agent Base ---

class Agent(ABC):
    """A specialized agent — one node in the agent graph."""

    name: str
    system_prompt: str
    tools: list[BaseTool]
    llm_profile: str = "conversation"  # which LLM profile to use

    @abstractmethod
    async def run(self, state: AgentState, llm: LLM) -> AsyncIterator[AgentOutput]:
        """Process state, yield streaming output. May modify state."""
        pass

    def should_handoff(self, state: AgentState) -> str | None:
        """Return agent name to hand off to, or None to continue."""
        return None

@dataclass
class AgentOutput:
    """Streaming output from an agent."""
    type: str          # "token", "tool_call", "tool_result", "handoff", "approval_needed"
    content: str
    metadata: dict = field(default_factory=dict)

# --- Agent Graph ---

class AgentGraph:
    """State graph of agents with conditional routing.
    Inspired by LangGraph but with real-time streaming (no batching).
    """

    def __init__(self, agents: dict[str, Agent], router: Router, checkpointer: Checkpointer):
        self.agents = agents
        self.router = router
        self.checkpointer = checkpointer

    async def run(self, state: AgentState) -> AsyncIterator[AgentOutput]:
        """Execute the agent graph, streaming tokens immediately."""
        max_iterations = 10

        for _ in range(max_iterations):
            # 1. Route to the right agent
            agent_name = state.current_agent
            agent = self.agents[agent_name]

            # 2. Run agent, stream output immediately (no batching!)
            async for output in agent.run(state, self.llm):
                if output.type == "approval_needed":
                    # Human-in-the-loop: checkpoint and pause
                    state.pending_approval = ApprovalRequest(
                        action=output.metadata["action"],
                        description=output.content,
                        tool_name=output.metadata["tool_name"],
                        tool_args=output.metadata["tool_args"],
                        agent=agent_name,
                        checkpoint_id=await self.checkpointer.save(state),
                    )
                    yield output
                    return  # Pause execution, wait for human

                if output.type == "handoff":
                    # Switch to another agent
                    state.current_agent = output.metadata["target_agent"]
                    break

                yield output  # Stream token/tool_result to caller immediately
            else:
                # Agent finished without handoff — done
                break

        # Checkpoint at end of turn
        await self.checkpointer.save(state)

    async def resume_after_approval(self, checkpoint_id: str, approved: bool) -> AsyncIterator[AgentOutput]:
        """Resume execution after human approves/rejects."""
        state = await self.checkpointer.load(checkpoint_id)
        approval = state.pending_approval
        state.pending_approval = None

        if approved:
            # Execute the approved tool
            result = await self.tool_manager.execute_tool(approval.tool_name, **approval.tool_args)
            state.tool_results.append({"tool": approval.tool_name, "result": result})
            state.current_agent = approval.agent  # return to requesting agent
            yield AgentOutput(type="tool_result", content=str(result))
        else:
            # Tell the agent the action was rejected
            state.messages.append({"role": "system", "content": f"User rejected action: {approval.action}"})
            state.current_agent = approval.agent

        # Continue the graph
        async for output in self.run(state):
            yield output

# --- Router ---

class Router:
    """Routes user input to the appropriate agent based on intent."""

    async def route(self, state: AgentState) -> str:
        """Determine which agent should handle this input.
        Can use a fast LLM call for intent classification,
        or simple keyword matching for common patterns.
        """
        last_message = state.messages[-1]["content"]

        # Fast path: keyword matching
        if any(kw in last_message for kw in ["搜索", "search", "查找", "find"]):
            return "search_agent"
        if any(kw in last_message for kw in ["计算", "calculate", "多少"]):
            return "math_agent"
        if any(kw in last_message for kw in ["任务", "task", "提醒", "remind"]):
            return "task_agent"

        # Slow path: LLM-based intent classification (use fast model)
        return "chat_agent"  # default

# --- Checkpointer ---

class Checkpointer:
    """Persists agent state for session resumption and human-in-the-loop."""

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self._init_db()

    async def save(self, state: AgentState) -> str:
        checkpoint_id = f"cp_{uuid.uuid4().hex[:12]}"
        self.conn.execute(
            "INSERT INTO checkpoints (id, session_id, state, created_at) VALUES (?, ?, ?, ?)",
            (checkpoint_id, state.session_id, json.dumps(asdict(state)), time.time()),
        )
        self.conn.commit()
        return checkpoint_id

    async def load(self, checkpoint_id: str) -> AgentState:
        row = self.conn.execute(
            "SELECT state FROM checkpoints WHERE id = ?", (checkpoint_id,)
        ).fetchone()
        return AgentState(**json.loads(row[0]))

    async def load_session(self, session_id: str) -> AgentState | None:
        """Resume a previous conversation session."""
        row = self.conn.execute(
            "SELECT state FROM checkpoints WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return AgentState(**json.loads(row[0])) if row else None
```

**Key difference from LangGraph**: Tokens stream immediately via `async for output in agent.run()`. No batching, no superstep synchronization barriers. The agent graph is async-generator-based, so every token flows to TTS the moment it's produced.

### BrainProcessor: Bridge Between Pipeline and Agent Graph

```python
class BrainProcessor(Processor):
    """Pipeline processor that delegates to the agent graph.
    Sits in Layer 1 (audio pipeline) but calls into Layer 2 (agent orchestration).
    Streams tokens to TTS immediately — no buffering.
    """

    def __init__(self, agent_graph: AgentGraph, bus: Bus):
        self.agent_graph = agent_graph
        self.bus = bus

    async def process(self, event: BrainInputEvent) -> AsyncIterator[tuple[FlowReturn, Any]]:
        state = AgentState(
            messages=[*self.history, {"role": "user", "content": event.text}],
            session_id=event.session_id,
            trace_id=event.trace_id,
        )

        full_text = ""
        async for output in self.agent_graph.run(state):
            if output.type == "token":
                full_text += output.content
                # Stream to TTS immediately
                yield FlowReturn.OK, AudioOutputRequest(content=output.content)
                # Post to UI
                self.bus.post(Message(type="ui_update", source="brain", payload=output))

            elif output.type == "approval_needed":
                # Notify UI that human approval is needed
                self.bus.post(Message(
                    type="approval_request",
                    source="brain",
                    payload=state.pending_approval,
                ))
                # TTS: "I need your permission to..."
                yield FlowReturn.OK, AudioOutputRequest(content=output.content)
                return  # Pause pipeline, wait for approval via API

            elif output.type == "tool_call":
                self.bus.post(Message(type="ui_update", source="brain", payload=output))

        # Update history
        self.history.append({"role": "user", "content": event.text})
        self.history.append({"role": "assistant", "content": full_text})
        await self._maybe_summarize()
```

### Human-in-the-Loop API

```python
# In api/router.py — new endpoint for human approval

@router.post("/api/approve/{checkpoint_id}")
async def approve_action(checkpoint_id: str, approved: bool, assistant: Assistant):
    """Human approves or rejects a pending action."""
    async for output in assistant.agent_graph.resume_after_approval(checkpoint_id, approved):
        # Stream results back through the pipeline
        if output.type == "token":
            await assistant.tts_queue.put(AudioOutputRequest(content=output.content))
        assistant.bus.post(Message(type="ui_update", source="brain", payload=output))

    return {"status": "ok", "checkpoint_id": checkpoint_id}
```

### Interruption via Bidirectional Events

```
User speaks → VAD detects speech
    │
    ▼
VAD sends Event(type="interrupt", direction="upstream")
    │
    ├──→ ASR receives: flushes partial results
    ├──→ Brain receives: cancels current LLM task
    ├──→ TTS receives: stops generation, flushes queue
    └──→ Playback receives: stops audio, fades out

    VAD also sends Event(type="flush", direction="downstream")
    │
    └──→ All downstream queues drain
```

This replaces the single `threading.Event` with targeted, per-processor interruption handling.

---

## Part 4: Implementation Roadmap

### Phase 0: Foundation (Week 1) ✅ COMPLETED
> Goal: Core abstractions without breaking existing functionality

**Functionality status: ✅ No breakage — new code only, old pipeline untouched**

**0.1 — Define core interfaces**
- Create `backend/core/src/tank_backend/pipeline/` package
- Implement `Processor` ABC, `FlowReturn` enum, `Event` dataclass, `AudioCaps`
- Implement `ThreadedQueue` with bounded size and backpressure
- Implement `Message` and `Bus`
- Write unit tests for all primitives

**0.2 — Implement PipelineBuilder**
- Parse pipeline config from `config.yaml`
- Validate caps compatibility between linked processors
- Insert `ThreadedQueue` at configured thread boundaries
- Wire up `Bus` with configured observers

**0.3 — Implement base observers**
- `LatencyObserver`: per-stage timing
- `TurnTrackingObserver`: conversation turn metrics
- `InterruptLatencyObserver`: time from VAD trigger to full silence
- Wire observers to Bus

**Deliverable**: New `pipeline/` package with core abstractions, fully tested, not yet integrated.

### Phase 1: Wrap Existing Components (Week 2) ✅ COMPLETED
> Goal: Wrap current workers as Processors — bridge old and new

**Functionality status: ✅ No breakage — wrappers delegate to existing workers, old Assistant still orchestrates**

**1.1 — Wrap VAD as Processor**
- `VADProcessor` wraps existing `SileroVAD`
- Declares `input_caps = AudioCaps(sample_rate=16000)`
- Emits `Event(type="interrupt", direction="upstream")` on speech detection

**1.2 — Wrap ASR as Processor**
- `ASRProcessor` wraps existing `StreamingPerception`
- Declares `input_caps` and `output_type`
- Posts transcription metrics to Bus

**1.3 — Wrap Brain as Processor**
- `BrainProcessor` wraps existing `Brain`
- Handles `interrupt` events (cancels LLM task)
- Posts LLM latency metrics to Bus

**1.4 — Wrap TTS as Processor**
- `TTSProcessor` wraps existing `TTSWorker`
- Handles `interrupt` and `flush` events
- Posts TTS latency metrics to Bus

**1.5 — Wrap Playback as Processor**
- `PlaybackProcessor` wraps existing `PlaybackWorker` / `CallbackAudioSink`
- Handles `flush` events (stop + fade out)

**Deliverable**: All existing components wrapped as Processors. Old `Assistant` still orchestrates, but components are now swappable.

### Phase 2: Pipeline Integration (Week 3) ✅ COMPLETED
> Goal: Replace Assistant's hardcoded orchestration with PipelineBuilder

**⚠️ BREAKING CHANGE: Speech interruption will be temporarily degraded during this phase**

**2.1 — New Assistant using PipelineBuilder**
- `AssistantV2` reads pipeline config from `config.yaml`
- Uses `PipelineBuilder` to construct processor chain with ThreadedQueues
- Replaces hardcoded thread creation with topology-driven threading
- Bus replaces `ui_queue`

**2.2 — Migrate WebSocket handler**
- `router.py` uses `AssistantV2`
- WebSocket handler subscribes to Bus for UI messages
- Audio input feeds into pipeline's first processor
- Audio output comes from pipeline's last processor

**2.3 — Migrate interruption (CRITICAL — restores functionality)**
- Remove `threading.Event` from `RuntimeContext`
- Interruption now flows as bidirectional `Event` through pipeline
- Each processor handles interruption independently:
  - `VADProcessor`: Emits `Event(type="interrupt", direction="upstream")` on speech detection
  - `PlaybackProcessor.handle_event(interrupt)`: Apply 5ms fade-out, stop gracefully (not `CallbackAbort`)
  - `TTSProcessor.handle_event(interrupt)`: Set cancel token, stop generation
  - `BrainProcessor.handle_event(interrupt)`: Cancel agent graph, save partial response to history
  - `ThreadedQueue.flush()`: Drain queues at thread boundaries
- **Interruption latency**: Target <20ms (VAD detection → full silence)
- Add `InterruptLatencyObserver` to Bus — tracks time from VAD trigger to last processor ack

**2.4 — Remove old orchestration**
- Delete old `RuntimeContext` (queues + event)
- Delete old `QueueWorker` base class
- `AssistantV2` becomes `Assistant`

**Downtime mitigation strategy:**
- Implement 2.3 (interruption) BEFORE 2.4 (delete old code)
- Run integration tests with interruption scenarios before removing old code
- Keep `config.yaml` version flag for instant rollback if issues found

**Deliverable**: Pipeline is config-driven. Threading is topology-driven. Interruption is event-driven with <20ms latency. Old orchestration removed.

**Functionality status:**
- ✅ Speech interruption: **RESTORED** (better than before — ordered propagation, graceful fade-out, partial response saved)
- ❌ ANC: Still not implemented (no change from current)

### Phase 3: Advanced Features — ANC & Audio Filters (Week 4-5) ✅ COMPLETED
> Goal: Leverage the new architecture for features that were impossible before

**Functionality status: ✅ All existing features working. NEW: Noise cancellation and AEC added.**

**3.1 — Context summarization**
- Add `summarize_at` config to BrainProcessor
- Implement `_maybe_summarize()` using LLM
- Track token usage via Bus metrics

**3.2 — VAD Threshold Switching During Playback (Echo Guard Layer 1)**

When TTS is playing through the speaker, the microphone picks up the assistant's own voice.
Echo from speakers is typically quieter at the mic than direct user speech. By raising the
VAD `speech_threshold` during playback, most echo is filtered at the signal level before it
triggers any interrupt or ASR transcription.

**Architecture — defense in depth:**

```
Layer 1: VAD threshold during playback     — raises VAD sensitivity, filters echo at signal level
Layer 2: Self-echo text detection          — catches what slips through layer 1 (semantic safety net)
```

**Why NOT backend signal-level AEC/ANC:**
- By the time audio reaches the backend, the echo is already mixed with user voice and degraded by network transit
- The reference signal arrives via bus with variable network jitter — misalignment degrades AEC quality
- The backend can't model the acoustic path (speaker → room → mic) — it never heard the room
- Frontend platforms already have hardware-optimized AEC that outperforms any software solution
- Backend's unique advantage is **semantic context** (knows what TTS just said), not signal processing

**VAD threshold switching implementation:**
- `SileroVAD` exposes `set_threshold(value)` and `reset_threshold()` methods
- `VADProcessor` subscribes to `playback_started` / `playback_ended` bus messages
- During playback: raises threshold (default 0.85) so only loud/close speech triggers detection
- On playback end: restores default threshold immediately
- Keeps immediate interrupt behavior — no deferred interrupt complexity
- Preserves barge-in for loud/close user speech
- Config:
  ```yaml
  echo_guard:
    enabled: true
    vad_threshold_during_playback: 0.85  # higher = less sensitive during playback
  ```

**3.3 — Self-echo text detection (Echo Guard Layer 2)**

After ASR produces a transcript, compare it against recent TTS output using token overlap.
If the transcript is too similar to what the assistant just said, discard it.

**Implementation:**
- `SelfEchoDetector` class maintains a sliding window of recent TTS text (last 10 seconds)
- On each ASR transcript: compute token overlap ratio against recent TTS text
- If overlap > threshold (default 0.6) → discard transcript, log as echo
- Uses simple word-level tokenization (split + lowercase + strip punctuation)
- Posts `echo_discarded` metric to Bus for observability
- Config:
  ```yaml
  echo_guard:
    self_echo_detection:
      enabled: true
      similarity_threshold: 0.6    # discard if >60% token overlap
      window_seconds: 10           # compare against last 10s of TTS text
  ```

**Why this approach is superior to backend signal-level AEC:**
- Platform-independent — protects all clients (web, CLI, Tauri, mobile) equally
- Zero additional latency — runs after ASR, not in the audio hot path
- No signal processing dependencies (no speexdsp, no noisereduce)
- Leverages the backend's unique advantage: knowing what was just spoken
- Fail-open — if detection fails, audio passes through (same as current behavior)
- Observable — `echo_discarded` metrics show how often echo leaks through platform AEC

**3.4 — Smart turn detection**
- Implement `SmartTurnProcessor` that uses ML model for end-of-turn detection
- Replace simple silence timeout with prosody-aware detection
- Configurable via pipeline config

**3.5 — Fan-out support**
- Extend PipelineBuilder to support parallel branches:
  ```yaml
  stages:
    - name: vad
      processor: vad:silero
      fan_out:
        - name: asr
          processor: asr-sherpa:asr
        - name: speaker_id
          processor: speaker-sherpa:speaker
      fan_in: brain    # both feed into brain
  ```
- ASR and speaker ID run in parallel on the same audio

**Deliverable**: Self-echo detection, VAD threshold switching, smart turn detection, parallel processing.

**Functionality status:**
- ✅ Speech interruption: Working (immediate interrupt, no deferred logic)
- ✅ Echo guard Layer 1: **NEW** — VAD threshold raised during playback filters echo at signal level
- ✅ Echo guard Layer 2: **NEW** — self-echo text detection catches leaked echo semantically

### Phase 4: LLM Layer Hardening (Week 6) ✅ COMPLETED
> Goal: Make the LLM layer production-robust without adding frameworks

**4.1 — Token counting with tiktoken**
- Add `_count_tokens()` to `Brain` using `tiktoken` (already an `openai` transitive dep)
- Replace message-count-based truncation with token-aware truncation
- Log token usage per turn to Bus

**4.2 — Context summarization**
- Add `summarize_at` config to BrainProcessor
- Implement `_maybe_summarize()` — when history exceeds token threshold, summarize older messages via a fast LLM call
- Keep system prompt + summary + last N messages
- Track summarization events via Bus metrics

**4.3 — Bounded tool iterations**
- Add `MAX_TOOL_ITERATIONS = 10` guard to `chat_stream()` `while True` loop
- Log warning when limit is hit

**4.4 — Retry with exponential backoff**
- Add `tenacity` retry decorator to `_create_completion()` in `llm.py`
- Retry on transient errors (rate limit, timeout, 5xx) with exponential backoff
- Max 3 attempts, 1-10s wait

**4.5 — Multiple LLM profiles per task**
- Extend `config.yaml` to support task-specific model selection:
  ```yaml
  llm:
    conversation:
      model: deepseek-chat
      temperature: 0.7
    summarization:
      model: gpt-4o-mini      # fast + cheap for summarization
      temperature: 0.3
    tool_use:
      model: gpt-4o           # strong reasoning for tool selection
      temperature: 0.2
    routing:
      model: gpt-4o-mini      # fast intent classification
      temperature: 0.0
  ```
- `Brain` / `AgentGraph` selects profile based on task type

**4.6 — Conversation persistence (Checkpointer)**
- Implement `Checkpointer` with SQLite backend
- Save conversation state at end of each turn
- Load previous session on reconnect via `session_id`
- API endpoint: `GET /api/sessions/{session_id}` to resume

**Deliverable**: Token-aware history management, auto-summarization, robust error handling, task-specific model routing, conversation persistence.

### Phase 5: Observability & Dashboard (Week 7-8) ✅ COMPLETED
> Goal: Full-stack observability across pipeline and LLM layers

(unchanged — see existing Phase 5 content)

### Phase 6: Agent Orchestration Layer (Week 9-11) ✅ COMPLETED
> Goal: Evolve Brain from single-LLM to multi-agent state graph

**Functionality status: ✅ No breakage — ChatAgent wraps existing Brain, new agents added alongside**
**Speech interruption: ✅ Working — BrainProcessor v2 propagates interrupt to AgentGraph via cancel token**
**ANC/AEC: ✅ Working — untouched (Layer 1 is independent of Layer 2 changes)**

**6.1 — Agent base class and AgentOutput protocol**
- Create `backend/core/src/tank_backend/agents/` package
- Implement `Agent` ABC with `async run() -> AsyncIterator[AgentOutput]`
- Implement `AgentState` dataclass with shared state, messages, metadata
- Implement `AgentOutput` dataclass (token, tool_call, tool_result, handoff, approval_needed)
- Write unit tests

**6.2 — Chat agent (wrap existing Brain)**
- `ChatAgent` wraps existing `Brain._process_stream()` logic
- Uses `llm.chat_stream()` directly — no framework overhead
- Yields `AgentOutput(type="token")` for each LLM token
- Handles tool calling loop internally, yields tool status updates
- This is the default agent — all current functionality preserved

**6.3 — Router (intent classification)**
- Implement `Router` with fast-path keyword matching + slow-path LLM classification
- Fast path: regex/keyword patterns for common intents (search, calculate, task)
- Slow path: single LLM call with `routing` profile (fast model, temperature=0)
- Router is the entry node of the agent graph

**6.4 — AgentGraph orchestrator**
- Implement `AgentGraph` with `async run() -> AsyncIterator[AgentOutput]`
- Supports: routing → agent execution → handoff → another agent → done
- Max iteration guard (prevent infinite agent loops)
- Streams tokens immediately (async generator, no batching)
- Integrates with `Checkpointer` for state persistence

**6.5 — BrainProcessor v2 (bridge pipeline ↔ agent graph)**
- Refactor `BrainProcessor` to delegate to `AgentGraph` instead of calling `llm.chat_stream()` directly
- Streams `AgentOutput` tokens to TTS immediately via pipeline
- Posts all agent events to Bus (routing decisions, tool calls, handoffs)
- Handles `approval_needed` by pausing pipeline and notifying UI

**6.6 — Specialized agents**
- `SearchAgent` — web search + summarization (uses `web_search` + `web_scraper` tools)
- `TaskAgent` — task management, reminders, scheduling
- `CodeAgent` — code execution via sandbox tools
- Each agent has its own system prompt, tool set, and LLM profile
- Agents are registered via config:
  ```yaml
  agents:
    chat:
      type: chat
      llm_profile: conversation
      tools: [weather, time, calculator]
    search:
      type: search
      llm_profile: tool_use
      tools: [web_search, web_scraper]
    task:
      type: task
      llm_profile: conversation
      tools: [calculator, time]
    code:
      type: code
      llm_profile: tool_use
      tools: [sandbox_exec, sandbox_bash]
  ```

**Deliverable**: Multi-agent system with routing, handoff, specialized agents, all streaming through the audio pipeline.

### Phase 7: Human-in-the-Loop (Week 12-13) ✅ COMPLETED
> Goal: Approval gates for sensitive actions, with voice + UI interaction

**7.1 — ApprovalRequest and approval gate**
- Implement `ApprovalRequest` dataclass (action, description, tool_name, tool_args, checkpoint_id)
- Agents can yield `AgentOutput(type="approval_needed")` before sensitive tool calls
- AgentGraph checkpoints state and pauses execution

**7.2 — Approval API endpoints**
- `POST /api/approve/{checkpoint_id}` — approve or reject pending action
- `GET /api/pending-approvals` — list all pending approvals for a session
- WebSocket notification when approval is needed

**7.3 — Voice-based approval flow**
- When approval is needed, TTS speaks: "I'd like to [action]. Should I proceed?"
- ASR listens for "yes"/"no"/"go ahead"/"cancel" (simple intent classification)
- Auto-approve or auto-reject based on voice response
- Fallback to UI approval if voice is ambiguous

**7.4 — Approval policies (config-driven)**
- Define which tools require approval:
  ```yaml
  approval_policies:
    always_approve:
      - weather
      - time
      - calculator
    require_approval:
      - sandbox_exec
      - sandbox_bash
      - web_scraper
    require_approval_first_time:
      - web_search    # approve once per session, then auto-approve
  ```
- Policies are checked by AgentGraph before tool execution

**7.5 — Resume after approval**
- `AgentGraph.resume_after_approval()` loads checkpoint, executes or rejects tool, continues graph
- Full conversation context preserved across the pause
- Langfuse trace shows the approval pause and resume

**Deliverable**: Human-in-the-loop approval for sensitive tools, voice + UI approval, configurable policies, checkpoint-based resume.

### Phase 8: Production Readiness (Week 14-15) ✅ COMPLETED
> Goal: Health monitoring, alerting, graceful degradation

**8.1 — Health monitoring**
- Pipeline health check: all processors running, queues not stuck
- Agent graph health: no stuck checkpoints, no infinite loops
- LLM health check: Langfuse connectivity, LLM API reachability
- Auto-restart on processor failure
- Expose via `/health` endpoint (for load balancers / k8s probes)

**8.2 — QoS feedback (from GStreamer)**
- If TTS can't keep up, send QoS event upstream
- Brain can reduce response length or skip tool calls
- Graceful degradation under load

**8.3 — Dynamic processor swap**
- Implement pad-probe-like mechanism:
  1. Block upstream queue
  2. Drain downstream queue
  3. Swap processor
  4. Unblock
- Enable hot-swapping ASR/TTS engines without restart

**8.4 — Alerting**
- Bus observer detects anomalies:
  - Latency spike (>2x p95 for 5 consecutive turns)
  - Error rate (>10% of turns in last 5 minutes)
  - Queue saturation (>80% full for >30 seconds)
  - Stuck approval requests (>5 min without response)
- Post alert messages to Bus → webhook/email notification
- Langfuse alerts on LLM-specific anomalies (cost spike, error rate)

**Deliverable**: Production-grade health monitoring, graceful degradation, hot-swap, alerting.

---

## Part 5: Migration Strategy

### Parallel Operation

During Phase 1-2, both old and new architectures coexist:

```
config.yaml:
  pipeline:
    version: 1    # Use old Assistant
    # version: 2  # Use new pipeline-based Assistant
```

This allows gradual migration and A/B testing.

### Langfuse Integration is Non-Breaking

Langfuse integration (Phase 5) can be done on the current architecture — it doesn't depend on the pipeline refactor. The single import change (`from langfuse.openai import AsyncOpenAI`) works with the existing `llm.py`. This means you can get LLM observability immediately, before any pipeline work.

### Agent Graph is Incremental

Phase 6 (Agent Orchestration) doesn't require rewriting the Brain. The `ChatAgent` wraps the existing `Brain._process_stream()` logic — all current functionality is preserved. New agents are added alongside, not replacing.

**Recommended quick-win order:**
1. Phase 4.3 (bounded tool iterations) — 5 min, prevents runaway loops
2. Phase 5.1 + 5.2 (Langfuse deploy + integrate) — 1 day, immediate dashboard
3. Phase 4.1 (token counting) — 30 min, enables smart truncation
4. Phase 4.2 (context summarization) — 2 hours, fixes unbounded history
5. Phase 4.6 (conversation persistence) — 2 hours, enables session resume
6. Then proceed with pipeline refactor (Phase 0-3)
7. Then agent orchestration (Phase 6-7)

### Backward Compatibility

- Existing plugins continue to work — Processor wrappers delegate to plugin instances
- Existing `config.yaml` format is extended, not replaced
- Existing tests continue to pass — new tests added for pipeline primitives
- Langfuse is optional — if not configured, `AsyncOpenAI` import falls back to standard SDK
- Agent graph is optional — if only `chat_agent` is configured, behavior is identical to current Brain

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Latency regression | Benchmark before/after each phase; Bus metrics track per-stage latency |
| Thread safety bugs | ThreadedQueue is the only shared state; processors are single-threaded within their queue |
| Breaking existing features | Parallel operation (version flag) allows rollback |
| Over-engineering | Each phase delivers standalone value; stop after any phase if sufficient |
| Langfuse downtime | Langfuse SDK is async/non-blocking; if Langfuse is unreachable, LLM calls still work (traces are dropped) |
| Cost tracking accuracy | Langfuse uses model pricing tables; verify against actual provider invoices monthly |
| Agent routing latency | Fast-path keyword matching handles 80% of intents; LLM routing only for ambiguous cases |
| Approval UX friction | Voice-based approval for common cases; UI fallback for complex ones; configurable policies per tool |
| Checkpoint storage growth | TTL on checkpoints (7 days default); periodic cleanup job |
| **Speech interruption breakage (Phase 2)** | **Implement 2.3 (event-based interruption) BEFORE 2.4 (delete old code); integration tests with interruption scenarios; keep version flag for instant rollback** |
| **AEC false negatives (Phase 3)** | **Defense in depth: Layer 1 (VAD threshold during playback) + Layer 2 (self-echo text detection). If any layer fails, the next catches it. Config-tunable thresholds per deployment.** |
| **Echo detection false positives** | **Conservative default threshold (0.6 token overlap). User speech that happens to repeat assistant words is rare and short. Minimum word count (3) during playback prevents single-word false discards.** |

### Minimizing Downtime: Critical Path Analysis

**Speech interruption downtime window:**
- **Breaks**: Phase 2.1-2.2 (when `AssistantV2` is activated but event-based interruption not yet implemented)
- **Restores**: Phase 2.3 (event-based interruption implemented)
- **Duration**: ~2-4 hours if done sequentially
- **Mitigation**: Implement 2.3 in parallel with 2.1-2.2, activate all three together in a single deployment

**Zero-downtime deployment strategy for Phase 2:**

```
Day 1 (Morning):
  - Implement Phase 2.1 (AssistantV2 + PipelineBuilder) — don't activate yet
  - Implement Phase 2.2 (WebSocket migration) — don't activate yet
  - Implement Phase 2.3 (event-based interruption) — don't activate yet
  - All code merged but behind version flag

Day 1 (Afternoon):
  - Run full integration test suite with version=2
  - Test interruption scenarios specifically:
    - Interrupt during TTS playback
    - Interrupt during LLM streaming
    - Interrupt during tool execution
    - Rapid successive interrupts
  - Measure interruption latency (target <20ms)

Day 1 (Evening):
  - Deploy with version=1 (old pipeline still active)
  - Flip version flag to version=2 in config
  - Monitor Bus metrics for 1 hour
  - If issues: flip back to version=1 (instant rollback)
  - If stable: proceed to Phase 2.4 (delete old code)

Downtime: 0 seconds (version flag flip is instant)
```

**Echo guard has no downtime risk:**
- Phase 3.2 (VAD threshold switching) and 3.3 (self-echo text detection) are backend-only layers
- If they fail, audio passes through unprocessed — same as current behavior (fail-open)
- Can be disabled via config without code changes:
  ```yaml
  echo_guard:
    enabled: false    # disable all echo guard layers
  ```

---

## Part 6: Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Adding a new pipeline stage | ~2 hours (queue plumbing) | ~15 min (config + Processor class) |
| Swapping ASR/TTS engine | Restart required | Hot-swap, zero downtime |
| End-to-end latency visibility | None (logging only) | Per-stage p50/p95/p99 via `/api/metrics` |
| Backpressure handling | None (unbounded queues) | Bounded queues with FlowReturn |
| Interruption latency | ~50ms (polling interval) | <10ms (event propagation) |
| Context overflow handling | None (grows forever) | Auto-summarization at token threshold |
| Audio pre-processing | None | Platform AEC (frontend) + semantic echo guard (backend) |
| LLM call visibility | None (logging only) | Every call traced in Langfuse (prompt, tokens, cost, latency) |
| Token usage tracking | None | Per-call, per-session, per-day breakdown in Langfuse dashboard |
| Cost tracking | None | Real-time cost per conversation, daily/monthly aggregates |
| Conversation review | None | Browse all conversations in Langfuse UI with full traces |
| Tool call debugging | Log messages only | Full tool call chain visible in Langfuse trace view |
| Trace correlation | Pipeline and LLM are separate | Unified trace_id links audio input → ASR → LLM → TTS |
| Error diagnosis | Grep through logs | Langfuse error filtering + pipeline Bus error events |
| Alerting | None | Automated alerts on latency spikes, error rates, cost anomalies |
| Adding a new agent | N/A (single Brain) | Config + Agent class, auto-registered in graph |
| Agent routing | N/A (single Brain) | Intent-based routing to specialized agents |
| Sensitive tool safety | No approval gate | Human-in-the-loop with voice + UI approval |
| Session resumption | None (in-memory only) | Checkpoint to SQLite, resume via session_id |
| Multi-agent handoff | N/A | Agent A → Agent B with shared state preserved |

---

## Part 7: Observability Architecture

### Two-Layer Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Observability Architecture                       │
│                                                                      │
│  Layer 1: Pipeline Observability (Internal)                          │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                        Message Bus                             │  │
│  │                                                                │  │
│  │  Producers:              Consumers:                            │  │
│  │  ├─ VAD processor        ├─ LatencyObserver → /api/metrics     │  │
│  │  ├─ ASR processor        ├─ TurnTrackingObserver → /api/metrics│  │
│  │  ├─ Brain processor      ├─ QueueDepthObserver → /api/metrics  │  │
│  │  ├─ TTS processor        ├─ AlertObserver → webhook/email      │  │
│  │  ├─ Playback processor   └─ WebSocket UI → client display      │  │
│  │  └─ ThreadedQueues                                             │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Layer 2: LLM Observability (Langfuse)                               │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                                                                │  │
│  │  AsyncOpenAI (Langfuse-wrapped)                                │  │
│  │       │                                                        │  │
│  │       ├─ Auto-captures: prompts, completions, tokens, cost     │  │
│  │       ├─ Auto-captures: streaming TTFT, tool calls             │  │
│  │       ├─ Trace metadata: session_id, user_id, trace_id         │  │
│  │       │                                                        │  │
│  │       ▼                                                        │  │
│  │  Langfuse Server (self-hosted Docker)                          │  │
│  │       │                                                        │  │
│  │       ├─ ClickHouse (time-series storage)                      │  │
│  │       ├─ PostgreSQL (metadata, users, projects)                │  │
│  │       │                                                        │  │
│  │       ▼                                                        │  │
│  │  Langfuse Web Dashboard                                        │  │
│  │       ├─ Conversation traces                                   │  │
│  │       ├─ Token usage & cost analytics                          │  │
│  │       ├─ Latency breakdown (TTFT, total)                       │  │
│  │       ├─ Model comparison                                      │  │
│  │       └─ Prompt versioning & evaluation                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Trace Linking:                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  trace_id generated at turn start (ASR final)                  │  │
│  │       │                                                        │  │
│  │       ├─ Attached to Bus messages (pipeline metrics)           │  │
│  │       └─ Attached to Langfuse trace (LLM metrics)              │  │
│  │                                                                │  │
│  │  Enables: "audio chunk X → ASR took 120ms → LLM took 2.1s     │  │
│  │           → used 450 tokens ($0.003) → TTS took 200ms"         │  │
│  └────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Langfuse Integration Detail

```python
# llm.py — minimal change required

# Option A: Drop-in wrapper (recommended, zero code change beyond import)
from langfuse.openai import AsyncOpenAI  # instead of: from openai import AsyncOpenAI

# Option B: Explicit decorator (more control over trace metadata)
from langfuse import Langfuse

langfuse = Langfuse()

class LLM:
    async def chat_stream(self, messages, tools, tool_executor, trace_id=None):
        trace = langfuse.trace(
            id=trace_id,
            name="conversation_turn",
            session_id=self._session_id,
            metadata={"model": self.model, "tools": [t["function"]["name"] for t in tools]},
        )
        generation = trace.generation(
            name="llm_stream",
            model=self.model,
            input=messages,
        )

        # ... existing streaming code ...

        generation.end(
            output=full_content,
            usage={"input": prompt_tokens, "output": completion_tokens},
        )
```

### Docker Compose for Langfuse

```yaml
# docker-compose.observability.yml
services:
  langfuse-server:
    image: langfuse/langfuse:2
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
      - NEXTAUTH_SECRET=your-secret-here
      - SALT=your-salt-here
      - NEXTAUTH_URL=http://localhost:3000
      - TELEMETRY_ENABLED=false
    depends_on:
      - langfuse-db
      - langfuse-clickhouse

  langfuse-db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_USER=langfuse
      - POSTGRES_PASSWORD=langfuse
      - POSTGRES_DB=langfuse
    volumes:
      - langfuse-pg-data:/var/lib/postgresql/data

  langfuse-clickhouse:
    image: clickhouse/clickhouse-server:24
    volumes:
      - langfuse-ch-data:/var/lib/clickhouse

volumes:
  langfuse-pg-data:
  langfuse-ch-data:
```

---

## Appendix A: File Structure After Implementation

```
backend/core/src/tank_backend/
├── pipeline/                     # NEW — core pipeline framework (Phase 0)
│   ├── __init__.py
│   ├── processor.py              # Processor ABC, FlowReturn, AudioCaps
│   ├── event.py                  # Event, EventType
│   ├── queue.py                  # ThreadedQueue (thread boundary)
│   ├── bus.py                    # Message, Bus
│   ├── builder.py                # PipelineBuilder (config-driven)
│   ├── observer.py               # PipelineObserver protocol
│   └── observers/
│       ├── latency.py            # LatencyObserver
│       ├── turn_tracking.py      # TurnTrackingObserver
│       ├── queue_depth.py        # QueueDepthObserver
│       └── alert.py              # AlertObserver (anomaly detection)
│
├── processors/                   # NEW — processor implementations (Phase 1-3)
│   ├── __init__.py
│   ├── vad_processor.py          # Wraps SileroVAD
│   ├── asr_processor.py          # Wraps ASR engines
│   ├── brain_processor.py        # Bridge: pipeline ↔ agent graph
│   ├── tts_processor.py          # Wraps TTS engines
│   ├── playback_processor.py     # Wraps playback
│   ├── noise_filter_processor.py # Audio noise cancellation
│   └── smart_turn_processor.py   # ML-based turn detection
│
├── agents/                       # NEW — agent orchestration layer (Phase 6-7)
│   ├── __init__.py
│   ├── base.py                   # Agent ABC, AgentOutput, AgentState
│   ├── graph.py                  # AgentGraph orchestrator
│   ├── router.py                 # Intent-based routing (keyword + LLM)
│   ├── checkpointer.py           # SQLite-based state persistence
│   ├── approval.py               # ApprovalRequest, approval policies
│   ├── chat_agent.py             # Default conversational agent (wraps existing Brain)
│   ├── search_agent.py           # Web search + summarization
│   ├── task_agent.py             # Task management, reminders
│   └── code_agent.py             # Code execution via sandbox
│
├── core/                         # MODIFIED
│   ├── assistant.py              # Refactored to use PipelineBuilder + AgentGraph
│   ├── brain.py                  # Kept as implementation, wrapped by ChatAgent
│   ├── events.py                 # Kept for backward compat
│   ├── runtime.py                # Deprecated after Phase 2
│   └── worker.py                 # Deprecated after Phase 2
│
├── llm/                          # MODIFIED (Phase 4-5)
│   ├── llm.py                    # Langfuse-wrapped AsyncOpenAI + retry + token counting
│   ├── profile.py                # Extended: task-specific model profiles
│   └── summarizer.py             # NEW — context summarization utility
│
├── audio/                        # UNCHANGED — processors wrap these
│   ├── input/
│   └── output/
│
├── plugin/                       # EXTENDED — registers processor + agent factories
│   ├── manager.py
│   ├── registry.py
│   └── ...
│
├── api/                          # EXTENDED (Phase 5, 7)
│   ├── router.py                 # Uses Bus instead of ui_queue
│   ├── metrics.py                # NEW — /api/metrics endpoint
│   ├── health.py                 # NEW — /health endpoint
│   ├── approval.py               # NEW — /api/approve, /api/pending-approvals
│   └── sessions.py               # NEW — /api/sessions (resume conversations)
│
└── observability/                # NEW — observability utilities (Phase 5)
    ├── __init__.py
    ├── langfuse_client.py        # Langfuse initialization + trace helpers
    └── trace.py                  # Trace ID generation + linking
```

## Appendix B: Quick-Win Implementation Order

For maximum value with minimum effort, implement in this order (independent of pipeline refactor):

```
Day 1:  Phase 4.3 — Bounded tool iterations (5 min, prevents runaway loops)
Day 1:  Phase 5.1 — Deploy Langfuse via Docker Compose (1 hour)
Day 1:  Phase 5.2 — Swap AsyncOpenAI import (10 min, instant LLM dashboard)
Day 2:  Phase 4.1 — Token counting with tiktoken (30 min)
Day 2:  Phase 4.4 — Retry with backoff (30 min)
Day 3:  Phase 4.2 — Context summarization (2 hours)
Day 3:  Phase 4.6 — Conversation persistence / Checkpointer (2 hours)
Day 4:  Phase 5.4 — Trace linking (2 hours)
Week 2: Phase 0   — Pipeline foundation (start the architecture refactor)
Week 3: Phase 1-2 — Wrap components + pipeline integration
Week 4: Phase 3   — Advanced pipeline features (fan-out, noise filter)
Week 5: Phase 6.1-6.4 — Agent graph foundation + ChatAgent
Week 6: Phase 6.5-6.6 — BrainProcessor v2 + specialized agents
Week 7: Phase 7   — Human-in-the-loop approval
Week 8: Phase 8   — Production readiness
```

This gives you a working observability dashboard on Day 1, conversation persistence by Day 3, and the full multi-agent system by Week 7.

## Appendix C: Research Summary

### Frameworks Evaluated

| Framework | Verdict | Reason |
|-----------|---------|--------|
| **Pipecat** | Borrow ideas, don't adopt | Good composability model, but async-only + frame overhead conflicts with voice latency |
| **GStreamer** | Borrow ideas, don't adopt | Gold standard patterns (queue-as-thread-boundary, backpressure, bidirectional events), but C/GObject complexity is overkill |
| **LangChain** | Don't adopt | Massive dependency, abstraction tax on streaming, breaking API changes, tool calling already solved |
| **LangGraph** | Borrow ideas, don't adopt | Excellent multi-agent/HITL patterns, but batched streaming + checkpoint-per-superstep conflicts with voice latency |
| **LlamaIndex** | Don't adopt | RAG-focused, not relevant to voice pipeline |
| **Langfuse** | Adopt (self-hosted) | Drop-in OpenAI wrapper, MIT license, rich dashboard, minimal latency overhead |
| **Helicone** | Alternative to Langfuse | Proxy-based (~8ms overhead), simpler but less feature-rich |
| **Phoenix (Arize)** | Alternative to Langfuse | OpenTelemetry-native, good for dev, less suited for production multi-user |
| **OpenLIT** | Alternative to Langfuse | Zero-code instrumentation, but requires separate OTEL backend |

### Key Architectural Decisions

1. **Three-layer architecture** — Audio pipeline (real-time) / Agent orchestration (stateful) / LLM transport (raw SDK) — each layer has different latency constraints and can evolve independently
2. **Custom agent graph over LangGraph** — Async-generator-based streaming (no batching), checkpoint only at turn boundaries (not every superstep), no `langchain-core` dependency
3. **Langfuse over custom dashboard** — Rich LLM analytics out-of-the-box, one-import integration, self-hosted, MIT license
4. **Raw OpenAI SDK over LangChain** — 370 lines vs framework, zero abstraction tax on streaming hot path
5. **GStreamer patterns over GStreamer itself** — Queue-as-thread-boundary, FlowReturn, bidirectional events — implemented in Python, not C/GObject
