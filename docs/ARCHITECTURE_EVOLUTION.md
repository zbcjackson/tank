# Architecture Evolution

This document traces how Tank's architecture grew from a single-file Python script
into the current multi-connector, agentic-harness voice assistant platform. It is
organized by era, each bounded by an architectural inflection point (a change in
the core abstraction, not just a new capability).

Dates are taken from the git log. Commit hashes in parentheses mark the
representative commit for each change.

---

## Stage 1 — Sequential Script (Sep 2025)

**Representative commit:** `9894a04` (init), `c2a0425`, `b71c8fa`

Tank started as a conventional synchronous Python CLI assistant. A single
`VoiceAssistant` class composed the whole system:

```
┌──────────────────────────────────────────────────┐
│                  main.py                          │
│                    │                              │
│          ┌─────────▼──────────┐                   │
│          │  VoiceAssistant    │                   │
│          │                    │                   │
│          │ ┌────────────────┐ │                   │
│          │ │WhisperTranscr. │ │  ASR              │
│          │ └────────────────┘ │                   │
│          │ ┌────────────────┐ │                   │
│          │ │ EdgeTTSSpeaker │ │  TTS              │
│          │ └────────────────┘ │                   │
│          │ ┌────────────────┐ │                   │
│          │ │ OpenRouterLLM  │ │  LLM + history    │
│          │ └────────────────┘ │                   │
│          │ ┌────────────────┐ │                   │
│          │ │  ToolManager   │ │  calc/weather/... │
│          │ └────────────────┘ │                   │
│          └────────────────────┘                   │
│                                                   │
│  conversation_loop():                             │
│    record → transcribe → LLM → speak              │
│         (one blocking turn at a time)             │
└──────────────────────────────────────────────────┘
```

Characteristics of this era:

- **One blocking `conversation_loop()`** — record → transcribe → LLM → speak,
  one turn at a time. No streaming, no interruption.
- **Tools invoked via prompt parsing** (`tool_name(params)` string patterns),
  later switched to real OpenAI tool-calling (`edb4f8d`).
- **Config via `.env`** parsed by Pydantic `BaseSettings`.
- **LLM abstraction was homegrown** — `OpenRouterLLM` with its own `Message`
  dataclass. It was renamed and switched to the official `openai` client within
  the same day (`7dcf76d`, `d476309`), which was the first hint that provider
  lock-in would be avoided.

The architecture was effectively "script with classes." It had no notion of
concurrency, no audio pipeline, and no UI beyond stdout.

---

## Stage 2 — Queue-Based Concurrency and the TUI (late Jan 2026)

**Representative commits:** `e9c8a41` (threaded CLI), `7938d84` (Textual TUI),
`f7d680b` (Assistant class), `5ce4f38` (Perception/BrainInputQueue),
`fc18258` (audio scaffold), `8e44878` (Silero VAD)

The first structural rewrite introduced concurrency and decoupled the UI from
the processing core. The motivation was obvious once the project tried to go
full-duplex: a blocking loop cannot both listen and speak.

New core abstractions:

```
┌──────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│                           │                                      │
│                ┌──────────▼──────────┐                           │
│                │      TankApp        │                           │
│                │    (Textual TUI)    │                           │
│                │                     │                           │
│                │ ┌─────┐ ┌────────┐ │                           │
│                │ │Head │ │ConvoArea│ │                           │
│                │ └─────┘ └────────┘ │                           │
│                │ ┌────────────────┐ │                           │
│                │ │  InputFooter   │ │                           │
│                │ └────────────────┘ │                           │
│                └─────────┬──────────┘                           │
│                          │                                       │
│                ┌─────────▼──────────┐                            │
│                │    Assistant       │  (background task mgr)     │
│                │                    │                            │
│                │ ┌────────────────┐ │                            │
│                │ │   Perception   │ │ mic → VAD → segmenter      │
│                │ └───────┬────────┘ │                            │
│                │         │          │                            │
│                │   BrainInputQueue  │ ← async queue              │
│                │         │          │                            │
│                │ ┌───────▼────────┐ │                            │
│                │ │     Brain      │ │ LLM, tools, history        │
│                │ └───────┬────────┘ │                            │
│                │         │          │                            │
│                │   DisplayQueue     │ → TUI updates              │
│                │   AudioOutputQueue │ → speaker                  │
│                │         │          │                            │
│                │ ┌───────▼────────┐ │                            │
│                │ │  Speaker / Mic │ │ sounddevice wrappers        │
│                │ └────────────────┘ │                            │
│                └────────────────────┘                            │
│                                                                  │
│  Key pattern: QueueWorker base class                             │
│    Perception, Brain, Segmenter, Mic all share                   │
│    start/stop/run semantics with bounded queues                  │
└──────────────────────────────────────────────────────────────────┘
```

Key patterns established here:

- **Queues as the backbone.** Components communicated exclusively through
  bounded queues. `BrainInputEvent` unified text input and audio input so the
  Brain had a single consumer loop (`cd10967`).
- **QueueWorker base class** — `Perception`, `Brain`, `Segmenter`, `Mic` all
  inherited a shared worker with `start/stop/run` semantics (`9c8a111`,
  `1f741fc`). This was the first time concurrency was a first-class concept.
- **Textual TUI (`7938d84`).** A decision to ship a rich terminal UI before a
  web UI. It pushed the assistant to separate UI state (display messages) from
  compute (Brain).
- **Audio subsystem emerged** with its own module (`fc18258`), then split into
  `audio/input/` and `audio/output/` (`57c3999`). Voice Activity Detection
  moved from naive energy thresholding to Silero VAD (`8e44878`).
- **Interrupt mechanism** arrived as a `threading.Event` passed between
  workers so speaking could be cancelled when new speech was detected
  (`88a8a1f`).

This era also added Edge TTS (`402ffa5`), streaming ASR via Sherpa-ONNX
(`39cdb56`), speaker identification via voiceprints (`4f0e494`), and streaming
LLM output that was spoken as tokens arrived (`214b0da`). The system was a
fully working voice assistant, but entirely local — nothing ran over a wire.

---

## Stage 3 — Client/Server Split and Monorepo (Feb 2026)

**Representative commits:** `0a43990` (WebSocket API), `ccc174c` (React app),
`1594950` (voice/chat modes), `965026a` (monorepo), `1117e5d` (frontend VAD)

