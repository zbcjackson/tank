# Autonomous Mode Design

This document describes the design for Tank's autonomous operation — where the assistant performs tasks without a user actively prompting it.

## Motivation

Tank today is interactive-first: a user speaks or types, the pipeline processes, the assistant responds. But many valuable tasks don't need a human in the loop:

- **Scheduled briefings**: "Read me the AI news every morning at 9am"
- **Background research**: "Monitor Hacker News for posts about voice assistants and summarize weekly"
- **Maintenance tasks**: "Back up my notes to git every evening"
- **Proactive alerts**: "Check my server health every hour, tell me if anything is wrong"
- **Batch processing**: "Translate all markdown files in this folder to Chinese"

These tasks share a common pattern: a trigger starts the work, the agent runs to completion without user interaction, and results are delivered somewhere.

## Design Principles

1. **Reuse existing infrastructure** — AgentRunner, ToolManager, LLM, Bus, and persistence already work. Autonomous mode is a new entry point into the same agent system, not a parallel stack.
2. **Configurable output modality** — Some tasks should speak results aloud (news briefing). Others should write files silently (backup). Others should send a notification. The task defines its delivery, not the system.
3. **Safe by default** — Without a human watching, dangerous operations must be denied or sandboxed. Approval gates that normally ask the user must have a clear autonomous policy.
4. **Jobs are user data** — Job definitions, run history, and output logs live in `~/.tank/jobs/`, not in project config. Users manage jobs conversationally ("schedule a job to...") or via REST API. The project `config.yaml` only holds global scheduler settings (enabled, max_parallel).
5. **Start simple** — Cron scheduler first. Webhooks, backlogs, and event watchers come later.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       Trigger Layer                              │
│                                                                  │
│  Phase 1          Phase 2           Phase 3                      │
│  ┌──────────┐    ┌──────────────┐  ┌────────────────────────┐   │
│  │   Cron   │    │   Webhook    │  │  Backlog / Event Watch │   │
│  │ Scheduler│    │   Receiver   │  │  (file, queue, API)    │   │
│  └────┬─────┘    └──────┬───────┘  └───────────┬────────────┘   │
│       └─────────────────┼──────────────────────┘                 │
│                         ▼                                        │
│                ┌─────────────────┐                               │
│                │   Task Queue    │  (SQLite, persistent)         │
│                │   pending →     │                               │
│                │   running →     │                               │
│                │   succeeded /   │                               │
│                │   failed        │                               │
│                └────────┬────────┘                               │
│                         ▼                                        │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Autonomous Runner                             │  │
│  │                                                            │  │
│  │  1. Pick next pending task                                 │  │
│  │  2. Create headless session (choose pipeline mode)         │  │
│  │  3. Run AgentRunner with task prompt                       │  │
│  │  4. Enforce iteration budget + wall-clock timeout          │  │
│  │  5. Collect output (text, artifacts, audio)                │  │
│  │  6. Update task status                                     │  │
│  │                                                            │  │
│  └────────────────────────┬──────────────────────────────────┘  │
│                           ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Delivery Layer                                │  │
│  │                                                            │  │
│  │  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌───────────────┐   │  │
│  │  │  Audio  │ │   Text   │ │  File  │ │  Notification │   │  │
│  │  │ (TTS + │ │ (WebSocket│ │ (save  │ │  (webhook,    │   │  │
│  │  │ playback│ │  or log) │ │  to    │ │   message)    │   │  │
│  │  │  )     │ │          │ │  disk) │ │               │   │  │
│  │  └─────────┘ └──────────┘ └────────┘ └───────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Job Definition

A job is the persistent unit of autonomous work. It defines what to do, when to do it, and where to deliver results.

```python
@dataclass(frozen=True)
class JobDefinition:
    """Immutable definition of an autonomous job."""

    id: str                          # UUID
    name: str                        # Human-readable name
    prompt: str                      # What to tell the agent
    schedule: str                    # Cron expression: "0 9 * * *"
    enabled: bool = True

    # --- Execution constraints ---
    agent: str = "chat"              # Agent definition to use
    llm_profile: str = "default"     # LLM profile override
    max_iterations: int = 30         # Max LLM calls per run
    timeout_seconds: int = 300       # Wall-clock timeout
    allowed_tools: list[str] | None = None   # Whitelist (None = all)
    blocked_tools: list[str] | None = None   # Blacklist

    # --- Delivery ---
    delivery: DeliveryConfig = DeliveryConfig()

    # --- Approval policy override ---
    approval_mode: str = "deny"      # "deny" | "auto" | "interactive"
```

