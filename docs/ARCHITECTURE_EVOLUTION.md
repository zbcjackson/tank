# Architecture Evolution

This document traces how Tank's architecture grew from a single-file Python script
into the current three-layer, pipeline-based, plugin-extensible, multi-client voice
assistant. It is organized by era, each bounded by an architectural inflection
point (a change in the core abstraction, not just a new capability).

Dates are taken from the git log. Commit hashes in parentheses mark the
representative commit for each change.

---

## Stage 1 — Sequential Script (Sep 2025)

**Representative commit:** `9894a04` (init), `c2a0425`, `b71c8fa`

Tank started as a conventional synchronous Python CLI assistant. A single
`VoiceAssistant` class composed the whole system:

```
main.py
  └── VoiceAssistant
        ├── WhisperTranscriber  (ASR)
        ├── EdgeTTSSpeaker      (TTS)
        ├── OpenRouterLLM       (LLM + conversation history)
        └── ToolManager         (calculator, weather, time, web_search)
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
main.py
  └── TankApp (Textual TUI)
        ├── TankHeader / ConversationArea / InputFooter
        └── Assistant (background task manager)
              ├── Perception      — mic → VAD → segmenter → brain_input_queue
              ├── Brain           — consumes BrainInputEvent, runs LLM, emits display/audio
              └── Speaker/Mic     — sounddevice wrappers
                  ↕ queues (BrainInputQueue, DisplayQueue, AudioOutputQueue)
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
pipeline/
├── processor.py          # Processor ABC, AudioCaps, FlowReturn
├── event.py              # PipelineEvent (bidirectional, typed)
├── queue.py              # ThreadedQueue (bounded, backpressure)
├── fan_out_queue.py      # parallel branches
├── bus.py                # pub/sub for metrics, state, alerts
├── builder.py            # PipelineBuilder (fluent assembly)
├── processors/           # VAD, ASR, SpeakerID, Brain, EchoGuard, TTS, Playback
└── observers/            # latency, interrupt_latency, turn_tracking,
                          # metrics_collector, health_monitor, alerting
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
persistence/
├── database.py     # shared engine + session factory (WAL, FK on)
├── base.py         # one DeclarativeBase for all stores
├── models/         # ORM rows per domain
├── migrate.py      # run_migrations() — programmatic Alembic
├── bootstrap.py    # first-run lift-and-shift from legacy DBs
└── migrations/     # Alembic env + versioned scripts
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

## Cross-Cutting Trends

Looking at the sequence end to end, four recurring moves show up:

1. **Concurrency made explicit.** Sync loop → queue workers → pipeline
   processors. Each step made thread boundaries declarative rather than
   implicit.
2. **Data flow made bidirectional.** Fire-and-forget queues → Bus for
   observability → typed `PipelineEvent` for upstream control → typed
   `PolicyVerdict` for security. Control, metrics, and security decisions
   travel on named buses, not hidden channels.
3. **Extension over modification.** Plugin manifests for engines, tool groups
   for tools, sandbox backends for runtime isolation, ORM models for
   persistence domains. Adding a capability is a manifest or group, not an
   edit to a central class.
4. **Trim what didn't earn its keep — and sometimes reshape it.** The
   keyword router was deleted in favor of LLM-driven tool choice; the
   specialized agent classes were replaced by markdown-defined sub-agents
   exposed as tools; the four per-feature SQLite files collapsed into one
   SQLAlchemy database. Each of these was a genuine design decision at the
   time, and each was reverted or reshaped when the cost outweighed the
   benefit. The project treats architectural complexity as reversible.

## Today (May 2026)

```
Clients: CLI (Textual) · Web (React 19 + Vite) · macOS (Tauri 2 wrapping web/)
         │
         ▼  WebSocket (binary PCM + JSON signals)
┌─────────────────────────────────────────────────────────────────┐
│ Backend (FastAPI + Uvicorn)                                     │
│                                                                 │
│ Layer 1 — Audio Pipeline                                        │
│   VAD → Q → ASR ┬→ SpeakerID ──┐                                │
│                 └→────────→ ASRSpeakerMerger → Q → Brain        │
│   Playback ← Q ← TTS ← EchoGuard ← Brain                        │
│                                                                 │
│ Layer 2 — Agent Orchestration                                   │
│   AgentGraph → ChatAgent(all tools) + Approval gates            │
│   Skills · MCP · Tool groups · Prompts · Context · Preferences  │
│                                                                 │
│ Layer 3 — LLM Transport                                         │
│   AsyncOpenAI (Langfuse) · retry · tiktoken                     │
│                                                                 │
│ Cross-cutting                                                   │
│   Bus + Observers (latency, health, alerting, metrics)          │
│   PolicyVerdict (command/file/network/tool) + audit             │
│   Unified SQLAlchemy persistence (conversations, channels,      │
│     jobs, speakers) + Alembic migrations                        │
│   Plugins (ASR, TTS, speaker, wake-word) + sandbox backends     │
│     (Docker, Seatbelt, Bubblewrap)                              │
│   Scheduler (APScheduler) for autonomous jobs + channel delivery│
└─────────────────────────────────────────────────────────────────┘
```

Every one of these boxes is traceable to a commit in the history above. The
shape was not planned up front — it was arrived at by building, measuring, and
occasionally deleting.
