# Pipeline Architecture

This document describes Tank's three-layer audio pipeline architecture — inspired by GStreamer's threading model, Pipecat's composability, and LangGraph's agent orchestration ideas, but custom-built for voice assistant latency requirements.

## Three-Layer Design

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Audio Pipeline (GStreamer-inspired)                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Audio In → [VAD] → [Q] → [ASR] ──┬──→ [ASR+Speaker Merge]│ │
│  │                                    └──→ [Speaker ID]       │ │
│  │                                                            │ │
│  │ Audio Out ← [Playback] ← [Q] ← [TTS] ← [Echo Guard] ←   │ │
│  │                                              Brain         │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Layer 2: Agent Orchestration                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ AgentGraph → ChatAgent (all tools)                         │ │
│  │ Approval gates · Checkpointing · Streaming tokens to TTS   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Layer 3: LLM Transport (Raw SDK)                                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ AsyncOpenAI (Langfuse-wrapped) · Retry · Token counting    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Cross-cutting: Message Bus + Observers + Langfuse               │
└─────────────────────────────────────────────────────────────────┘
```

**Why three layers matter:**

- **Layer 1 (Audio Pipeline)** has hard real-time constraints — 20ms audio frames, interrupt within 10ms, backpressure on queues. Must never block on agent logic.
- **Layer 2 (Agent Orchestration)** is where intelligence lives — managing conversation state, handling tool approval. Must stream LLM tokens to TTS immediately (not batch them).
- **Layer 3 (LLM Transport)** is a thin wrapper — raw `AsyncOpenAI` with retry, token counting, and Langfuse tracing. No framework, no abstraction tax.

The critical interface is between Layer 1 and Layer 2: `BrainProcessor` sits in the audio pipeline but delegates to the agent graph. It streams tokens from the agent graph to TTS without buffering.

## Core Abstractions

Key files:

| File | Purpose |
|------|---------|
| `pipeline/processor.py` | `Processor` ABC, `AudioCaps`, `FlowReturn` |
| `pipeline/event.py` | `PipelineEvent`, `EventDirection` |
| `pipeline/queue.py` | `ThreadedQueue` — bounded queue creating thread boundaries |
| `pipeline/fan_out_queue.py` | `FanOutQueue` — routes items to parallel branches |
| `pipeline/bus.py` | `Bus`, `BusMessage` — thread-safe pub/sub |
| `pipeline/builder.py` | `PipelineBuilder`, `Pipeline` — fluent builder + lifecycle |
| `pipeline/health.py` | `HealthAggregator` — unified health checks |

## Processor Interface

Every pipeline stage implements the same interface:

```python
class Processor(ABC):
    name: str
    input_caps: AudioCaps | None = None   # None = non-audio input
    output_caps: AudioCaps | None = None  # None = non-audio output

    @abstractmethod
    async def process(self, item: Any) -> AsyncIterator[tuple[FlowReturn, Any]]:
        """Process input, yield (flow_return, output) pairs."""

    def handle_event(self, event: PipelineEvent) -> bool:
        """Handle control event. Return True if consumed, False to propagate."""
        return False

    async def start(self): ...
    async def stop(self): ...
```

Processors are async generators that yield `(FlowReturn, output)` pairs. This enables streaming output without buffering the entire result.

### FlowReturn

Backpressure signaling enum:

| Value | Meaning |
|-------|---------|
| `OK` | Normal output, continue processing |
| `EOS` | End of stream |
| `FLUSHING` | Queue is draining (interrupt in progress) |
| `ERROR` | Processor error |

### AudioCaps

Format declaration for audio processors:

```python
@dataclass
class AudioCaps:
    sample_rate: int
    channels: int = 1
    dtype: str = "float32"
