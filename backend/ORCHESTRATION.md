# Workflow & Orchestration

This document describes how Tank structures multi-step work today, where the
design is going, and which patterns are deliberately deferred. It is the
single source of truth for "how should the agent loop be shaped".

The goal of this phase is workflow and orchestration only. The future
chat-agent / worker split is named where it matters, but no work in this
phase commits Tank to that topology.

## Guiding principle

**Explore-plan-act is a workflow shape, not an agent topology.** The shape
is stable across architectures; only where each phase lives changes.

| Phase | Today (single LLM loop) | Future (chat agent + workers) |
|---|---|---|
| Explore | LLM emits parallel read-only tool calls in one turn | Chat agent dispatches an exploration worker |
| Plan | LLM produces a brief outline as text, then continues | Chat agent reasons over findings; presents plan |
| Act | LLM emits mutating tool calls | Chat agent dispatches an execution worker |

The corollary: **don't reify a phase into a sub-agent until evidence shows
the phase needs its own context.** A phase is free to migrate; a sub-agent
is a contract.

## Tank's current state

Mapped against the three patterns at the source of this work:

| Pattern | Status |
|---|---|
| Explore-plan-act | Absent. The main agent jumps straight to tool calling. |
| Context-isolated subagents | Present, basic. `AgentTool` → `AgentRunner.run_agent()` with depth/concurrency limits. `background=True` is plumbed but doesn't actually decouple — the parent iterates the child to completion. No resumable `task_id`. No channel-aware delivery. |
| Fork-join parallelism | Half-present. `_CONCURRENT_SAFE_TOOLS = frozenset({"agent"})` — only the agent tool runs in parallel. Read-only tools like `web_search`, `file_read`, `web_fetch` run sequentially even when the LLM emits them in one turn. |

Existing strengths to preserve:

- Bus + observers (`pipeline/bus.py`) for cross-cutting state.
- `ApprovalGateExecutor` + three-way `PolicyVerdict` for sensitive tools.
- Markdown agent definitions with frontmatter (`backend/agents/*.md`).
- Single-loop streaming via `LLMAgent` — no graph framework tax.
- Unified `tank.db` with Alembic migrations and shared ORM `Base`.

## Phase 1 — what we're building

Three items, ordered so each is reversible and the next builds on it.

### Gap D — Broaden `_CONCURRENT_SAFE_TOOLS`

**What.** Expand the set of tools that the LLM loop runs in parallel via
`asyncio.gather` when emitted in the same assistant turn.

**Why.** This is the EXPLORE primitive. With `agent` as the only
concurrent-safe tool today, parallel research isn't possible inside the
main agent — every `web_search` + `file_read` + `web_fetch` triplet runs
sequentially. Voice users feel every saved second.

**How.** Edit `backend/core/src/tank_backend/llm/llm.py`:

```python
_CONCURRENT_SAFE_TOOLS = frozenset({
    "agent",
    "file_read", "file_list", "file_search",
    "web_search", "web_fetch",
    "get_weather", "get_time", "calculate",
    "get_user_memory", "get_context_usage",
})
```

Excluded (mutating or stateful): `file_write`, `file_edit`, `file_delete`,
`run_command`, `persistent_shell`, `manage_process`, `confirm_action`,
`remember`, `consolidate_memory`, `compact_context`, channel/job tools.

**Risk.** Low. The `asyncio.gather` machinery already exists and is
exercised by parallel `agent` calls today. Read-only tools are by
construction concurrency-safe.

### Gap A′ — Explore-plan-act in the system prompt

**What.** Teach the main agent the explore-plan-act loop as a phase shape.
No new tool, no new agent type, no read-only mode gate.

**Why.** Tank's typical complex request ("plan a 3-day trip", "research
options for X", "compare A and B") benefits from a brief outline step
before fan-out. Without it, the LLM tends to fire searches in poor order
or miss a category. With the prompt nudge plus Gap D's parallel exploration,
the natural rhythm becomes: parallel lookups → 1-3 line outline → execute.

**Why not a `planner` sub-agent.** Reifying planning into a sub-agent
hardcodes it onto the executor layer. When the chat-agent split happens,
planning becomes a chat-agent responsibility — migrating a sub-agent is
expensive; migrating a phase is free.

**How.** Edit `Brain._build_main_agent_prompt` to append the loop shape.

**Override hooks.** "Just do it", "skip the plan", "go ahead" → straight
to ACT. "Wait, let's think first", "what's your plan" → forces the loop.
These are LLM-level cues, not code.

**Risk.** Low. Pure prompt change; if it hurts simple-request latency,
revert in one commit.

### Worker runtime — Gaps B + C + E unified (deferred to Phase 2)

A unified package combining real backgrounding, resumable `task_id`, and
channel-aware delivery. Sized at 1-2 weeks; not in this phase. The shape
locked in here so Phase 1 work doesn't paint into a corner:

```python
# Tool surface — same across today's main agent and tomorrow's chat agent.

agent(
    prompt: str,
    subagent_type: str = "coder",
    description: str = "",
    run_in_background: bool = False,   # Gap B
    task_id: str | None = None,         # Gap C — resume an existing run
)

agent_status(task_id, wait=False, timeout_ms=60000) -> {state, output}
agent_stop(task_id) -> {state}
list_active_agents() -> [{task_id, agent_def, description, status, started_at}]
```

Backed by a new ORM table:

```python
class WorkerRunRow(Base):
    task_id: str          # primary key, returned to LLM
    agent_def: str
    description: str
    prompt: str
    status: Literal["running", "completed", "failed", "cancelled"]
    originating_conversation_id: str
    originating_channel: str        # "voice", "telegram:123", etc.
    parent_msg_id: str | None
    started_at: float
    completed_at: float | None
    output: str
    error: str | None
```