### 2. Delivery Configuration

Each job specifies how its results should be delivered. Multiple channels can be active simultaneously — a morning briefing might both speak aloud AND save a text summary.

```python
@dataclass(frozen=True)
class DeliveryConfig:
    """How to deliver job results."""

    # Audio: speak results through TTS + playback pipeline
    audio: bool = False
    audio_voice: str | None = None   # Override TTS voice
    audio_priority: str = "low"      # "low" | "normal" | "high" (see Audio Conflict Resolution)
    audio_idle_threshold: int = 300   # Seconds of silence before auto-play

    # Text: save to file or log
    text: bool = True                # Always save text output
    text_path: str | None = None     # Custom output path (default: ~/.tank/jobs/output/)

    # WebSocket: push to connected clients
    websocket: bool = False          # Push to any connected WebSocket session
    websocket_session_id: str | None = None  # Specific session

    # Webhook: POST results to external URL
    webhook_url: str | None = None
    webhook_headers: dict[str, str] | None = None

    # Notification: lightweight alert (future: system notification, email, etc.)
    notify: bool = False
    notify_channel: str | None = None  # "system" | "email" | "telegram" | etc.
```

#### Delivery Examples

**Morning news briefing** (audio + text):
```yaml
delivery:
  audio: true
  audio_voice: en-US-JennyNeural
  text: true
```

**Silent background research** (text file only):
```yaml
delivery:
  audio: false
  text: true
  text_path: ~/research/ai-news-weekly.md
```

**Server health check** (webhook + notify on failure):
```yaml
delivery:
  audio: false
  text: true
  webhook_url: https://hooks.slack.com/services/xxx
  notify: true
```

**Git backup** (silent, no output needed):
```yaml
delivery:
  audio: false
  text: true  # Log what was backed up
```

### 3. Job Storage

Jobs are user data — they live in `~/.tank/jobs/`, not in project config. This keeps them alongside sessions, preferences, and memory. SQLite gives us ACID guarantees, WAL mode for concurrent reads, and a single portable directory.

```
~/.tank/jobs/
├── jobs.db          # Job definitions + run history + scheduling state
└── output/          # Run output files (browsable by user or agent)
    ├── {job_name}/
    │   ├── 2026-04-25T090000.md
    │   ├── 2026-04-26T090000.md
    │   └── ...
```

Output files use `{job_name}/` (not job_id) so the directory is human-readable. The user can browse `~/.tank/jobs/output/morning_news/` directly, or ask Tank: "What did my morning briefing say yesterday?"

**Schema**:

```sql
-- Job definitions (user data, not project config)
CREATE TABLE jobs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,  -- human-readable, used as output dir name
    prompt      TEXT NOT NULL,
    schedule    TEXT NOT NULL,          -- cron expression
    enabled     INTEGER DEFAULT 1,
    config_json TEXT NOT NULL,          -- Full JobDefinition as JSON
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- Run history (queryable by user: "show me last week's briefings")
CREATE TABLE job_runs (
    id          TEXT PRIMARY KEY,
    job_id      TEXT NOT NULL REFERENCES jobs(id),
    status      TEXT NOT NULL,          -- pending | running | succeeded | failed | timeout
    started_at  TEXT,
    finished_at TEXT,
    output_path TEXT,                   -- Path to output markdown file
    error       TEXT,                   -- Error message if failed
    stats_json  TEXT                    -- Iteration count, token usage, duration, etc.
);

-- Scheduling state (internal, drives the tick loop)
CREATE TABLE job_schedule (
    job_id      TEXT PRIMARY KEY REFERENCES jobs(id),
    next_run_at TEXT NOT NULL,          -- ISO timestamp
    last_run_at TEXT,
    last_status TEXT
);
```