Tank's second structural rewrite split the monolithic Python app into a server
and one or more clients. The trigger was wanting to run the UI in a browser
and eventually in a native macOS window — neither of which can share an
address space with the Python event loop.

```
┌─────────────────────────────────────────────────────────────────┐
│                         Clients                                  │
│                                                                  │
│  ┌─────────────────┐         ┌─────────────────────┐            │
│  │    CLI / TUI     │         │    Web Frontend      │            │
│  │ (Python/Textual) │         │  (React/TypeScript)  │            │
│  │ • sounddevice    │         │ • Web Audio API      │            │
│  │ • Silero VAD     │         │ • AudioWorklet VAD   │            │
│  └────────┬─────────┘         └──────────┬──────────┘            │
│           │                               │                      │
│           │    WebSocket (binary+JSON)     │                      │
│           └───────────────┬───────────────┘                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Backend (FastAPI + Uvicorn)                     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                 Assistant                                  │  │
│  │                                                            │  │
│  │  Perception (VAD → ASR → SpeakerID)                       │  │
│  │       │ BrainInputQueue                                    │  │
│  │       ▼                                                    │  │
│  │  Brain (LLM + tools + streaming)                           │  │
│  │       │ AudioOutputQueue                                   │  │
│  │       ▼                                                    │  │
│  │  Speaker (TTS → playback)                                  │  │
│  │                                                            │  │
│  │  AudioSource / AudioSink factories (pluggable)             │  │
│  │  WebSocket endpoint /ws/{session_id}                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  New: Step model — turn = sequence of typed steps                │
│    (text, thinking, tool, weather) with server-computed step_id  │
└─────────────────────────────────────────────────────────────────┘
```

The WebSocket API (`0a43990`) introduced the messaging protocol that the
project still uses today:

- **Binary frames** — raw Int16 PCM audio, either direction.
- **JSON frames** — `input`, `interrupt`, `transcript`, `text`, `signal`,
  `update`, later `audio` control messages.

Audio was made pluggable on the server with `AudioSource` / `AudioSink`
factories (`f8c9ebe`) so that the same `Assistant` could be driven either by a
local microphone (TUI) or by a queue fed from a WebSocket (web/CLI client).

A few commits later (`965026a`) the repository was flattened into a monorepo:

```
tank/
├── backend/   # FastAPI + audio pipeline (was src/voice_assistant/)
├── web/       # React + Vite + TypeScript
└── cli/       # (Textual TUI, extracted later)
```

The browser client introduced its own concerns that mirror the backend:

- **Mode switching** — voice vs chat — became a first-class UI concept
  (`1594950`, `62d2e7d`).
- **Frontend VAD** (`1117e5d`) ran in an AudioWorklet to drop silent frames
  before they hit the wire, reducing bandwidth and backend load.
- **Reconnection, heartbeat, stopSpeaking, calibration, muting**
  (`e6b39ac`, `66c8941`, `5027653`, `fefb84b`, `74dd589`) — WebSocket
  reliability and UX features that a TUI never needed.

At the same time, the message model was tightened. The old flat "one message
per assistant turn" was refactored into a **Step** model
(`6d49d6c`, `2ef94e2`): each turn is a sequence of typed steps (`text`,
`thinking`, `tool`, `weather`) with a server-computed `step_id` so the
frontend can upsert streaming updates in O(1).

---

## Stage 4 — Pluggable Engines and Config-First Runtime (Mar 2026)

**Representative commits:** `e7faf87` (Sherpa ASR plugin), `b3a29d4`
(speaker embedding plugin), `361f891` (ElevenLabs plugins),
`3b044c0` (extension system), `47a7205` (PluginManager lifecycle)

Until this point the ASR, TTS, and speaker-ID engines were imported directly
from `tank_backend`. Adding a new engine meant touching Assistant construction
code. That coupling became untenable once the team wanted to A/B Whisper vs
Sherpa, CosyVoice vs Edge, ElevenLabs realtime vs Sherpa offline.

The plugin architecture introduced:

```
┌──────────────────────────────────────────────────────────────────┐
│                         Backend                                  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  PluginManager                                           │    │
│  │                                                          │    │
│  │  discover → load → register → validate → instantiate     │    │
│  │                                                          │    │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │    │
│  │  │ plugins.yaml│  │ExtensionReg. │  │  config.yaml    │ │    │
│  │  │ (on/off)    │  │ plugin:ext   │  │  (structured    │ │    │
│  │  └─────────────┘  │ key catalog  │  │   validated     │ │    │
│  │                    └──────────────┘  │   config)       │ │    │
│  │                                      └─────────────────┘ │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Plugin Packages (backend/plugins/)                      │    │
│  │                                                          │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐ │    │
│  │  │asr-sherpa│ │tts-edge  │ │speaker-  │ │tts-        │ │    │
│  │  │          │ │          │ │sherpa    │ │elevenlabs  │ │    │
│  │  │[tool.tank│ │[tool.tank│ │[tool.tank│ │[tool.tank  │ │    │
│  │  │ manifest]│ │ manifest]│ │ manifest]│ │ manifest]  │ │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └────────────┘ │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  New: .env → secrets only; config.yaml → structured runtime cfg  │
│  New: Sandbox abstraction (Docker, Seatbelt, Bubblewrap)         │
└──────────────────────────────────────────────────────────────────┘
```

- **`backend/plugins/<name>/`** — each engine as an installable package with a
  `pyproject.toml` containing a `[tool.tank]` manifest declaring the
  extensions it provides (`3b044c0`).
- **`ExtensionRegistry`** — a catalog keyed by `"plugin:ext"` strings (e.g.
  `"asr-sherpa:asr"`). Manifests, not instances, are registered at startup.
- **`PluginManager`** (`47a7205`) — a real lifecycle: `discover → load →
  register → validate → instantiate`. A generated `plugins.yaml` acts as the
  enable/disable switchboard.
- **`config.yaml`** replaced most `.env`-driven runtime settings
  (`6a4c144`). `.env` kept only secrets; YAML held structured,
  validated-against-registry config. The loader went through several iterations
  (`2afa31c`, `b62343a`, `bb1f7be`) and eventually landed on typed dataclasses
  with a `from_dict` factory per section.
- **Per-slot enable/disable** — ASR, TTS, and speaker-ID slots each gained an
  `enabled` flag. The frontend learns backend capabilities from the `ready`
  signal and hides voice mode when ASR is off (`3b044c0`).