Two architectural rules to honor when this lands:

1. **Foreground and background share one code path.** Every dispatch
   creates a `WorkerRunRow`. Foreground = parent waits for `status !=
   "running"`. Background = parent returns the `task_id` immediately. No
   privileged "stream tokens directly into the parent" path — the future
   chat-agent split would need to consolidate it anyway.
2. **Don't bake "the LLM that dispatched is the LLM that delivers" into
   the runtime.** Completion posts a bus event with
   `originating_conversation_id` + `originating_channel`. Whoever is
   currently listening on that conversation picks it up. Today that's the
   same agent loop. Tomorrow it's the chat agent. Identical runtime.

Until Phase 2 lands, the existing foreground-only `agent` tool stays
unchanged.

## Migration path to the future chat-agent split

When the chat agent moves to its own actor (Phase 3+), the changes are
mostly additive:

- The dispatching LLM gets a smaller toolset (chat-agent boundary).
- The conversational LLM's system prompt updates: planning still happens,
  but ACT becomes worker dispatch instead of inline tool calls.
- The exploration phase becomes a worker dispatch instead of inline
  parallel calls. Gap D's concurrent-safe set still applies — just inside
  the worker.

What does *not* change: the worker runtime, the `WorkerRunRow` schema,
the four dispatch tools, the bus delivery contract, the agent definitions.

## Parking lot — interesting ideas, deliberately deferred

Captured here so we don't lose them and don't accidentally re-discover
them as if they were new.

### Plan mode as a hard read-only gate (à la OpenCode / Claude Code)

OpenCode's `plan_enter`/`plan_exit` tools and Claude Code's `EnterPlanMode`
both enforce read-only via a permission system that *denies* `edit`/`write`/
`bash` until the user approves a plan. Useful for coding tools where the
unwanted blast radius is silent file mutation.

Why deferred for Tank: Tank's mutating actions (sending messages,
scheduling jobs, updating memory) are visible side effects, not silent
code edits. A hard gate is the wrong shape — what Tank needs is the
*outline + go* rhythm of Gap A′, which is collaborative not approval-gated.
Reconsider if Tank ever takes on responsibilities where rollback is
genuinely hard (e.g., autonomous external transactions, irreversible API
calls without audit).

### Worktree isolation for sub-agents

Claude Code's `isolation: "worktree"` and OpenClaw's
`SUBAGENT_SPAWN_SANDBOX_MODES = ["inherit", "require"]` create per-agent
git worktrees so experimental code changes are reversible.

Why deferred for Tank: Tank is a hosted service — there's no per-user
repo, the user often isn't on the same machine, and Tank's existing Docker
sandbox already covers untrusted code execution. Reconsider only if Tank
sprouts a "work on the user's local repo over a tunnel" feature.

### Mixture-of-agents primitive

Hermes's `mixture_of_agents_tool` runs the same prompt against N reference
models in parallel, then a stronger aggregator synthesizes their answers.
Useful for hard reasoning (the paper claims SOTA on coding/math/analysis).

Why deferred for Tank: the typical Tank failure mode for "plan my trip"
isn't reasoning depth, it's information gathering. Skip unless quality
complaints on hard reasoning queries materialize. Slots cleanly into
Tank's existing `LLM` profile machinery as a pure tool when needed.

### Full chat-agent / worker split

The endpoint of this roadmap: the conversational LLM becomes a thin
manager that owns the user relationship; all multi-step work goes to
workers. Tasks survive disconnect. Workers report back through whichever
channel the user is on at completion time. The user can ask "what are
you working on?" and stop tasks by description.

Why deferred for Tank: Phase 1 is a 1-day investment; Phase 2 (worker
runtime) is 1-2 weeks; the full split is another 1-2 weeks on top. Ship
the foundation first, gather signal on real usage, then commit to the
split when the cost/benefit is clear. Phase 1 and Phase 2 are explicitly
designed so the split is a refactor, not a rewrite.

### `list_active_agents()` as the seed of chat-agent introspection

Once the worker runtime exists (Phase 2), this tool already gives the
main agent the data it needs to answer "what am I working on?", "stop
the trip planning one", "how's the research going?". The future chat
agent calls the same function unchanged. Worth being explicit so we
don't separately invent a different roster API later.

### OpenClaw's three-axis sub-agent spawn

OpenClaw factors sub-agent spawn into three orthogonal modes:
- `["run", "session"]` — one-shot vs persistent.
- `["isolated", "fork"]` — fresh context vs forked from parent.
- `["inherit", "require"]` — sandbox policy.

Why deferred for Tank: powerful but expensive to model correctly.
Phase 2's `WorkerRun` covers `run`/`isolated`/`inherit` (the common case).
The other axes can layer on later without breaking the schema —
`spawn_mode`, `context_mode`, `sandbox_mode` are nullable columns.

## Phase 1 success criteria

- `_CONCURRENT_SAFE_TOOLS` includes the read-only set; a unit test asserts
  membership and that the `_is_concurrent_safe` helper agrees.
- `Brain._build_main_agent_prompt` returns a string containing the
  EXPLORE / PLAN / ACT phase shape; a unit test pins the shape.
- Full verification checklist (lint, types, unit tests, dev-server reload,
  E2E) passes.

Phase 1 ships value immediately (parallel exploration → measurable voice
latency win) while doing zero work that Phase 2 or the eventual chat-agent
split will have to undo.