**Querying results**: The agent can read job output files using existing file tools. When the user asks "What did my morning briefing say?", the agent calls `manage_jobs(action="history", job_name="morning_news")` to find the latest output path, then reads the file. No special infrastructure needed — the output is just markdown on disk.

### 4. Cron Scheduler

The scheduler is a background asyncio task that runs inside the existing FastAPI server process. No separate daemon needed.

```python
class CronScheduler:
    """Tick-based scheduler that checks for due jobs every 60 seconds."""

    def __init__(
        self,
        job_store: JobStore,
        runner: AutonomousRunner,
        max_parallel: int = 3,
    ) -> None:
        self._job_store = job_store
        self._runner = runner
        self._max_parallel = max_parallel
        self._running: dict[str, asyncio.Task] = {}
        self._tick_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the scheduler tick loop."""
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        """Stop scheduler and cancel running jobs."""
        if self._tick_task:
            self._tick_task.cancel()
        for task in self._running.values():
            task.cancel()

    async def _tick_loop(self) -> None:
        """Main loop: check for due jobs every 60 seconds."""
        while True:
            try:
                await self._tick()
            except Exception:
                logger.error("Scheduler tick error", exc_info=True)
            await asyncio.sleep(60)

    async def _tick(self) -> None:
        """Find due jobs and launch them."""
        due_jobs = self._job_store.get_due_jobs()
        for job in due_jobs:
            if job.id in self._running:
                continue  # Already running
            if len(self._running) >= self._max_parallel:
                break     # At capacity
            task = asyncio.create_task(self._run_job(job))
            self._running[job.id] = task

    async def _run_job(self, job: JobDefinition) -> None:
        """Execute a single job and handle lifecycle."""
        try:
            await self._runner.execute(job)
        finally:
            self._running.pop(job.id, None)
            self._job_store.advance_schedule(job.id)
```

#### Schedule Expressions

Standard 5-field cron: `minute hour day-of-month month day-of-week`

```
"0 9 * * *"       → Every day at 9:00 AM
"0 9 * * 1-5"     → Weekdays at 9:00 AM
"*/30 * * * *"     → Every 30 minutes
"0 0 * * 0"       → Every Sunday at midnight
"0 9 1 * *"       → First day of every month at 9:00 AM
```

Also support human-friendly intervals (parsed to cron internally):
```
"every 30m"        → */30 * * * *
"every 2h"         → 0 */2 * * *
"every day at 9am" → 0 9 * * *
```

### 5. Autonomous Runner

The runner creates a headless session and executes the agent. It reuses `AgentRunner` directly — no new agent execution path.

```python
class AutonomousRunner:
    """Execute jobs without user interaction."""

    def __init__(
        self,
        app_config: AppConfig,
        job_store: JobStore,
    ) -> None:
        self._app_config = app_config
        self._job_store = job_store

    async def execute(self, job: JobDefinition) -> JobRunResult:
        """Run a job to completion."""
        run_id = uuid.uuid4().hex
        self._job_store.record_run_start(job.id, run_id)

        try:
            # 1. Create headless components (no audio pipeline by default)
            llm = create_llm_from_profile(
                self._app_config.get_llm_profile(job.llm_profile)
            )
            bus = Bus()
            tool_manager = ToolManager(
                app_config=self._app_config,
                bus=bus,
            )

            # 2. Build approval policy for autonomous mode
            approval_policy = self._build_approval_policy(job)

            # 3. Build agent
            agent_def = self._resolve_agent(job)
            runner = AgentRunner(
                llm=llm,
                tool_manager=tool_manager,
                bus=bus,
                approval_policy=approval_policy,
                pending_store=PendingToolCallStore(),
                definitions={agent_def.name: agent_def},
            )

            # 4. Execute with timeout
            output_parts: list[str] = []
            messages = [{"role": "user", "content": job.prompt}]

            async with asyncio.timeout(job.timeout_seconds):
                async for output in runner.run_agent(
                    agent_def=agent_def,
                    messages=messages,
                    max_turns=job.max_iterations,
                ):
                    if output.type == AgentOutputType.TOKEN:
                        output_parts.append(output.content)

            result_text = "".join(output_parts)

            # 5. Deliver results
            await self._deliver(job, result_text, run_id)

            # 6. Record success
            self._job_store.record_run_end(
                job.id, run_id, status="succeeded", output=result_text
            )
            return JobRunResult(status="succeeded", output=result_text)

        except asyncio.TimeoutError:
            self._job_store.record_run_end(
                job.id, run_id, status="timeout",
                error=f"Exceeded {job.timeout_seconds}s timeout",
            )
            return JobRunResult(status="timeout")

        except Exception as e:
            self._job_store.record_run_end(
                job.id, run_id, status="failed", error=str(e),
            )
            return JobRunResult(status="failed", error=str(e))

        finally:
            await tool_manager.cleanup()
```