This era also produced the sandbox abstraction (`51377e0`, `951a981`) that
gave the LLM code-execution tools. It started as a Docker-only `sandbox_exec`
and grew platform backends for macOS (Seatbelt) and Linux (Bubblewrap) behind
a common `Sandbox` protocol — the same extension-over-modification pattern
applied to runtime isolation.

---

## Stage 5 — The Pipeline Architecture (mid Mar 2026)

**Representative commits:** `f8a45ca` (roadmap),
`7a5a67e` (Bus + Processor + observers), `72ef903` (processor wrappers),
`1ae1ee1` (migrate v1 to v2), `d91e57f` (Brain as native Processor),
`61ffeab` (V2 → Assistant), `5b59e17` (fan-out/fan-in)

The queue-based worker model from Stage 2 had carried the project a long way,
but several pressures compounded:

- QoS and health monitoring were bolted on per component.
- Backpressure was ad hoc — workers just pushed into unbounded or hand-sized
  queues.
- Interruption still relied on a shared `threading.Event`.
- Adding parallel branches (ASR + speaker-ID on the same audio) required
  custom wiring.

A 1,684-line roadmap document (`f8a45ca`) laid out a GStreamer-inspired
redesign. The implementation landed as a new abstraction layer:

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Pipeline (Layer 1)                           │
│                                                                      │
│  Audio In                                                            │
│     │                                                                │
│     ▼                                                                │
│  ┌──────────┐    ┌────┐    ┌──────────┐  ┌─────────────┐            │
│  │VADProc.  │───►│ Q  │───►│ASRProc.  │  │SpeakerIDProc│            │
│  │(interrupt│    └────┘    │          │  │             │            │
│  │ upstream)│              └────┬─────┘  └──────┬──────┘            │
│  └──────────┘                   │ FanOut          │ FanOut           │
│                                 └────────┬────────┘                  │
│                                          ▼                           │
│                                ┌──────────────────┐                  │
│                                │ASRSpeakerMerger  │                  │
│                                └────────┬─────────┘                  │
│                                         │                            │
│                                    ┌────┘                            │
│                                    ▼                                 │
│                                ┌──────────┐                          │
│                                │BrainProc.│  (Layer 2 bridge)        │
│                                └────┬─────┘                          │
│                                     │                                │
│                                ┌────▼─────┐                          │
│                                │EchoGuard │  (self-echo filter)      │
│                                └────┬─────┘                          │
│                                     │                                │
│                                ┌────▼─────┐                          │
│                                │ Q        │                          │
│                                └────┬─────┘                          │
│                                     │                                │
│                                ┌────▼─────┐                          │
│                                │TTSProc.  │  (QoS feedback)          │
│                                └────┬─────┘                          │
│                                     │                                │
│                                ┌────▼─────┐                          │
│                                │Playback  │  (fade-out on interrupt) │
│                                └────┬─────┘                          │
│                                     │                                │
│                                  Audio Out                           │
│                                                                      │
│  Cross-cutting:                                                      │
│  ┌───────────────────────────────────────────────────────────────┐   │
│  │  Bus ◄── LatencyObserver, HealthMonitor, AlertingObserver    │   │
│  │       ◄── MetricsCollector, TurnTracker, InterruptLatency     │   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Core types:  Processor (ABC)  ·  FlowReturn (OK/EOS/FLUSH/ERROR)   │
│               PipelineEvent (bidirectional)  ·  ThreadedQueue        │
│               FanOutQueue  ·  PipelineBuilder                        │
└──────────────────────────────────────────────────────────────────────┘
```

The key design choices:

- **Queue = thread boundary.** Inserting a `ThreadedQueue` between two
  processors creates a new thread. Pipeline topology decides threading, not
  hardcoded `threading.Thread()` calls.
- **FlowReturn** propagates backpressure, EOS, and errors the way GStreamer
  does. No more silent queue overflow.
- **Bidirectional events.** Data flows downstream; interrupt/flush events flow
  upstream from VAD back to Playback. Each processor handles events in
  isolation (Playback fade-out, TTS cancel, Brain LLM cancel). The old shared
  `threading.Event` was retired.
- **Bus for observability.** Processors post `BusMessage`s — metrics,
  `ui_update`s, `qos` warnings, errors — without knowing who listens.
  Observers subscribe. This is what made health monitoring, latency
  observation, and QoS-driven graceful degradation orthogonal to the data
  path.
- **Fan-out / fan-in** (`5b59e17`). ASR and speaker-ID now run in parallel
  branches and reconverge in `ASRSpeakerMerger`, which is just another
  Processor.

The migration was two-phased: first the old `AudioInput`/`Brain`/`AudioOutput`
workers were wrapped as Processors (`72ef903`), then the wrappers were
collapsed (`d91e57f`), and the parallel `AssistantV2` was renamed to
`Assistant`, deleting the old one (`1ae1ee1`, `61ffeab`). After this era the
backend pipeline has not fundamentally changed.

---

## Stage 6 — Agents, Approval, and Observability (Mar 2026)

**Representative commits:** `a6bf83a` (specialized agents + router + graph),
`b1ec3e5` (approval system), `8032dab` (health + QoS), `8ddaf1a` (Langfuse),
`a0a4273` (three-layer doc), `5b847f6` (checkpointing + summarization LLM)

With a stable pipeline, the Brain was extracted into a dedicated agent
orchestration layer. The first iteration introduced **router + specialized
agents** (Chat, Search, Task, Code) with an `AgentGraph` that picked an agent
per turn and streamed its output back to TTS.

```
┌───────────────────────────────────────────────────────────────────┐
│                         Three-Layer Model                         │
│                                                                   │
│  Layer 1: Audio Pipeline (unchanged from Stage 5)                │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  VAD → ASR → BrainProcessor → EchoGuard → TTS → Playback  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                    │
│                              ▼                                    │
│  Layer 2: Agent Orchestration                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  AgentGraph                                                 │  │
│  │    │                                                        │  │
│  │    ▼                                                        │  │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐   │  │
│  │  │ChatAgent│  │SearchAgent│  │TaskAgent │  │ CodeAgent │   │  │
│  │  └────┬────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘   │  │
│  │       │             │             │              │          │  │
│  │       └─────────────┴─────────────┴──────────────┘          │  │
│  │                           │                                  │  │
│  │                  ApprovalManager                            │  │
│  │                  (per-tool policy gate)                      │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                    │
│                              ▼                                    │
│  Layer 3: LLM Transport                                          │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  AsyncOpenAI  ·  retry  ·  tiktoken  ·  Langfuse tracing   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Cross-cutting:                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Bus + Observers                                            │  │
│  │  HealthAggregator · QoS feedback · Checkpointing            │  │
│  │  Conversation summarization · Langfuse auto-tracing         │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

