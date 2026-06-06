# Workflow & Orchestration

This document describes how Tank structures multi-step work: today's
implementation, the planned next phase, and the long-term direction.
It is the single source of truth for "how should the agent loop be
shaped".

The roadmap has three phases:

- **Phase 1 — Foundations.** *Shipped.* Parallel exploration + the
  explore-plan-act phase shape baked into the main agent's prompt.
- **Phase 2 — Worker runtime.** *Planned.* Real backgrounding, resumable
  task ids, and channel-aware delivery — the substrate that lets Tank
  finish work after the user disconnects and report back over any
  channel.
- **Phase 3 — Chat-agent / worker split.** *Speculative.* The
  conversational LLM becomes a thin manager; all multi-step work goes
  to workers. Phase 1 and Phase 2 are deliberately shaped so this
  becomes a refactor, not a rewrite.

## Guiding principle

**Explore-plan-act is a workflow shape, not an agent topology.** The
shape is stable across architectures; only where each phase lives
changes.

| Phase | Today (single LLM loop) | Phase 3 (chat agent + workers) |
|---|---|---|
| Explore | LLM emits parallel read-only tool calls in one turn | Chat agent dispatches an exploration worker |
| Plan | LLM produces a brief outline as text, then continues | Chat agent reasons over findings; presents plan |
| Act | LLM emits mutating tool calls | Chat agent dispatches an execution worker |

The corollary: **don't reify a phase into a sub-agent until evidence
shows the phase needs its own context.** A phase is free to migrate;
a sub-agent is a contract.

## Tank's starting state (before Phase 1)

| Pattern | Status |
|---|---|
| Explore-plan-act | Absent. The main agent jumped straight to tool calling. |
| Context-isolated subagents | Present, basic. `AgentTool` → `AgentRunner.run_agent()` with depth/concurrency limits. `background=True` plumbed but didn't decouple — the parent iterated the child to completion. No resumable `task_id`. No channel-aware delivery. |
| Fork-join parallelism | Half-present. `_CONCURRENT_SAFE_TOOLS = frozenset({"agent"})` — only the agent tool ran in parallel. Read-only tools like `web_search`, `file_read`, `web_fetch` ran sequentially even when emitted in one turn. |

Existing strengths preserved across all phases:

- Bus + observers (`pipeline/bus.py`) for cross-cutting state.
- `ApprovalGateExecutor` + three-way `PolicyVerdict` for sensitive tools.
- Markdown agent definitions with frontmatter (`backend/agents/*.md`).
- Single-loop streaming via `LLMAgent` — no graph framework tax.
- Unified `tank.db` with Alembic migrations and shared ORM `Base`.

---

## Phase 1 — Foundations (shipped)

### Gap D — Broaden `_CONCURRENT_SAFE_TOOLS`

Read-only / pure-query tools now run in parallel via `asyncio.gather`
when emitted in one assistant turn:

```python
_CONCURRENT_SAFE_TOOLS = frozenset({
    "agent",
    "file_read", "file_list", "file_search",
    "web_search", "web_fetch",
    "get_weather", "get_time", "calculate",
    "get_user_memory", "get_context_usage",
})
```

Excluded (mutating or stateful): `file_write`, `file_edit`,
`file_delete`, `run_command`, `persistent_shell`, `manage_process`,
`confirm_action`, `remember`, `consolidate_memory`, `compact_context`,
channel/job tools.

This is the EXPLORE primitive. Phase 1 makes parallel research
possible inside the main agent; Phase 3 keeps the same set in workers.

### Gap A′ — Explore-plan-act in the system prompt

The main agent's system prompt (`Brain._build_main_agent_prompt`)
teaches the loop as a phase shape — no new tool, no new agent type,
no read-only mode gate:

```
For requests that benefit from research (multi-step, ambiguous,
comparative, exploratory), follow this shape:

  1. EXPLORE: gather information using read-only tools. Prefer
              multiple lookups in one turn — they run in parallel.
  2. PLAN:    state your approach in 1-3 lines based on what you
              found. Surface clarifying questions only if they
              would change the plan.
  3. ACT:     execute and deliver.

For simple requests (greetings, one-shot facts, direct commands),
skip straight to ACT.
```

**Why not a `planner` sub-agent.** Reifying planning into a sub-agent
hardcodes it onto the executor layer. When the chat-agent split
happens, planning becomes a chat-agent responsibility — migrating a
sub-agent is expensive; migrating a phase is free.

### Phase 1 verification

- `core/tests/test_concurrent_safe_tools.py` pins the safe set, the
  mutating exclusion set, and the `_is_concurrent_safe` helper.
- `core/tests/test_main_agent_prompt_phases.py` pins the EXPLORE /
  PLAN / ACT markers, the parallel-explore directive, and the
  simple-request short-circuit. Also asserts there is no
  `planner` / `plan_enter` / `plan_exit` so we don't drift into the
  wrong topology.
- Eight-step verification checklist clean.

---

## Phase 2 — Worker runtime (in progress)

### Goal

Turn `agent` from a synchronous parent-blocking call into a real
worker runtime. Workers persist across websocket disconnects, get
resumed by `task_id`, and report results to whichever channel the
user is currently on.

### Why now

Three concrete failure modes today:

1. A `verifier` sub-agent that runs a long check blocks the voice
   loop. The user is stuck listening to silence.
2. The user closes their phone app; whatever the agent was doing
   dies. There's no "I'll be done in a minute, I'll text you" path.
3. A natural follow-up like "now also research X on that trip"
   loses everything because every `agent` call starts a fresh
   context.

Phase 2 fixes all three with one small runtime.

### Scope

In scope:
- New `WorkerRunRow` ORM table + Alembic migration.
- New `WorkerStore` with the same shape as `JobStore`.
- New `WorkerSupervisor` owning the in-process registry and lifecycle.
- New tools: `agent_status`, `agent_stop`, `list_active_agents`.
- Existing `agent` tool gains `run_in_background: bool` (real now)
  and `task_id: str | None` (resume).
- Channel-aware delivery: completion events route to the originating
  channel via the existing connector observers.
- Voice-mode flush rules: announce on next idle, suppress during
  user speech.
- `/api/agents` REST routes (list, get, stop) so the web UI can
  surface what's running.

Out of scope (deliberately deferred):
- Worker-to-worker dispatch with full delivery (workers can still
  use `agent` for sub-tasks, but their results route to the
  parent worker, not back to the channel directly).
- Sandbox/worktree isolation for workers (`isolation` parameter
  stays unimplemented).
- Cross-process supervision. Workers live in the FastAPI process.
  If the process dies, in-flight workers are marked `cancelled`
  on next start and re-runnable via `task_id`.

### Schema

Mirrors `JobRow` / `JobRunRow` so the patterns the codebase already
exercises apply unchanged.

```python
# core/src/tank_backend/persistence/models/workers.py

class WorkerRunRow(Base):
    """One row per agent dispatch. Foreground and background share this."""

    __tablename__ = "worker_runs"

    task_id:                       Mapped[str] = mapped_column(String, primary_key=True)
    agent_def:                     Mapped[str] = mapped_column(String, nullable=False)
    description:                   Mapped[str] = mapped_column(String, nullable=False, default="")
    prompt:                        Mapped[str] = mapped_column(Text, nullable=False)
    status:                        Mapped[str] = mapped_column(String, nullable=False, index=True)
    # "running" | "completed" | "failed" | "cancelled" | "timeout"

    parent_task_id:                Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    originating_conversation_id:   Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    originating_channel:           Mapped[str | None] = mapped_column(String, nullable=True)
    # "voice:<session>" | "channel:<slug>" | "telegram:<chat_id>" | "discord:<channel>" | ...
    parent_msg_id:                 Mapped[str | None] = mapped_column(String, nullable=True)

    background:                    Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at:                    Mapped[str] = mapped_column(String, nullable=False)
    completed_at:                  Mapped[str | None] = mapped_column(String, nullable=True)
    output:                        Mapped[str] = mapped_column(Text, nullable=False, default="")
    error:                         Mapped[str | None] = mapped_column(Text, nullable=True)
    messages_json:                 Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of OpenAI messages for resume-via-task_id
```