```

Non-audio processors (Brain, EchoGuard) set `input_caps` / `output_caps` to `None`.

## Pipeline Data Flow

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

### Processors

| Processor | Input | Output | Notes |
|-----------|-------|--------|-------|
| `VADProcessor` | Audio frames | Speech segments | Emits `interrupt` events. Switches VAD threshold during playback (echo guard layer 1). |
| `ASRProcessor` | Speech segments | Transcripts | Posts ASR latency metrics to Bus. |
| `SpeakerIDProcessor` | Audio segments | Speaker identity | Runs in parallel branch via FanOutQueue. |
| `ASRSpeakerMerger` | ASR + Speaker ID | Combined transcript | Merges parallel branch results. |
| `BrainProcessor` | Transcripts | LLM responses | Bridges Layer 1 ↔ Layer 2. Token counting, context summarization, QoS feedback, checkpointing. |
| `EchoGuard` | Transcripts | Filtered transcripts | Layer 2 echo defense: compares ASR text against recent TTS output using token overlap. |
| `TTSProcessor` | Text | Audio chunks | Posts QoS messages when queue fill exceeds threshold. |
| `PlaybackProcessor` | Audio chunks | Speaker output | Handles interrupt with graceful fade-out (no audio pop). |

## ThreadedQueue (Thread Boundaries)

**Key design principle: Queue = Thread Boundary.** Inserting a `ThreadedQueue` between two processors creates a new thread. Pipeline topology determines threading, not hardcoding.

```python
class ThreadedQueue:
    def __init__(self, name: str, maxsize: int = 10): ...

    def push(self, item) -> FlowReturn:
        """Push item. Blocks if full (backpressure). Returns FlowReturn."""

    def flush(self):
        """Drain queue on interrupt."""

    def start(self):
        """Spawn consumer thread."""

    def stop(self):
        """Signal consumer to stop."""
```

- Bounded queue with configurable `maxsize`
- `push()` blocks when full (1.0s timeout) — this IS the backpressure mechanism
- Consumer thread runs an async event loop, calling `downstream.process()` for each item
- Tracks `_consecutive_failures` for health monitoring
- Daemon threads — won't prevent process exit

## FanOutQueue (Parallel Branches)

Routes processor outputs to multiple branch queues for parallel execution:

```python
class FanOutQueue(ThreadedQueue):
    def add_branch(self, name: str, queue: ThreadedQueue): ...
```

- Extends `ThreadedQueue`
- Consumer pushes output to ALL branches in parallel
- Each branch queue runs its own consumer thread
- Used for: ASR output → [SpeakerIDProcessor, ASRSpeakerMerger] in parallel

## PipelineEvent (Bidirectional Control)

Data flows downstream. Control events flow both directions.

```python
@dataclass(frozen=True)
class PipelineEvent:
    type: str          # "interrupt", "flush", "eos", "qos"
    direction: str     # UPSTREAM or DOWNSTREAM
    source: str        # processor name that originated the event
    metadata: dict
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

Each processor handles the event independently via `handle_event()`. Return `True` to consume (stop propagation), `False` to propagate to the next processor.

## Message Bus

Thread-safe pub/sub for decoupled observability:

```python
class Bus:
    def post(self, message: BusMessage): ...      # Thread-safe, from any thread
    def subscribe(self, msg_type: str, handler): ...
    def subscribe_all(self, handler): ...          # Subscribe to all message types
    def poll(self): ...                            # Dispatch pending messages (app thread)
```

Messages are queued in `_pending` list and dispatched via `poll()` from the application thread. Any processor can post; any observer can subscribe.

### BusMessage

```python
@dataclass
class BusMessage:
    type: str          # "metric", "ui_update", "qos", "error", "state_change"
    source: str        # processor name
    payload: dict
    timestamp: float
```

## Observers

Subscribe to Bus message types for pipeline monitoring:

| Observer | File | Purpose |
|----------|------|---------|
| `LatencyObserver` | `observers/latency.py` | Per-stage timing metrics |
| `InterruptLatencyObserver` | `observers/interrupt_latency.py` | VAD trigger → full silence latency |
| `TurnTracker` | `observers/turn_tracking.py` | Conversation turn metrics |
| `MetricsCollector` | `observers/metrics_collector.py` | Aggregated performance metrics + Langfuse trace IDs |
| `HealthMonitor` | `observers/health_monitor.py` | Pipeline health checks from Bus messages |
| `AlertingObserver` | `observers/alerting.py` | Anomaly detection: latency spikes, error rates, queue saturation |

Observers are lightweight — no blocking I/O in handlers.

## Health Monitoring

`HealthAggregator` collects health from multiple check functions:

```python
aggregator = HealthAggregator()
aggregator.register("llm", check_llm_health)
aggregator.register("asr", check_asr_health)

result = await aggregator.check_all()
# Returns worst status: unhealthy > degraded > healthy
```

Per-component health includes:
- Queue health: size, stuck detection, consumer alive status
- Processor health: running status, consecutive failures, last error
- Exposed via `GET /health?detail=true` (returns HTTP 503 if unhealthy)