Critical companions:

- **Approval system** (`b1ec3e5`). Every tool can declare an approval
  policy (`always_approve`, `require_approval`, `require_approval_first_time`).
  The agent pauses and emits `APPROVAL_NEEDED`; a REST endpoint and a voice
  "yes/no" path both feed the `ApprovalManager`.
- **Health + QoS** (`8032dab`). Queue-size, stuck-detection, and per-processor
  error counters are aggregated by `HealthAggregator` and exposed at
  `/health?detail=true`. TTS posts `qos` bus messages when its queue fills;
  Brain subscribes and skips optional tool calls — graceful degradation
  without coupling.
- **Langfuse** (`8ddaf1a`). Auto-tracing the `AsyncOpenAI` client via monkey
  patch, so every LLM call shows up with full prompts, tokens, cost, and tool
  calls without code changes anywhere in the Brain.

At the same time the LLM transport was simplified to a thin layer: raw
`AsyncOpenAI` with retry (`5b847f6`), token counting via `tiktoken`, and a
dedicated `summarization` LLM profile for history compaction. This is the
"Layer 3" the architecture document would later describe explicitly.

The result was the three-layer model documented in `a0a4273` and still in
force today:

```
Layer 1 — Audio Pipeline     (GStreamer-inspired, hard real-time)
Layer 2 — Agent Orchestration (AgentGraph, approval gates, streaming)
Layer 3 — LLM Transport       (AsyncOpenAI + retry + Langfuse)
         ── Bus + Observers (cross-cutting)
```

---

## Stage 7 — Router Out, Sub-Agent-As-Tool In (Apr 2026)

**Representative commits:** `1c3b334` (design doc), `44fedc1` (back to
single agent, no router), `720bba7` (learnings from Claude Code),
`8443dbd` (agent_tool/definition/runner refactor), `2ac52ec` (verifier +
parallel agents), `1f88969` (skills)

The first multi-agent attempt used a `router.py` that ran a keyword/LLM
classifier each turn and dispatched to one of four hard-coded Python classes
(`ChatAgent`, `SearchAgent`, `TaskAgent`, `CodeAgent`), each with its own
prompt file. It ran for about two weeks.

The retreat (`44fedc1`, "back to single agent, no router") deleted the
router, the specialized Python classes, and their prompts. It kept the
`AgentGraph` — which was always a thin orchestrator — and refocused it on a
single `ChatAgent` that sees every tool and lets the LLM decide.

```
┌───────────────────────────────────────────────────────────────────┐
│  BEFORE (Stage 6):                                                │
│  ┌─────────┐                                                      │
│  │ Router  │──► keyword/LLM classifier                            │
│  └────┬────┘                                                      │
│       │ dispatches to one of:                                     │
│  ┌────▼──────────────────────────────────────────────────┐        │
│  │ ChatAgent │ SearchAgent │ TaskAgent │ CodeAgent        │        │
│  │ (Python)  │ (Python)    │ (Python)  │ (Python)         │        │
│  │ own prompt│ own prompt  │ own prompt│ own prompt       │        │
│  └───────────────────────────────────────────────────────┘        │
│                                                                   │
│  AFTER (Stage 7):                                                 │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │ ChatAgent (sees ALL tools)                                │    │
│  │                                                           │    │
│  │ Tools: calculator, weather, web_search, ...               │    │
│  │        + agent_tool (sub-agents as tools)                 │    │
│  │          │                                                │    │
│  │          ├──► Task(coder, ...)     ← markdown definition  │    │
│  │          ├──► Task(researcher, ...) ← markdown definition │    │
│  │          └──► Task(verifier, ...)  ← markdown definition │    │
│  │                                                           │    │
│  │ LLM decides delegation, not upstream router               │    │
│  └───────────────────────────────────────────────────────────┘    │
│                                                                   │
│  Agent definitions are DATA, not classes:                         │
│  backend/agents/*.md  (coder.md, researcher.md, verifier.md)      │
│  → loaded by AgentsFileResolver → AgentDefinition → AgentRunner   │
└───────────────────────────────────────────────────────────────────┘
```

What replaced the router was not the absence of multi-agent capability, but a
different shape of it, borrowed from Claude Code (`720bba7`,
`docs/CLAUDE_CODE_LEARNINGS.md`):

- **Agent definitions are data, not classes.** `backend/agents/*.md`
  (`coder.md`, `researcher.md`, `tasker.md`, `verifier.md`) declare sub-agents
  as markdown with frontmatter, loaded by an `AgentsFileResolver` (`d313435`).