Alembic migration: `<timestamp>_add_worker_runs.py`. Single `op.create_table`,
no data backfill needed.

### Tool surface

Same tool names today and after the chat-agent split.

```python
agent(
    prompt: str,
    subagent_type: str = "coder",
    description: str = "",
    run_in_background: bool = False,
    task_id: str | None = None,        # resume an existing run
)
# Returns:
#   foreground:  {task_id, status: "completed"|"failed", output|error}
#   background:  {task_id, status: "running"}
#   resume:      same shape; the worker continues with appended prompt

agent_status(task_id, wait: bool = False, timeout_ms: int = 60000)
# Returns: {task_id, status, output, error, started_at, completed_at}
# wait=True blocks until status != "running" or timeout.

agent_stop(task_id)
# Returns: {task_id, status: "cancelled"|...}

list_active_agents()
# Returns: [{task_id, agent_def, description, status, started_at}]
# Filtered to status="running" by default; ?include=all in REST.
```

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  LLMAgent emits agent(...)                                      │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  AgentTool.execute                                              │
│   • resolve agent_def                                           │
│   • runner.dispatch(prompt, ..., background, task_id)           │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  WorkerSupervisor.dispatch                                      │
│   • new task_id (or resume from row)                            │
│   • write WorkerRunRow(status="running")                        │
│   • depth/concurrency check (existing _AgentTracker)            │
│   • asyncio.create_task(_run_to_completion(...))                │
│   • foreground: await deferred                                  │
│   • background: return task_id                                  │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  _run_to_completion (rooted in app's task group)                │
│   • drain runner.run_agent() AsyncIterator                      │
│   • accumulate output / messages                                │
│   • on terminal status → store.update + bus.post(WorkerEvent)   │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Bus event: type="worker", event="completed"                    │
│   payload: {task_id, originating_channel, output, ...}          │
└────────────┬────────────────────────────────────┬───────────────┘
             │                                    │
             ▼                                    ▼
   WorkerInboxObserver                  ConnectorOutboundObserver
   (voice/web sessions)                 (Telegram/Discord/Slack)
   • queue for next idle                • post to originating chat
   • surface as synthetic msg
```

Critical design rules:

1. **One code path for foreground and background.** Every dispatch
   creates a `WorkerRunRow`. Foreground = parent awaits a `Deferred`
   tied to terminal status. Background = parent returns the
   `task_id` immediately. No privileged "stream tokens directly into
   the parent" mode — Phase 3 would have to consolidate it anyway.
2. **Workers never speak to the user directly.** Completion posts a
   `BusMessage(type="worker")`. Whoever is listening on the
   originating conversation picks it up. Today that's the same agent
   loop. After Phase 3, it's the chat agent. Identical runtime.
3. **Workers root in the app, not the websocket.** Use the FastAPI
   app's lifespan-scoped task group, not the per-session scope.
   Disconnect ≠ cancellation.

### Dispatch lifecycle

Foreground (`run_in_background=False`, `task_id=None` — today's
default behavior, preserved):

```
agent(...) → dispatch → run_to_completion → status="completed"
                                          → terminal output returned
                                          → bus.post(worker.completed)
agent() returns the output (caller blocks).
```

Background (`run_in_background=True`):

```
agent(..., run_in_background=True)
  → dispatch → kick task → return {task_id, status: "running"}
  → caller continues with other work
  → some time later: run_to_completion finishes
  → status="completed", bus.post(worker.completed)
  → originating channel observer surfaces the result
```

Resume (`task_id="<id>"`):

```
agent(prompt="dig deeper into the second option", task_id="t_abc")
  → dispatch loads WorkerRunRow.messages_json
  → appends new prompt to messages
  → kicks new run_to_completion; same task_id, status="running"
  → terminal completion overwrites output, appends to messages_json
```

Stop (`agent_stop(task_id)`):

```
agent_stop(t_abc)
  → supervisor.cancel(t_abc)
  → cooperative interrupt via existing _interrupt_event mechanism
  → task transitions to status="cancelled"
  → bus.post(worker.cancelled)
```

### Channel-aware delivery

Completion delivery is the part that's specific to a hosted service
and needs the most care. The pieces:

**Origin capture.** When `agent(...)` is dispatched, the supervisor
records `originating_conversation_id` and `originating_channel` on
the row. Sources, in order of preference:
1. Explicit `channel_slug` passed via `ToolManager._session_id` /
   `set_session_id` plumbing (already exists for chart media).
2. The current `Brain` conversation id + the `connector` field on
   the most recent inbound message.
3. Fallback to `"voice:<session_id>"` or
   `"channel:<conversation_id>"`.

**Completion event.** On terminal status the supervisor posts:

```python
BusMessage(
    type="worker",
    source="worker_supervisor",
    payload={
        "event": "completed" | "failed" | "cancelled" | "timeout",
        "task_id": ...,
        "agent_def": ...,
        "description": ...,
        "originating_conversation_id": ...,
        "originating_channel": ...,
        "output": ...,           # truncated to <= 4 KB; full text in store
        "error": ...,            # if not completed
    },
)
```

**Observers.** Two new bus subscribers:

- `WorkerInboxObserver` — runs inside `Brain`. Queues completion
  events for the conversation it owns. Flushes per the voice-mode
  rules below by injecting a synthetic `system` message containing
  `[Worker '<description>' completed: <output>]`. The next user
  turn sees this message in context.
- `ConnectorOutboundObserver` — extends the existing
  `tool_output_observer` pattern. For non-voice channels (Telegram,
  Discord, Slack, Feishu, WeChat, web channel slugs), formats the
  result and posts via the connector's `send` method. Reuses the
  existing async-from-sync hop in `connectors/manager.py`.

**Voice-mode flush rules.**

Voice has the strongest etiquette requirements: we don't want to
talk over the user, and we don't want to surprise them with a
30-second TTS dump.

- If the user is currently speaking (VAD active) → defer.
- If the user finished speaking less than 2 seconds ago → defer.
- If `tts_enabled=false` → never speak; queue text-only.
- If TTS is currently playing the assistant's own response → defer
  to next idle.
- Otherwise → speak a short pre-amble ("That research is back —")
  followed by the worker's summary. Cap pre-roll at 4 seconds; if
  the output is longer, speak a one-sentence summary and append
  the full text to the conversation log so the user can ask
  follow-ups.

**Other-channel flush rules.** Simpler — post immediately, no
debouncing. Telegram/Discord/Slack handle their own ordering.

### Concurrency, depth, cancellation

Carries forward from today's `AgentRunner`:

- `MAX_AGENT_DEPTH = 3` and `MAX_CONCURRENT_AGENTS = 5` still apply,
  enforced via `WorkerStore.count_active(parent_task_id=...)` rather
  than the in-process `_AgentTracker`.
- Cancellation uses the existing `_interrupt_event` per-worker.
- On supervisor shutdown (server stop), in-flight workers are
  recorded as `cancelled` with `error="supervisor shutdown"`.
- On supervisor startup, any rows left in `running` from a prior
  process are reaped to `cancelled` (no zombie state).

### File-by-file change list

```
core/src/tank_backend/persistence/models/workers.py        NEW
core/src/tank_backend/persistence/models/__init__.py       export WorkerRunRow
core/src/tank_backend/persistence/migrations/versions/
    <ts>_add_worker_runs.py                                NEW

core/src/tank_backend/agents/store.py                      NEW (WorkerStore)
core/src/tank_backend/agents/supervisor.py                 NEW (WorkerSupervisor)
core/src/tank_backend/agents/runner.py                     refactor — dispatch via supervisor
core/src/tank_backend/agents/agent_tool.py                 + run_in_background, + task_id
core/src/tank_backend/agents/inbox_observer.py             NEW
core/src/tank_backend/agents/status_tools.py               NEW (agent_status, agent_stop, list_active_agents)
core/src/tank_backend/tools/manager.py                     register the three new tools

core/src/tank_backend/pipeline/processors/brain.py         wire WorkerInboxObserver; flush rules
core/src/tank_backend/connectors/manager.py                wire ConnectorOutboundObserver

core/src/tank_backend/api/server.py                        spawn supervisor in lifespan
core/src/tank_backend/api/routes/agents.py                 NEW: GET /api/agents, GET /api/agents/{id}, POST /api/agents/{id}/stop

core/src/tank_backend/llm/llm.py                           — no change (agent already concurrent-safe)
backend/agents/*.md                                        — no change to existing definitions

core/tests/test_worker_store.py                            NEW
core/tests/test_worker_supervisor.py                       NEW
core/tests/test_worker_inbox_observer.py                   NEW
core/tests/test_agent_status_tools.py                      NEW
core/tests/test_agent_tool_resume.py                       NEW
core/tests/test_brain_voice_flush_rules.py                 NEW

test/features/background_agents.feature                    NEW (E2E)
```

Estimated diff size: ~1,500 lines net. Bulk in supervisor + tests.

### Test plan

Per-piece unit tests:

- **Store** — round-trip a row; status transitions; count by parent;
  cleanup-on-startup reaps `running` rows.
- **Supervisor** — foreground dispatch returns inline; background
  dispatch returns immediately and resolves later; cancellation
  flips status; depth/concurrency limits trigger the same error
  shapes today's runner returns; resume re-runs with appended
  messages.
- **InboxObserver** — defers during user-speaking; emits synthetic
  message at next idle; respects `tts_enabled=false`.
- **Status tools** — `agent_status(wait=True)` blocks until
  terminal; `agent_stop` is idempotent on already-finished tasks;
  `list_active_agents` filters by status.
- **AgentTool resume** — passing `task_id` continues the same row;
  passing both `prompt` and `task_id` appends to messages.
- **Voice flush rules** — table-driven test over (vad_state,
  recent_user_speech, tts_playing, tts_enabled) → expected action.

Integration:

- **Brain integration** — full pipeline test: user dispatches
  background agent → supervisor runs to completion → inbox surfaces
  result on next idle → next user turn sees it in context.
- **Connector integration** — fake connector receives the post;
  format matches expected.

E2E:

- **`background_agents.feature`** — chat-mode user starts a
  background agent, sends a follow-up message immediately (proves
  parent isn't blocked), the background result lands in the
  conversation later as a system/assistant message pair.

### Risks & mitigations

| Risk | Mitigation |
|---|---|
| Worker outlives a websocket but the user expects a result on that socket — they reconnect with a new session id and can't find the task | `originating_conversation_id` is the routing key, not session id. Reconnections rejoin the conversation; the inbox surfaces pending events. |
| Bus delivery is sync; long worker outputs delay the loop | Truncate `output` in the bus payload to 4 KB; full text in the store. |
| Resume races with an already-running task | Supervisor rejects resume on `status="running"` rows with a clear error. The LLM can then call `agent_status` first. |
| Concurrent re-entry on the same `task_id` (parent calls `agent(task_id=X)` twice in one turn) | Same rejection; the second call gets a "task already in progress" error. |
| Migration on a populated `tank.db` | Pure additive — single `CREATE TABLE`. No risk to existing rows. |
| Approval prompts originating inside a background worker | Workers inherit the existing `ApprovalGateExecutor`. If a prompt originates in a background worker and the originating channel is unreachable, the worker fails with `error="approval needed but channel unavailable"`. Phase 3 / chat-agent has a better answer; for Phase 2, we accept this. |
| Voice TTS announcing background completion while the user is mid-thought | Flush rules above; conservative defaults (≥2 s post-speech idle). |

### Sequencing

Land in this order so each PR is reviewable on its own:

1. **Schema + migration + `WorkerStore`** (pure data layer; no behavior
   change). ✓ Shipped — `core/tests/test_worker_store.py` (20 tests).
2. **`WorkerSupervisor` + foreground path.** ✓ Shipped —
   `core/tests/test_worker_supervisor.py` (12 tests).
3. **Wire `AgentTool` through the supervisor.** Today's behavior
   preserved bit-for-bit (foreground only). ✓ Shipped —
   `core/tests/test_agent_tool_supervisor.py` (12 tests).
4. **Background path + worker-control tools + `WorkerInboxObserver`.**
   Adds `run_in_background=True`, `agent_status`, `agent_stop`,
   `list_active_agents`, and inbox-driven surfacing of terminal
   completions on the next user turn. Voice flush rules NOT
   implemented — Brain drains the inbox at the start of each user
   turn, which is voice-mode-safe by construction (TTS only fires
   when the user already spoke). ✓ Shipped —
   `core/tests/test_worker_supervisor_background.py` (6 tests),
   `core/tests/test_worker_tools.py` (8 tests),
   `core/tests/test_worker_inbox.py` (7 tests).
5. **REST routes + Brain integration test + end-to-end flow.**
   `/api/agents` (list, get) for the web UI panel; cancellation stays
   in-conversation via the `agent_stop` tool. ✓ Shipped —
   `core/tests/test_api_agents.py` (4 tests),
   `core/tests/test_brain_worker_inbox.py` (3 tests),
   `core/tests/test_background_agent_flow.py` (3 tests).
6. **Worker-initiated clarification (`ask_user` / `agent_reply`).** 
   Workers can pause mid-execution to ask the user a question. The
   worker calls `ask_user(question=...)` → supervisor transitions to
   `status="waiting"` → NotificationHub delivers the question →
   ChatAgent calls `agent_reply(task_id, answer)` → worker resumes
   with full message history + answer. ✓ Shipped —
   `core/tests/test_worker_pause_resume.py` (17 tests).
7. **Resume via `task_id`** — deferred. The schema and store already
   support it (`messages_json`, no terminal status guard yet); the
   piece left is wiring `task_id` through `AgentTool` so the LLM
   can extend a prior worker's context. Useful but not gating any
   user-visible flow today.
8. **Worker-initiated channel delivery for non-voice channels** —
   deferred. Today completions land in the conversation via the
   inbox observer, which covers chat-mode users. A connector
   outbound observer (Telegram/Discord/Slack) is the next
   independent PR.
9. **Voice flush rules** — only needed if/when we want the assistant
   to *spontaneously* announce completions instead of waiting for
   the next user turn. Deliberately not implemented.

### Phase 2 success criteria

- A user starts a long-running agent in chat, closes the page,
  reopens it, and sees the result in the conversation.
- A voice user says "go research X in the background" → keeps
  conversing → 30 seconds later hears "the research is back, here's
  the summary".
- A user says "now also check Y on that trip plan" → resumes the
  prior worker's context rather than starting fresh.
- A user says "stop the trip planning" → the agent identifies the
  task by description and cancels it.
- All eight verification-checklist steps pass; no regressions in
  existing 2,856 tests.

---

## Phase 3 — Chat-agent / worker split (speculative)

Speculative because it should be re-evaluated against real Phase 2
usage data before committing. The shape, if pursued:

**Roles.** The conversational LLM ("chat agent") owns the user
relationship: dialogue, presence, etiquette, surface of worker
status. Workers own the *work*: long tool chains, multi-step
research, anything that needs a fat context.

**Toolset partition.** Chat agent gets a small set: `agent` (which
becomes `dispatch_task` in spirit), `agent_status`, `agent_stop`,
`list_active_agents`, plus a "trivial-direct" group (`calculate`,
`get_time`, `get_user_memory`, `web_search` for one-shot facts,
`remember`). Workers get everything else.

**Question-back path.** Workers can park themselves
(`status="waiting"`) and post a question event. The
chat agent surfaces it; the user's answer becomes a resume input.
This pattern is already implemented in Phase 2 via `ask_user` /
`agent_reply` — Phase 3 inherits it unchanged.

**Cancel-by-description.** The chat agent uses
`list_active_agents()` plus a fuzzy-match step against the task
descriptions to map "stop the trip planning" → the right
`task_id`.

**What stays unchanged from Phase 2.** Worker runtime, schema,
delivery substrate, voice flush rules, REST routes, all four tool
shapes. The split is mostly a matter of:
- A new agent definition `chat.md` with a smaller toolset.
- An updated main system prompt: planning happens in the chat
  agent; ACT becomes worker dispatch.
- A "primary agent" toggle so the conversational LLM is the chat
  agent, not the all-tools agent.

**Honest tradeoffs from earlier discussion** (kept here so future
us doesn't re-litigate them):

1. Two-LLM cost — chat + worker contexts simultaneously. Mitigation:
   smaller/cheaper LLM for the chat agent.
2. Latency floor on trivial requests. Mitigation: trivial-direct
   tool boundary; revisit if it gets fuzzy.
3. Concurrency-bug surface area grows. The Phase 2 worker runtime
   already absorbs most of this.

### Phase 3 trigger conditions

Pursue Phase 3 only if at least one of:

- Users routinely run >1 worker in parallel and find the
  all-tools-on-one-LLM behavior confusing.
- Worker context windows are bumping limits even with compaction.
- Voice etiquette (interruptions, cross-talk between user
  conversation and worker reports) keeps regressing in ways that
  inline Phase 2 logic can't fix cleanly.

If none of these manifest, Phase 2 alone is the production end
state and Phase 3 stays parked.

---

## Parking lot — interesting ideas, deliberately deferred

Captured here so we don't lose them and don't accidentally
re-discover them as if they were new.

### Plan mode as a hard read-only gate (à la OpenCode / Claude Code)

OpenCode's `plan_enter`/`plan_exit` tools and Claude Code's
`EnterPlanMode` both enforce read-only via a permission system that
*denies* `edit`/`write`/`bash` until the user approves a plan.
Useful for coding tools where the unwanted blast radius is silent
file mutation.

Why deferred for Tank: Tank's mutating actions (sending messages,
scheduling jobs, updating memory) are visible side effects, not
silent code edits. A hard gate is the wrong shape — what Tank needs
is the *outline + go* rhythm of Gap A′, which is collaborative not
approval-gated. Reconsider if Tank ever takes on responsibilities
where rollback is genuinely hard (autonomous external transactions,
irreversible API calls without audit).

### Worktree isolation for sub-agents

Claude Code's `isolation: "worktree"` and OpenClaw's
`SUBAGENT_SPAWN_SANDBOX_MODES = ["inherit", "require"]` create
per-agent git worktrees so experimental code changes are
reversible.

Why deferred for Tank: Tank is a hosted service — there's no
per-user repo, the user often isn't on the same machine, and
Tank's existing Docker sandbox already covers untrusted code
execution. Reconsider only if Tank sprouts a "work on the user's
local repo over a tunnel" feature.

### Mixture-of-agents primitive

Hermes's `mixture_of_agents_tool` runs the same prompt against N
reference models in parallel, then a stronger aggregator
synthesizes their answers. Useful for hard reasoning (the paper
claims SOTA on coding/math/analysis).

Why deferred for Tank: the typical Tank failure mode for "plan my
trip" isn't reasoning depth, it's information gathering. Skip
unless quality complaints on hard reasoning queries materialize.
Slots cleanly into Tank's existing `LLM` profile machinery as a
pure tool when needed.

### OpenClaw's three-axis sub-agent spawn

OpenClaw factors sub-agent spawn into three orthogonal modes:
- `["run", "session"]` — one-shot vs persistent.
- `["isolated", "fork"]` — fresh context vs forked from parent.
- `["inherit", "require"]` — sandbox policy.

Why deferred for Tank: powerful but expensive to model correctly.
Phase 2's `WorkerRunRow` covers `run`/`isolated`/`inherit` (the
common case). The other axes can layer on later as nullable
columns — `spawn_mode`, `context_mode`, `sandbox_mode` — without
breaking the schema.

### Worker-initiated clarification questions

~~A worker that needs information from the user could post a
`clarification_needed` event, park itself, and resume on receipt
of an answer. Phase 2 deliberately omits this because routing the
question through the conversational layer is fundamentally a
chat-agent responsibility (the chat agent decides *when* to
surface the question — not during the user's own monologue, not
during a TTS playback). Phase 3 is the right home.~~

**Implemented in Phase 2** (step 6 in the sequencing above). The
terminate-and-resume pattern avoids coroutine serialization:

1. Sub-agent calls `ask_user(question=...)` tool.
2. `LLM.chat_stream()` breaks the tool loop after executing it.
3. `WorkerSupervisor._consume_stream()` detects the tool result,
   returns an `_AskUserResult` to `_drive_to_completion`.
4. Supervisor transitions to `status="waiting"`, persists full
   message history via `WorkerStore.pause()`.
5. Bus event → `NotificationHub` queues and delivers the question.
6. ChatAgent calls `agent_reply(task_id, answer)`.
7. Supervisor appends the answer to messages, transitions back to
   `running`, re-dispatches via `_drive_to_completion` with the
   accumulated messages. The LLM sees full history and continues.

### Mixture-of-workers (parallel research with synthesis)

A Tank-shaped variant of mixture-of-agents: dispatch N workers on
the same research question with different angles, then a thin
"synthesizer" worker reconciles their findings before returning to
the chat agent. Speculative; only pursue if Phase 2 reveals that
single-worker research consistently underperforms parallel
research by N independent agents.

### Cross-process worker supervision

Workers today live in the FastAPI process. A future Tank
deployment with multiple worker processes (or a separate worker
service) would need a Postgres-backed supervisor with row-level
locking, heartbeats, and lease semantics. Phase 2 explicitly
skips this — single-process is fine for the foreseeable hosted
deployment.

### Job ↔ Worker unification

Tank's existing `jobs` subsystem (cron-scheduled headless agents)
and Phase 2 `workers` (interactive sub-agents that may run
backgrounded) are two flavors of the same thing: a stored agent
run with delivery to channels. They could share infrastructure
(the supervisor, the row schema, the delivery observers).

Worth doing eventually — having two "headless agent execution"
paths is duplication. Deferred from Phase 2 because the unifying
refactor is large and the existing `JobStore`/`AutonomousRunner`
work; the pragmatic Phase 2 path is to mirror the patterns
(`WorkerStore` looks like `JobStore`; `WorkerSupervisor` looks
like `AutonomousRunner`) and unify in a later cleanup phase.

### `list_active_agents()` as the seed of chat-agent introspection

Phase 2's `list_active_agents` tool already gives the main agent
the data it needs to answer "what am I working on?", "stop the
trip planning one", "how's the research going?". Phase 3's chat
agent calls the same function unchanged. Worth being explicit so
we don't separately invent a different roster API later.

---

## Cross-phase invariants

These hold across all phases and must not be silently broken:

1. **Tool names are stable.** `agent`, `agent_status`, `agent_stop`,
   `list_active_agents`. The LLM's vocabulary doesn't churn between
   phases.
2. **Foreground and background share one code path.** No special
   "stream tokens directly into parent" mode.
3. **Workers don't speak directly.** Delivery goes through the bus.
4. **Origin is conversation-id-keyed, not session-id-keyed.**
   Reconnection works.
5. **The eight-step verification checklist passes.** No phase ships
   with red tests, including pre-existing ones.