### 6. Pipeline Modes for Delivery

The key insight: TTS and playback are useful for autonomous tasks too. A morning briefing should speak. A background research task should not. The runner selects the pipeline mode based on the job's delivery config.

#### Mode: Silent (default)

No audio pipeline. Agent runs text-only. Output saved to file and/or delivered via webhook.

```
AgentRunner → collect text → save to file / webhook / WebSocket
```

#### Mode: Audio

Full TTS + playback pipeline. Agent output streams through TTS and plays through speakers, exactly like interactive mode but triggered by the scheduler instead of a user.

```
AgentRunner → stream tokens → TTSProcessor → PlaybackProcessor → speakers
                           → also save text to file
```

This reuses the existing pipeline infrastructure. The `AutonomousRunner` creates a mini-pipeline with just Brain → TTS → Playback (no VAD, no ASR, no echo guard — there's no user speaking).

```python
async def _deliver_audio(self, job: JobDefinition, text: str) -> None:
    """Speak the result through TTS + playback."""
    tts_engine = self._create_tts_engine(job.delivery.audio_voice)
    if tts_engine is None:
        logger.warning("TTS not available for audio delivery, falling back to text")
        return

    bus = Bus()
    tts = TTSProcessor(tts_engine=tts_engine, bus=bus)
    playback = PlaybackProcessor(bus=bus)

    # Build a minimal output pipeline
    builder = PipelineBuilder(bus)
    builder.add(tts)
    builder.add(playback)
    pipeline = builder.build()

    await pipeline.start()
    try:
        # Feed text into TTS
        pipeline.push(AudioOutputRequest(text=text, language=detect_language(text)))
        # Wait for playback to finish
        await self._wait_for_playback_complete(bus)
    finally:
        await pipeline.stop()
```

#### Mode: WebSocket

Push results to a connected client session. Useful when the user has the web UI open and wants to see autonomous task results appear in their chat.

```
AgentRunner → stream tokens → WebSocket session → client UI
```

### 7. Safety Model

Autonomous mode changes the safety equation fundamentally. There's no human to approve dangerous operations in real-time.

#### Approval Modes (per-job)

In autonomous mode, there's no user to approve tool calls. The approval gate has two outcomes: execute or park-for-user. "Park" in headless mode effectively means "block" — the agent gets an error and must work around it.

`CommandSecurityPolicy` evaluates commands into a binary verdict (`allowed` or not). Both "dangerous" (e.g. `rm -rf /`) and "unknown" (not in the safe allowlist) produce the same `needs_approval=True`. The approval mode controls what happens at that point:

```
Tool call → CommandSecurityPolicy evaluates → verdict:
  ├─ allowed=True   → execute (both modes)
  └─ allowed=False  → approval_mode decides:
       ├─ "deny"  → block (agent gets error, must work around it)
       └─ "auto"  → execute (bypasses the gate entirely)
```

| Mode | Behavior | Use case |
|------|----------|----------|
| `deny` (default) | Only pre-approved safe commands run. Unknown and dangerous commands are blocked. | Safe default for most jobs. |
| `auto` | All commands execute, including ones the security policy would normally flag. | Trusted jobs where you control the prompt and need full shell access. |

**Important**: `auto` mode bypasses the approval gate entirely for command tools. It does NOT selectively allow "unknown but safe" commands while blocking dangerous ones — the current `CommandVerdict` is binary and doesn't distinguish between them. If you need finer control, use `deny` mode with a broader `command_security` safe-command allowlist in config.yaml.

Other tool-internal security layers (NetworkAccessPolicy, FileAccessPolicy, Docker sandbox) still apply in both modes — they enforce their own restrictions at execution time, independent of the approval gate.

#### Tool Restrictions

Each job can specify `allowed_tools` (whitelist) or `blocked_tools` (blacklist):

```yaml
# News briefing: only needs web search and web fetch
allowed_tools:
  - web_search
  - web_fetch
  - get_time

# Backup job: block dangerous tools
blocked_tools:
  - run_command
  - persistent_shell
  - file_delete
```

When neither is specified, the job inherits the global tool set minus tools in `require_approval` (which are blocked in `deny` mode).

#### Iteration and Resource Limits

| Limit | Default | Purpose |
|-------|---------|---------|
| `max_iterations` | 30 | Max LLM API calls per run |
| `timeout_seconds` | 300 | Wall-clock timeout |
| `max_parallel` | 3 | Max concurrent jobs (scheduler-level) |

These prevent runaway loops and unbounded resource consumption.

#### Sandboxing

Code execution tools (`run_command`, `persistent_shell`) already run in Docker/seatbelt sandbox. This applies equally to autonomous mode — no changes needed.

### 8. Job Setup via Voice and Text Chat

The most natural way to create a job is conversationally. The user just says what they want:

> "Every morning at 9, read me the AI news"
> "Remind me to check server health every hour"
> "Every Sunday, summarize Hacker News this week and save it to ~/research/"

The LLM already has tool-calling. We add a `manage_jobs` tool that the agent calls when it recognizes scheduling intent:

```
User: "Every morning at 9, read me the AI news"
  │
  ▼
LLM recognizes scheduling intent, calls manage_jobs:
  {
    "action": "create",
    "name": "morning_ai_news",
    "prompt": "Search for the top 5 AI news stories from the last 24 hours.
               Summarize each in 2-3 sentences. Include source URLs.",
    "schedule": "0 9 * * *",
    "delivery": { "audio": true, "text": true }
  }
  │
  ▼
Tool creates the job in ~/.tank/jobs/jobs.db, returns confirmation
  │
  ▼
LLM responds: "Done — I'll read you the AI news every morning at 9."
```

The LLM does the intent parsing — no special command syntax needed. It decides:
- What the recurring prompt should be (often rephrased from the user's request)
- What schedule to use (parsing "every morning at 9" → `0 9 * * *`)
- What delivery mode fits ("read me" → audio, "save to file" → text only)

Modifications work the same way:
- "Change my morning briefing to 8am" → `manage_jobs(action="update", ...)`
- "Stop the server health check" → `manage_jobs(action="disable", ...)`
- "What jobs do I have?" → `manage_jobs(action="list")`
- "Run the news briefing now" → `manage_jobs(action="run", ...)`
- "What did my morning briefing say yesterday?" → `manage_jobs(action="history", ...)` → reads the output file

```python
class JobManagementTool(BaseTool):
    """Manage autonomous jobs: create, list, run, enable, disable, delete, history."""

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="manage_jobs",
            description=(
                "Create, list, update, run, enable, disable, delete scheduled jobs, "
                "or view run history and output. Jobs are stored in ~/.tank/jobs/."
            ),
            parameters=[
                ToolParameter(name="action", type="string",
                    enum=["create", "list", "update", "run", "enable",
                          "disable", "delete", "history", "status"],
                    description="Action to perform"),
                ToolParameter(name="name", type="string",
                    description="Job name (for create/update/run/enable/disable/delete/history)"),
                ToolParameter(name="prompt", type="string",
                    description="What the agent should do each run (for create/update)"),
                ToolParameter(name="schedule", type="string",
                    description="Cron expression or human-friendly schedule (for create/update)"),
                ToolParameter(name="delivery", type="object",
                    description="Delivery config: {audio, text, webhook_url, ...} (for create/update)"),
                ToolParameter(name="approval_mode", type="string",
                    enum=["deny", "auto"],
                    description="Tool approval policy (for create/update, default: deny)"),
            ],
        )
```

### 9. Audio Conflict Resolution

When a job with audio delivery fires while the user is mid-conversation, we need to avoid talking over them. The delivery system checks conversation state before playing audio.

#### Decision Flow

```
Job completes with audio delivery
  │
  ├─ No client connected?
  │    → Save text only. Queue audio for next session connect.
  │
  ├─ Client connected, conversation idle (no activity for idle_threshold)?
  │    → Play audio immediately.
  │
  ├─ Client connected, conversation active, priority = "high"?
  │    → Brief pause (2s), then play audio. (Urgent alerts.)
  │
  └─ Client connected, conversation active, priority = "low" or "normal"?
       → Send text notification to session:
         "Your morning briefing is ready. Say 'read it' when you want."
       → Queue audio. Play when conversation goes idle or user requests it.
```

#### Priority Levels

| Priority | Behavior during active conversation | Use case |
|----------|-------------------------------------|----------|
| `low` (default) | Queue silently, play when idle | Background research, backups |
| `normal` | Notify user, queue for on-demand playback | Morning briefing, reports |
| `high` | Interrupt after brief pause | Server down, urgent alerts |

#### Implementation

The `DeliveryManager` tracks conversation activity via the Bus. The existing `speech_start` and `playback_started`/`playback_ended` bus events already indicate when the user or assistant is speaking.

```python
class DeliveryManager:
    def __init__(self, ..., connection_manager=None):
        self._connection_manager = connection_manager
        self._audio_queue: list[tuple[JobDefinition, str]] = []

    async def _deliver_audio(self, job: JobDefinition, text: str) -> None:
        session = self._get_active_session()
        if session is None:
            # No client connected — queue for later
            self._audio_queue.append((job, text))
            return

        idle_seconds = session.seconds_since_last_activity()
        threshold = job.delivery.audio_idle_threshold  # default 300s

        if idle_seconds >= threshold:
            # Conversation idle — play immediately
            await self._play_audio(session, job, text)
        elif job.delivery.audio_priority == "high":
            # Urgent — interrupt after brief pause
            await asyncio.sleep(2)
            await self._play_audio(session, job, text)
        else:
            # Active conversation — notify and queue
            session.send_notification(
                f"Your job '{job.name}' finished. Say 'read it' to hear the result."
            )
            self._audio_queue.append((job, text))
```

When a session goes idle (detected via a Bus subscription on activity events), the delivery manager drains the audio queue.

### 10. Configuration

Jobs are user data stored in `~/.tank/jobs/`. The project `config.yaml` only holds global scheduler settings — whether the feature is enabled and resource limits.

#### config.yaml (project-level — scheduler settings only)

```yaml
# Autonomous job scheduler — global settings.
# Job definitions are stored in ~/.tank/jobs/jobs.db (user data).
# Create jobs via voice ("schedule a job to..."), REST API, or seed file.
jobs:
  enabled: true
  max_parallel: 3           # Max concurrent job executions
  tick_interval: 60         # Seconds between scheduler ticks
  db_path: ~/.tank/jobs/jobs.db
  output_dir: ~/.tank/jobs/output
```

#### Seed file (optional, declarative sync)

Users who want to define jobs declaratively can place a `~/.tank/jobs/seed.yaml` file. The seed file operates in **sync mode** — it is the source of truth for seed-origin jobs:

- Jobs in the file but not in DB → created (tagged `origin='seed'`)
- Jobs in DB with `origin='seed'` but removed from the file → deleted from DB
- Jobs created via voice/API (`origin='api'`) → never touched by seed sync

This means removing a job from seed.yaml and reloading will delete it. Jobs created conversationally are always safe from seed sync.

Reload happens at server startup and via `POST /api/jobs/scheduler/reload-seed`.

```yaml
# ~/.tank/jobs/seed.yaml — optional, loaded once on startup
morning_briefing:
  prompt: |
    Search for the top 5 AI news stories from the last 24 hours.
    Summarize each in 2-3 sentences. Include source URLs.
    Present as a morning briefing.
  schedule: "0 9 * * 1-5"
  delivery:
    audio: true
    audio_priority: normal
    text: true
  approval_mode: deny
  allowed_tools:
    - web_search
    - web_fetch
    - get_time

weekly_research:
  prompt: |
    Search Hacker News and Reddit for posts about voice assistants,
    LLM agents, and speech recognition from the past week.
    Write a summary report with key trends and interesting projects.
  schedule: "0 10 * * 0"
  timeout_seconds: 600
  delivery:
    audio: false
    text: true
    text_path: ~/research/voice-ai-weekly.md
  approval_mode: deny
```

#### REST API

```
GET    /api/jobs                     # List all job definitions
POST   /api/jobs                     # Create a new job
GET    /api/jobs/{id}                # Get job details + schedule info
PUT    /api/jobs/{id}                # Update job definition
DELETE /api/jobs/{id}                # Delete job
POST   /api/jobs/{id}/run            # Trigger immediate run
GET    /api/jobs/{id}/runs           # List run history
GET    /api/jobs/{id}/runs/{run_id}  # Get run details + output
POST   /api/jobs/{id}/enable         # Enable job
POST   /api/jobs/{id}/disable        # Disable job
GET    /api/scheduler/status         # Scheduler health + next runs
```

#### User data layout

```
~/.tank/jobs/
├── jobs.db                          # SQLite: definitions + runs + schedule
├── seed.yaml                        # Optional: declarative job definitions
└── output/                          # Run outputs (human-readable)
    ├── morning_briefing/
    │   ├── 2026-04-25T090000.md
    │   └── 2026-04-26T090000.md
    └── weekly_research/
        └── 2026-04-20T100000.md
```

### 11. Observability

Autonomous jobs integrate with the existing Bus + observer system:

- **Bus messages**: `job_started`, `job_finished`, `job_failed`, `job_timeout`
- **Metrics**: Per-job iteration count, token usage, duration, success rate
- **Langfuse**: Each job run creates a trace (reuses existing LLM tracing)
- **Health**: Scheduler health exposed via `/health?detail=true`
- **Alerting**: AlertingObserver can fire on job failure rate spikes

### 12. Web UI Integration

The web frontend gets a new "Jobs" panel (future phase) showing:

- List of scheduled jobs with next run time
- Run history with status indicators
- Live output streaming for running jobs
- Create/edit/delete job forms

For Phase 1, jobs are managed via voice/chat, REST API, and optional seed.yaml.

## Implementation Phases

### Phase 1: Cron Scheduler (this PR)

Core autonomous infrastructure:

1. **Job data model** — `JobDefinition`, `DeliveryConfig`, `JobRunResult` dataclasses
2. **Job storage** — `JobStore` with SQLite backend in `~/.tank/jobs/jobs.db`
3. **Cron parser** — Parse 5-field cron expressions, calculate next run time
4. **Cron scheduler** — Background asyncio task, tick every 60s, launch due jobs
5. **Autonomous runner** — Headless agent execution with timeout and iteration budget
6. **Text delivery** — Save output to `~/.tank/jobs/output/{job_name}/`
7. **Audio delivery** — TTS + playback mini-pipeline with conflict resolution
8. **REST API** — CRUD for jobs, trigger immediate run, view history
9. **Job management tool** — `manage_jobs` tool for voice/chat job setup
10. **Seed file loader** — Load `~/.tank/jobs/seed.yaml` on startup
11. **Configuration** — `jobs:` section in config.yaml (scheduler settings only)
12. **Tests** — Job store, cron parser, scheduler tick, runner execution

**Files to create**:
```
backend/core/src/tank_backend/
├── jobs/
│   ├── __init__.py
│   ├── models.py          # JobDefinition, DeliveryConfig, JobRunResult
│   ├── store.py           # JobStore (SQLite in ~/.tank/jobs/)
│   ├── cron.py            # Cron expression parser + next-run calculator
│   ├── scheduler.py       # CronScheduler (tick loop)
│   ├── runner.py          # AutonomousRunner (headless execution)
│   └── delivery.py        # DeliveryManager (text, audio, webhook + conflict resolution)
├── api/
│   └── jobs.py            # REST API routes (new file)
└── tools/
    └── job_tools.py       # JobManagementTool (new file)
```

**Files to modify**:
```
backend/core/src/tank_backend/
├── api/server.py          # Mount jobs router, start/stop scheduler in lifespan
└── config.yaml            # Add jobs: section (scheduler settings only)
```

### Phase 2: APScheduler + Policy Redesign + WebSocket Delivery

**APScheduler migration** — Replace hand-built `CronScheduler` with `APScheduler.AsyncScheduler`:
- Native cron triggers, interval triggers, one-shot triggers
- Built-in SQLite/SQLAlchemy persistence for scheduling state
- `max_concurrent_jobs` enforcement
- FastAPI lifespan integration (documented pattern)
- Keep: `JobStore` (run history), `DeliveryManager`, `AutonomousRunner`, REST API, seed sync

**Policy redesign** — Unified three-way verdict protocol (see `DESIGN_POLICY_REDESIGN.md`):
- `PolicyVerdict(level=ALLOW|REQUIRE_APPROVAL|DENY)` — all policies return the same type
- `CommandSecurityPolicy` upgraded from binary to three-way (distinguish dangerous vs unknown)
- Pluggable `ApprovalResolver` protocol — decides what to do with `REQUIRE_APPROVAL`:
  - `InteractiveResolver` — park and ask user (current behavior)
  - `AlwaysApproveResolver` — auto-approve (for trusted autonomous jobs)
  - `AlwaysDenyResolver` — auto-deny (safe default for autonomous jobs)
  - `LLMResolver` — ask an LLM to decide (future)
- Approval mode renamed: `"auto"/"deny"` → `"always_approve"/"always_deny"`
- `DENY` verdicts are hard blocks — no resolver can override them

**WebSocket delivery**:
- Push job results to connected WebSocket clients
- Job results appear in chat history as system messages
- Basic job management in web UI

### Phase 3: Webhook Triggers

- HTTP endpoint to trigger jobs from external systems (GitHub, CI, etc.)
- Payload templating (inject webhook data into job prompt)
- HMAC signature validation for security

### Phase 4: Backlog Processing

- Read tasks from a file, database, or API
- Process items sequentially or in parallel
- Track completion state per item
- Retry failed items

### Phase 5: Notification Channels

- System notifications (macOS native via Tauri)
- Email delivery
- Messaging platform integration (Telegram, Slack, etc.)

## Comparison with Researched Systems

| Feature | Hermes Agent | OpenClaw | Claude Code | Tank (proposed) |
|---------|-------------|----------|-------------|-----------------|
| Cron scheduler | File-based jobs.json, ThreadPoolExecutor | SQLite task registry, heartbeat polling | scheduleRemoteAgents skill | SQLite jobs.db, asyncio tasks |
| Webhooks | Generic receiver with HMAC, GitHub integration | System events queue | RemoteTriggerTool | Phase 3 |
| Approval in autonomous | cron_mode: deny/approve | Tool classification + policy | Permission bridge | Per-job: deny/auto/interactive |
| Delivery | File + messaging platforms | Task delivery queue with retry | Structured IO (NDJSON) | File + audio + webhook + WebSocket |
| Audio output | N/A | N/A | N/A | TTS + playback pipeline (unique to Tank) |
| Subagent delegation | Flat (depth 1), ThreadPoolExecutor | Hierarchical task flows | Multi-agent coordinator | Reuse existing AgentRunner (depth 3) |
| State persistence | SQLite sessions + JSON jobs | SQLite task registry | Agent memory snapshots | SQLite jobs + existing context store |

Tank's unique advantage: **audio delivery**. No other agent framework can speak autonomous results aloud. This makes Tank genuinely useful as a proactive voice assistant, not just a background task runner.

## Open Questions

1. **Job chaining**: Should one job's output feed into another? (Not in Phase 1. If needed, a job can be prompted to "read the output of job X" since outputs are just files on disk.)

2. **Concurrent job isolation**: Should jobs share conversation context? (No. Each run gets a fresh AgentState. Jobs are independent.)

3. **Timezone handling**: Cron expressions are in server-local time. Should we support per-job timezones? (Not in Phase 1. Use server timezone.)

4. **Job templates / marketplace**: Should there be a library of pre-built job templates? (Future consideration. Start with voice/chat creation and optional seed.yaml.)

5. **Output retention**: How long to keep output files? (Add `max_output_age_days` config, default 30. Scheduler prunes old files on tick.)