- **`AgentDefinition` + `AgentRunner`** (`8443dbd`) provide a generic way to
  run any defined agent, with configurable `max_depth` and `max_concurrent`
  (visible in today's `config.yaml`).
- **`agent_tool`** exposes sub-agents to the main agent *as tools*. The main
  ChatAgent sees `Task(coder, ...)` the same way it sees `web_search(...)` —
  the LLM decides when delegation is worth the cost, not an upstream router.
- **Verifier and parallel patterns** (`2ac52ec`) became optional delegation
  targets instead of mandatory pipeline stages.

The lesson this stage encodes, in the form the codebase actually took: **the
router was the wrong place to put intelligence.** Routing by code is cheap but
brittle; routing by LLM-tool-choice is more expensive per turn but has no
classification floor because the same model that would do the work also does
the dispatching. The single-agent runtime today is not "no multi-agent" — it's
"multi-agent expressed as tools."

The pattern — try the elaborate structure, measure, reshape into something
simpler — recurs in Stage 10.

---

## Stage 8 — Skills, Prompts, Context, MCP (mid–late Apr 2026)

**Representative commits:** `1f88969` (skills), `d606d71` (MCP),
`628a5cc` (PromptAssembler), `f52899a` (context subsystem),
`6d8c3ac` (LLMContext), `04ef8ab` (preferences), `e099b77` (auto learning)

With a single agent carrying the load, the focus shifted to what it knows and
how its context is managed. Four subsystems landed in quick succession:

```
┌───────────────────────────────────────────────────────────────────┐
│                     Agent Orchestration (Layer 2)                 │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ ChatAgent                                                   │  │
│  │   │                                                         │  │
│  │   ├── PromptAssembler                                      │  │
│  │   │     AGENTS.md + SOUL.md + USER.md + cached base         │  │
│  │   │     (per-turn assembly, sanitizable, cache-friendly)    │  │
│  │   │                                                         │  │
│  │   ├── ContextManager                                       │  │
│  │   │     history · summarization · compaction · persistence  │  │
│  │   │     → LLMContext (messages sent to LLM)                 │  │
│  │   │                                                         │  │
│  │   ├── SkillSystem                                          │  │
│  │   │     backend/skills/ → SKILL.md + references/templates   │  │
│  │   │     use_skill tool → registry → load → execute          │  │
│  │   │                                                         │  │
│  │   ├── MCP Client                                           │  │
│  │   │     mount MCP servers as tool groups                    │  │
│  │   │     lifecycle management per connection                 │  │
│  │   │                                                         │  │
│  │   ├── Preferences                                          │  │
│  │   │     per-user store · auto-learning · staleness decay    │  │
│  │   │                                                         │  │
│  │   └── ToolManager                                          │  │
│  │         native tools + skill tools + MCP tools              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Brain is now a thin orchestrator —                               │
│  all "what to know" logic lives in dedicated components           │
└───────────────────────────────────────────────────────────────────┘
```

- **Skills** (`1f88969`). A Claude-Code-style skill system: skill packages
  with `SKILL.md`, references, templates, and a `use_skill` tool. The registry
  loads them from `backend/skills/`, remote sources can be pulled in
  (`f1b3105`), and skills can be reviewed by a dedicated reviewer agent
  (`6f98500`).
- **MCP client** (`d606d71`). A proxy layer that mounts Model Context Protocol
  servers as tool groups. The LLM sees MCP tools alongside native ones; the
  client manager handles connection lifecycle.
- **PromptAssembler** (`628a5cc`). Instead of a monolithic `system_prompt.txt`,
  the prompt is assembled per turn from `AGENTS.md`, `SOUL.md`, `USER.md`,
  and a cached base. It can be sanitized and is cache-friendly for prompt
  caching at the LLM layer.
- **Context subsystem** (`f52899a`, `6d8c3ac`). Brain no longer owns the
  conversation state. A `ContextManager` handles history, summarization,
  compaction, and persistence. `LLMContext` wraps the actual messages sent to
  the LLM and supports compaction and cache-friendly slicing.
- **Preferences** (`04ef8ab`, `e099b77`). Per-user preference store with
  automatic learning and staleness decay — another capability the agent can
  use as a tool.

The net effect: the Brain became a thin orchestrator again, and all the
"what should the model know right now" logic moved into dedicated components
with their own tests.

---

## Stage 9 — Security, Jobs, Channels (late Apr – early May 2026)

**Representative commits:** `6148df0` (network + audit), `10c1607` (tool
groups), `750337c` (autonomous jobs), `40b3066` (security verdict + resolvers),
`0891624` (channels)

As the agent gained real capabilities (file I/O, shell, network), security
stopped being something to review case by case:

```
┌────────────────────────────────────────────────────────────────────┐
│                    Security Architecture                            │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  PolicyVerdict (unified)                                     │  │
│  │                                                              │  │
│  │  AccessLevel: ALLOW | REQUIRE_APPROVAL | DENY                │  │
│  │                                                              │  │
│  │  ┌──────────────┐ ┌────────────┐ ┌────────────┐             │  │
│  │  │CommandSec.   │ │FileAccess  │ │Network     │             │  │
│  │  │Policy        │ │Policy      │ │AccessPolicy│             │  │
│  │  └──────┬───────┘ └──────┬─────┘ └──────┬─────┘             │  │
│  │         │                │               │                   │  │
│  │         └────────────────┼───────────────┘                   │  │
│  │                          ▼                                   │  │
│  │                  ┌───────────────┐                           │  │
│  │                  │ApprovalResolver│                          │  │
│  │                  │ (protocol)     │                          │  │
│  │                  └───────┬───────┘                           │  │
│  │                          │                                   │  │
│  │            ┌─────────────┼──────────────┐                   │  │
│  │            ▼             ▼              ▼                   │  │
│  │     AlwaysApprove  AlwaysDeny     Interactive               │  │
│  │     (autonomous)   (locked down)  (voice/chat)              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌────────────────────────┐  ┌─────────────────────────────────┐  │
│  │  Audit Log             │  │  Tool Groups                    │  │
│  │  every allow/deny →    │  │  shared dependencies:           │  │
│  │  Bus → observability   │  │  File · Web · Sandbox · Skill   │  │
│  └────────────────────────┘  └─────────────────────────────────┘  │
│                                                                    │
│  ┌────────────────────────┐  ┌─────────────────────────────────┐  │
│  │  Autonomous Jobs       │  │  Channels                       │  │
│  │  cron schedule → agent │  │  named conversations with       │  │
│  │  run → deliver result  │  │  read state + notifications     │  │
│  └────────────────────────┘  └─────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

- **Typed security verdicts** (`40b3066`). `AccessLevel` enum + `PolicyVerdict`
  unifies `ALLOW / REQUIRE_APPROVAL / DENY` across command, file, network, and
  tool-approval policies. Resolvers (`AlwaysApprove`, `AlwaysDeny`,
  `Interactive`) plug in different approval behaviors for interactive vs
  autonomous modes.
- **Audit log** (`6148df0`). Every allow/deny decision goes to the Bus, so it
  ends up in the same observability path as latency metrics.
- **Tool groups** (`10c1607`). Tools that share construction dependencies
  (file tools need an approval callback; web tools need credentials; sandbox
  tools need a backend) are grouped, and the manager wires dependencies once.

Autonomous jobs (`750337c`) introduced the ability to run the agent on a cron
schedule, with results delivered to a channel. This is when Tank stopped being
a turn-by-turn interactive assistant and started being a scheduled agent
runtime. Channels themselves (`0891624`) came a week later — named
conversations with their own read state and notification tracking, decoupling
"a session" from "a WebSocket connection" that had already happened at the
lifecycle level earlier (`439c10f`).

---

## Stage 10 — Unified Persistence (May 2026)

**Representative commit:** `c87cc1b`

The per-feature SQLite sprawl — `conversations.db`, `channels.db`, `jobs.db`,
`speakers.db`, each with its own ad-hoc schema, migrations, and connection
management — was consolidated into a single SQLAlchemy 2.0 ORM stack backed
by one database at `~/.tank/tank.db`.

```
┌───────────────────────────────────────────────────────────────────┐
│                    Persistence Layer                               │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Database (engine + session factory)                         │ │
│  │  sqlite+pysqlite:///~/.tank/tank.db                          │ │
│  │  or: postgresql+psycopg://user:pass@host/tank                │ │
│  │  WAL mode · FK on · connection listener                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                              │                                    │
│                    ┌─────────▼──────────┐                         │
│                    │   Base             │                         │
│                    │ (DeclarativeBase)  │                         │
│                    └─────────┬──────────┘                         │
│                              │                                    │
│          ┌───────────────────┼───────────────────┐                │
│          ▼                   ▼                   ▼                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ models/      │  │ models/      │  │ models/      │            │
│  │ Conversation │  │ Channel      │  │ Job          │            │
│  │ Row          │  │ Row          │  │ Row          │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                 │                     │
│         ▼                 ▼                 ▼                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ ConvStore    │  │ ChannelStore │  │ JobStore     │            │
│  │ (frozen DC)  │  │ (frozen DC)  │  │ (frozen DC)  │            │
│  └──────────────┘  └──────────────┘  └──────────────┘            │
│         + SpeakerRepository (voiceprints/embeddings)              │
│                                                                   │
│  Infrastructure:                                                  │
│  ┌────────────────┐  ┌───────────────┐  ┌──────────────────┐     │
│  │ migrate.py     │  │ bootstrap.py  │  │ migrations/      │     │
│  │ run_migrations │  │ legacy → new  │  │ Alembic env +    │     │
│  │ (startup)      │  │ (first run)   │  │ versioned scripts│     │
│  └────────────────┘  └───────────────┘  └──────────────────┘     │
│                                                                   │
│  Boundary: Stores return frozen dataclasses, callers never        │
│  see Mapped[...] or Session objects. Postgres swap = URL change.  │
└───────────────────────────────────────────────────────────────────┘
```

The stores kept their public APIs — callers never see `Mapped[...]` columns.
That boundary preservation is what made the Postgres swap a URL change:

```
sqlite+pysqlite:///~/.tank/tank.db
  → postgresql+psycopg://user:pass@host/tank
```

This mirrors the reversal in Stage 7: the architecture took on four
specialized databases when feature boundaries demanded it, then collapsed them
once the boundaries had stabilized and the cost of four schemas exceeded the
cost of one.

---

## Stage 11 — Connectors: Multi-Platform Inbound/Outbound (May 2026)

**Representative commits:** `e53851e` (Telegram), `e629acc` (Slack),
`cfdb5b7` (Discord), `60e79aa` (Feishu), `a3c621b` (WeChat),
`5fd5b50` (connector SDK refactor)

Until this point Tank was a single-user voice assistant with one client at a
time. The connector framework turned it into a multi-platform agent that
receives messages from chat platforms and replies in-kind — text, images, and
voice. Each platform is a plugin with a shared SDK.

```
┌────────────────────────────────────────────────────────────────────┐
│                        External Platforms                           │
│                                                                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Telegram │ │  Slack   │ │ Discord  │ │  Feishu  │ │ WeChat  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────┘ │
│       │             │            │             │            │       │
│  ┌────▼─────────────▼────────────▼─────────────▼────────────▼────┐ │
│  │                 ConnectorManager                              │ │
│  │                                                               │ │
│  │  lifecycle + dispatch for configured connectors               │ │
│  │  inbound messages → SessionMapper → ConnectionManager         │ │
│  │  outbound streams → StreamConsumer → platform API             │ │
│  │                                                               │ │
│  │  ┌───────────────────────────────────────────────────────┐    │ │
│  │  │  Connector (ABC, from tank_contracts.connector)       │    │ │
│  │  │                                                       │    │ │
│  │  │  • receive() → MessageEvent (text/audio/image)        │    │ │
│  │  │  • send() → SendResult (text/image/voice)             │    │ │
│  │  │  • capabilities: {voice_in, voice_out, images, ...}   │    │ │
│  │  └───────────────────────────────────────────────────────┘    │ │
│  │                                                               │ │
│  │  VoiceBridge: platform audio (Ogg/Opus) ←→ Tank PCM (16kHz)  │ │
│  │  DynamicAllowlist: admin-granted per-instance access          │ │
│  │  ConnectorAllowlistPolicy: security gate per connector        │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│                              ▼                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  SessionMapper                                                │ │
│  │  platform_user@platform → Tank session_id                    │ │
│  │  maps external identities to internal conversations           │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                     │
│                              ▼                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  ToolOutputObserver (bus subscriber)                          │ │
│  │  tool_completed → inspect ToolResult for ContentBlocks        │ │
│  │  → outbound_attachment → ImageDispatcher → platform send()    │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  Each connector is a plugin (backend/plugins/connector-<name>/)    │
│  Shared SDK in tank_contracts.connector_sdk/                       │
│  Additive: WebSocket entrypoint still works unchanged              │
└────────────────────────────────────────────────────────────────────┘
```

The connector framework introduced several new abstractions:

- **`Connector` ABC** lives in `tank_contracts.connector` — a separate
  workspace package so plugins depend on the contract alone, not the full
  backend. This mirrors the plugin manifest pattern from Stage 4.
- **`ConnectorManager`** owns the lifecycle of all configured connectors.
  Inbound messages route through `SessionMapper` into the existing
  `ConnectionManager`, so connectors share the same session/assistant path
  as WebSocket clients — no parallel agent infrastructure needed.
- **`StreamConsumer`** bridges outbound streaming replies (tokens, tool
  results) to platform-specific send calls.
- **`VoiceBridge`** converts between platform-native audio (Telegram's
  Ogg/Opus) and Tank's internal PCM (float32, 16kHz mono) via pydub/ffmpeg.
  This lets voice messages flow in from Telegram and voice replies flow out.
- **`ToolOutputObserver`** subscribes to `tool_completed` bus events,
  inspects `ToolResult` for non-text `ContentBlock`s (images, documents),
  and re-publishes as `outbound_attachment` events. This keeps `ToolManager`
  closed for modification — adding a new content kind means adding an
  observer, not editing the manager.
- **`DynamicAllowlist`** + **`ConnectorAllowlistPolicy`** extend the
  `PolicyVerdict` system from Stage 9 with per-connector identity gates.

The connector architecture is **additive**: a connector-free deploy behaves
exactly as before. The WebSocket endpoint, the web UI, and the TUI continue
to work unchanged.

---

## Stage 12 — Agentic Harness: Hooks, Guardrails, Toolsets (Jun 2026)

**Representative commits:** `fbb1b14` (shell hooks), `348bdd8` (agentic
harness patterns), `aad93f6` (composable toolset profiles),
`c3fd072` (tool metadata + loop guardrails + durable approvals),
`bf69900` (TokenUsageObserver), `da46f92` (session lifecycle hooks),
`09f9e95` (pre_llm_call hook), `510436b` (configurable guardrail thresholds)

With connectors bringing in unattended users and long-running autonomous jobs,
the agent needed production-grade safety rails — not just per-tool approval,
but lifecycle hooks, composable tool profiles, loop detection, and cost
tracking. This era introduced the "agentic harness": the machinery that wraps
the agent's tool calls and LLM interactions in configurable, extensible
guards.

```
┌────────────────────────────────────────────────────────────────────┐
│                       Agentic Harness                               │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    HookManager                               │  │
│  │                                                              │  │
│  │  config.yaml → hooks: block                                  │  │
│  │                                                              │  │
│  │  Events: pre_tool_call → post_tool_call → pre_llm_call      │  │
│  │          session_start → session_end                         │  │
│  │                                                              │  │
│  │  ┌────────────────────────────────────────────────────┐      │  │
│  │  │ Shell Hook:                                        │      │  │
│  │  │  JSON on stdin → {action:"block", reason:"..."}    │      │  │
│  │  │                → {context:"..."} (inject into LLM)  │      │  │
│  │  │  JSON on stdout (optional)                          │      │  │
│  │  │  Timeout protection + consent/allowlist              │      │  │
│  │  └────────────────────────────────────────────────────┘      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Toolset Profiles                                │  │
│  │                                                              │  │
│  │  config.yaml → toolsets: block                               │  │
│  │                                                              │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐      │  │
│  │  │  "full"      │ │  "safe"      │ │  "readonly"      │      │  │
│  │  │  all tools   │ │  no shell    │ │  read + search   │      │  │
│  │  │  (default)   │ │  no write    │ │  only            │      │  │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘      │  │
│  │                                                              │  │
│  │  Each agent definition references a toolset profile           │  │
│  │  ToolManager.get_openai_tools(toolset=...) → filtered list   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Loop Guardrails                                 │  │
│  │                                                              │  │
│  │  • max_consecutive_calls: same tool N times → auto-stop      │  │
│  │  • max_total_tool_calls: per-turn budget                     │  │
│  │  • configurable thresholds via config.yaml                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Cost & Usage Tracking                           │  │
│  │                                                              │  │
│  │  TokenUsageObserver (bus subscriber)                         │  │
│  │    → per-turn token counts + cumulative cost                 │  │
│  │    → posted to Bus for dashboards / alerting                 │  │
│  │                                                              │  │
│  │  Tool metadata: get_metadata() on every tool                 │  │
│  │    → risk_level, estimated_latency, side_effects             │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

The harness components:

- **Shell hooks** (`fbb1b14`). User-defined scripts that fire on
  `pre_tool_call`, `post_tool_call`, `pre_llm_call`, and session lifecycle
  events. Scripts receive JSON on stdin and can return JSON on stdout to block
  execution (`{action: "block"}`) or inject context (`{context: "..."}`).
  Timeout protection kills runaway scripts; consent/allowlist gates first-use
  approval (`8cfa256`).
- **Composable toolset profiles** (`aad93f6`). Named profiles in `config.yaml`
  that filter the tool registry — `"full"` (all tools), `"safe"` (no shell,
  no writes), `"readonly"` (read + search only). Each agent definition
  references a profile, so the coder sub-agent gets a different surface than
  the researcher.
- **Tool metadata** (`c3fd072`, `8cb543b`). Every tool now declares
  `get_metadata()` returning risk level, estimated latency, and side effects.
  The guardrail system uses this to make informed decisions.
- **Loop guardrails** (`c3fd072`). Configurable limits on consecutive same-tool
  calls and total per-turn tool calls. Thresholds exposed in `config.yaml`
  (`510436b`).
- **TokenUsageObserver** (`bf69900`). Bus subscriber that tracks per-turn and
  cumulative token counts and cost, posted back to the Bus for dashboards or
  alerting.
- **Session lifecycle hooks** (`da46f92`). `session_start` and `session_end`
  bus events let hooks run setup/teardown logic when conversations begin and
  end.

The agentic harness is the operational layer between "the agent can do things"
and "the agent can do things safely in production with unattended users." It
extends the policy system from Stage 9 with runtime hooks and the observability
system from Stage 6 with cost tracking.

---

## Stage 13 — Persistent Memory and Proactive Delivery (Jun 2026)

**Representative commits:** `518a6e1` (mem0 integration),
`f6c8016` (NotificationHub), `b25bdd2` (ask_user tool),
`ea1f5b5` (WorkerRunRow), `ce9495f` (compaction models),
`c445d00` (conversation titles)

The final era in the current evolution addresses two gaps that became acute
once connectors brought in long-lived users: memory across sessions and
proactive delivery of background results.

```
┌────────────────────────────────────────────────────────────────────┐
│                     Memory & Proactive Layer                       │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  MemoryService (mem0 wrapper)                                │  │
│  │                                                              │  │
│  │  store_turn()  → persists conversation facts                │  │
│  │  recall()      → hybrid search (vector + keyword)           │  │
│  │  get_all()     → dump all memories for user                 │  │
│  │  consolidate() → background merge of redundant memories     │  │
│  │                                                              │  │
│  │  All mem0 calls wrapped in asyncio.to_thread()              │  │
│  │  (mem0 is synchronous under the hood)                       │  │
│  │                                                              │  │
│  │  Tools: remember · get_user_memory · consolidate_memory     │  │
│  │         get_context_usage · compact_context                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  NotificationHub                                             │  │
│  │                                                              │  │
│  │  Proactive event delivery to connected clients               │  │
│  │                                                              │  │
│  │  Sources:                                                    │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐     │  │
│  │  │Job result│  │Worker events │  │Connector messages  │     │  │
│  │  │(cron)    │  │(background)  │  │(inbound from users)│     │  │
│  │  └────┬─────┘  └──────┬───────┘  └─────────┬──────────┘     │  │
│  │       │               │                     │                 │  │
│  │       └───────────────┼─────────────────────┘                 │  │
│  │                       ▼                                       │  │
│  │               NotificationHub                                 │  │
│  │                       │                                       │  │
│  │               ┌───────▼────────┐                              │  │
│  │               │ push via       │                              │  │
│  │               │ WebSocket      │                              │  │
│  │               │ OR connector   │                              │  │
│  │               │ send()         │                              │  │
│  │               └────────────────┘                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Interaction Patterns                                        │  │
│  │                                                              │  │
│  │  ask_user tool: agent → question → user prompt → response   │  │
│  │    (worker-initiated clarification for long tasks)           │  │
│  │                                                              │  │
│  │  Conversation titles: auto-generated from first exchange    │  │
│  │  Context compaction: get_context_usage → compact_context    │  │
│  │  WorkerRunRow: ORM model for background worker run history  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

Key components:

- **MemoryService** (`518a6e1`). Persistent cross-session memory using mem0.
  `store_turn()` persists conversation facts; `recall()` uses hybrid search
  (vector + keyword) to surface relevant memories; `consolidate()` runs
  background merges of redundant entries. All mem0 calls are wrapped in
  `asyncio.to_thread()` because mem0 is synchronous.
- **Memory tools** — `remember`, `get_user_memory`, `consolidate_memory`,
  `get_context_usage`, `compact_context` — give the agent explicit control
  over what it remembers and how compacted its context window is.
- **NotificationHub** (`f6c8016`). Proactive event delivery to connected
  clients. Job results, background worker events, and connector messages all
  route through the hub, which pushes via WebSocket or connector `send()`.
  This is the final piece that makes autonomous jobs and connector-driven
  conversations feel interactive rather than batch.
- **ask_user tool** (`b25bdd2`, `a7e11f1`). Worker-initiated clarification:
  when a long-running agent task hits an ambiguity, it pauses and asks the
  user a question rather than guessing. The user's answer is injected back
  into the agent's context.
- **Conversation titles** (`c445d00`). Auto-generated from the first exchange,
  stored via the persistence layer.
- **Context compaction** (`ce9495f`). ORM models and tools for monitoring
  context window usage and triggering compaction when limits are approached.
- **WorkerRunRow** (`ea1f5b5`). ORM model for background worker run history,
  giving the persistence layer visibility into autonomous job execution.

---

## Cross-Cutting Trends

Looking at the sequence end to end, five recurring moves show up:

1. **Concurrency made explicit.** Sync loop → queue workers → pipeline
   processors. Each step made thread boundaries declarative rather than
   implicit.
2. **Data flow made bidirectional.** Fire-and-forget queues → Bus for
   observability → typed `PipelineEvent` for upstream control → typed
   `PolicyVerdict` for security → shell hooks for external interception.
   Control, metrics, security decisions, and hook context all travel on named
   buses, not hidden channels.
3. **Extension over modification.** Plugin manifests for engines, tool groups
   for tools, sandbox backends for runtime isolation, ORM models for
   persistence domains, connector plugins for platforms, toolset profiles for
   agent scoping, shell hooks for lifecycle interception. Adding a capability
   is a manifest, group, or subscriber, not an edit to a central class.
4. **Trim what didn't earn its keep — and sometimes reshape it.** The
   keyword router was deleted in favor of LLM-driven tool choice; the
   specialized agent classes were replaced by markdown-defined sub-agents
   exposed as tools; the four per-feature SQLite files collapsed into one
   SQLAlchemy database. Each of these was a genuine design decision at the
   time, and each was reverted or reshaped when the cost outweighed the
   benefit. The project treats architectural complexity as reversible.
5. **The boundary moves outward.** Each era pushes the system boundary one
   layer further from the core: from Python classes to concurrent workers,
   from workers to networked clients, from clients to chat platforms, from
   platforms to proactive delivery and persistent memory. The core (pipeline +
   agent + LLM) stays stable while the perimeter expands.

## Today (Jun 2026)

```
Clients: CLI (Textual) · Web (React 19 + Vite) · macOS (Tauri 2)
         · Telegram · Slack · Discord · Feishu · WeChat
         │
         ▼  WebSocket (binary PCM + JSON signals)
         ▼  Connector SDK (platform-specific protocols)
┌─────────────────────────────────────────────────────────────────┐
│ Backend (FastAPI + Uvicorn)                                     │
│                                                                 │
│ Layer 1 — Audio Pipeline                                        │
│   VAD → Q → ASR ┬→ SpeakerID ──┐                                │
│                 └→────────→ ASRSpeakerMerger → Q → Brain        │
│   Playback ← Q ← TTS ← EchoGuard ← Brain                        │
│                                                                 │
│ Layer 2 — Agent Orchestration                                   │
│   AgentGraph → ChatAgent (all tools) + Approval gates           │
│   Skills · MCP · Tool groups · Toolsets · Hooks                 │
│   Memory (mem0) · Preferences · Context compaction              │
│                                                                 │
│ Layer 3 — LLM Transport                                         │
│   AsyncOpenAI (Langfuse) · retry · tiktoken · token usage       │
│                                                                 │
│ Cross-cutting                                                   │
│   Bus + Observers (latency, health, alerting, metrics, tokens)  │
│   PolicyVerdict (command/file/network/connector) + audit        │
│   Shell hooks (pre_tool_call, post_tool_call, pre_llm_call)     │
│   Unified SQLAlchemy persistence (conversations, channels,      │
│     jobs, speakers, workers) + Alembic migrations               │
│   Plugins (ASR, TTS, speaker, connectors) + sandbox backends   │
│     (Docker, Seatbelt, Bubblewrap)                              │
│   NotificationHub (proactive push to all client types)          │
│   Agentic harness (guardrails, toolsets, loop limits, cost)     │
│                                                                 │
│ Connectors (plugin-based)                                       │
│   Telegram · Slack · Discord · Feishu · WeChat                  │
│   SessionMapper → ConnectionManager → shared agent path         │
│   VoiceBridge (platform audio ↔ Tank PCM)                       │
│   ToolOutputObserver (non-text results → outbound attachments)  │
└─────────────────────────────────────────────────────────────────┘
```

Every one of these boxes is traceable to a commit in the history above. The
shape was not planned up front — it was arrived at by building, measuring, and
occasionally deleting.