## QoS Feedback

Graceful degradation under load:

1. `TTSProcessor` posts `"qos"` Bus messages when queue fill exceeds threshold
2. `BrainProcessor` subscribes: skips non-essential tool calls when TTS is overloaded
3. Prevents the pipeline from falling further behind

## Echo Guard (Defense in Depth)

Prevents the assistant from hearing its own voice through speakers:

- **Layer 1** (VAD threshold switching): During TTS playback, `VADProcessor` raises the VAD `speech_threshold` (default 0.85) so only loud/close speech triggers detection. Restores default on playback end.
- **Layer 2** (Self-echo text detection): `EchoGuard` maintains a sliding window of recent TTS text. Compares ASR transcripts against it using token overlap ratio. Discards if overlap > threshold (default 0.6).

Both layers are backend-only, platform-independent, and fail-open (if detection fails, audio passes through as before).

## Pipeline Builder

Fluent builder for assembling pipelines:

```python
pipeline = (PipelineBuilder()
    .add(VADProcessor(bus, config))
    .add(ThreadedQueue(name="vad_queue", maxsize=100))
    .add(ASRProcessor(bus, config))
    .fan_out(FanOutQueue(...), [speaker_id_queue, asr_merger_queue])
    .add(ThreadedQueue(name="brain_queue", maxsize=100))
    .add(BrainProcessor(bus, config))
    .add(EchoGuard(config))
    .add(ThreadedQueue(name="tts_queue", maxsize=100))
    .add(TTSProcessor(bus, config))
    .add(PlaybackProcessor(bus, config))
    .build())
```

`Pipeline` manages lifecycle: `await pipeline.start()` / `await pipeline.stop()`.

## LLM Transport (Layer 3)

Thin wrapper around `AsyncOpenAI`:

- Multiple named profiles (default, summarization) in `config.yaml`
- Streaming responses with real-time token delivery
- Bounded tool iterations: `MAX_TOOL_ITERATIONS = 10`
- Retry with exponential backoff: `MAX_RETRY_ATTEMPTS = 3`
- `tiktoken`-based token counting
- Auto context summarization when history exceeds `max_history_tokens`
- Optional Langfuse auto-tracing via monkey-patched `AsyncOpenAI`

## Observability Strategy

Two complementary layers:

1. **Pipeline layer** — Bus + observers for real-time pipeline health, exposed via `/api/metrics`
2. **LLM layer** — Langfuse for deep LLM tracing (token usage, cost, prompts, tool calls, conversation history)

Langfuse is async/non-blocking — no voice latency impact. Self-hostable via Docker.

## Gotchas

1. **ThreadedQueue blocks on full.** If downstream is slow, the queue fills and upstream blocks (1.0s timeout). This is intentional backpressure, but can cause latency spikes if queue sizes are too small.

2. **FanOutQueue fans to ALL branches.** If one branch is slow, all branches are affected because the fan-out consumer waits for all pushes to complete.

3. **Bus.poll() must be called from the app thread.** Messages accumulate in `_pending` until `poll()` dispatches them. If `poll()` is never called, messages pile up in memory.

4. **FlowReturn.ERROR doesn't stop the pipeline.** If a processor yields `ERROR`, the pipeline continues. Error handling must be implemented in the processor or observer — there's no automatic circuit breaker.

5. **Event propagation is synchronous.** If a processor's `handle_event()` is slow, event propagation is delayed. Keep event handlers fast and non-blocking.

6. **Processor lifecycle is explicit.** You must call `pipeline.start()` and `pipeline.stop()`. Forgetting `stop()` leaves consumer threads running.

7. **Audio frame timing is not enforced.** Processors don't validate that audio frames arrive at expected intervals. Out-of-order or gapped frames may produce incorrect results.

8. **Bus messages are not persisted.** If the app crashes, Bus messages are lost. For durable audit trails, use `AuditLogger` which writes to disk.

9. **Context summarization uses a separate LLM profile.** When history exceeds `max_history_tokens`, `BrainProcessor` summarizes using the `summarization` LLM profile (if configured). If not configured, falls back to message-count truncation.

10. **Interrupt latency target is <20ms.** The `InterruptLatencyObserver` measures time from VAD trigger to full silence. The bidirectional event system achieves this by propagating events through the pipeline without waiting for queue drains.
