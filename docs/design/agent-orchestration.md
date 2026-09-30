# Agent Orchestration

This document describes Tank's agent orchestration system — how the main agent handles conversations, delegates work to sub-agents, and manages tool approval.

## Architecture Overview

Tank uses a single main agent with access to ALL tools. For complex tasks, the main agent spawns sub-agents via the `agent` tool. Sub-agents are defined as markdown files and run through the `WorkerSupervisor` → `AgentRunner.run_agent()` execution path.

```
User message
  → BrainProcessor
    → AgentGraph
      → Main LLMAgent (all tools including `agent`)
        ├─ Handles simple tasks directly (weather, time, chat, file ops, shell)
        ├─ Spawns sub-agents via `agent` tool for complex/isolated tasks
        │    → WorkerSupervisor.run_foreground / run_background
        │      → AgentRunner.run_agent()
        │        → LLMAgent with filtered tools + own system prompt
        │        → Approval inherited from parent
        │        → Outputs streamed via Bus
        │    → Terminal result surfaced via NotificationHub
        └─ Synthesizes results into a response
          → Streamed to TTS
```

Key files:

| File | Purpose |
|------|---------|
| `agents/base.py` | `Agent` ABC, `AgentState`, `AgentOutput`, `AgentOutputType` |
| `agents/llm_agent.py` | `LLMAgent` — agent that runs via LLM with tool calling and approval |
| `agents/runner.py` | `AgentRunner` — single execution method for all agents |
| `agents/agent_tool.py` | `AgentTool` — the `agent` tool for spawning sub-agents |
| `agents/definition.py` | `AgentDefinition` — model + loader from markdown files |
| `agents/graph.py` | `AgentGraph` — orchestrator loop, streams outputs |
| `agents/store.py` | `WorkerStore` — SQLite-backed persistence for worker runs |
| `agents/supervisor.py` | `WorkerSupervisor` — lifecycle owner for all worker dispatches |
| `agents/notification_hub.py` | `NotificationHub` — cohort-aware delivery of worker results |
| `agents/worker_tools.py` | `agent_status`, `agent_stop`, `list_active_agents`, `agent_reply` |
| `agents/ask_user_tool.py` | `AskUserTool` — sub-agent tool to pause and ask questions |
| `agents/approval.py` | `ApprovalManager`, `ToolApprovalPolicy` |
| `llm/llm.py` | `LLM.chat_stream()` — streaming with tool execution loop |

## Worker Runtime (Phase 2)

Every `agent(...)` dispatch goes through the `WorkerSupervisor`, which persists a `WorkerRunRow` in SQLite and drives the agent to completion. Workers survive WebSocket disconnects and report results to the originating conversation.

### Worker Lifecycle

```
agent(prompt, subagent_type, run_in_background=False)
  → AgentTool.execute()
    → WorkerSupervisor.run_foreground() or .run_background()
      → WorkerStore.create(status="running")
      → _drive_to_completion()
        → _consume_stream() drains AgentRunner output
        → On success: WorkerStore.finish(status="completed")
        → On failure: WorkerStore.finish(status="failed")
        → On ask_user: WorkerStore.pause(status="waiting")
      → Bus event posted → NotificationHub delivers result
```

### Worker Statuses

| Status | Meaning |
|--------|---------|
| `running` | Worker is actively executing |
| `waiting` | Worker paused, awaiting user clarification via `agent_reply` |
| `completed` | Worker finished successfully |
| `failed` | Worker hit an error |
| `cancelled` | Worker was stopped via `agent_stop` or supervisor shutdown |
| `timeout` | Worker exceeded its time limit |

### Foreground vs Background

- **Foreground** (`run_in_background=False`): caller blocks until the worker completes. Result returned as the `agent` tool's output.
- **Background** (`run_in_background=True`): caller gets `{task_id, status: "running"}` immediately. The worker runs as an `asyncio.Task`. Terminal result delivered via `NotificationHub` on the next user turn or proactively.

### Tool Surface

```python
agent(
    prompt: str,
    subagent_type: str = "coder",
    description: str = "",
    run_in_background: bool = False,
)

agent_status(task_id, wait: bool = False, timeout_ms: int = 60000)
agent_stop(task_id)
list_active_agents()
agent_reply(task_id, answer)  # resume a waiting worker
```

### NotificationHub (Cohort-Aware Delivery)

When background workers complete, `NotificationHub` queues notifications per conversation and delivers them:

- **Cohort tracking**: tracks in-flight workers per conversation. Waits for all workers in a cohort to finish before delivering (avoids partial results).
- **Proactive delivery**: injects a synthetic `__notification__` event into the pipeline when the brain is idle, triggering a notification turn.
- **Passive fallback**: Brain calls `hub.drain(conversation_id)` at the start of each user turn, injecting queued notifications as system messages.
- **Question delivery**: `waiting` events bypass cohort wait and deliver immediately (high priority).

## Worker Pause-and-Ask

Sub-agents can pause mid-execution to ask the user a question. This uses a terminate-and-resume pattern — the worker's full message history is persisted to the database, and execution restarts with the accumulated context plus the user's answer.

### Flow

```
Sub-agent LLM calls ask_user(question="Which option?")
  → AskUserTool.execute() returns ToolResult(content=question)
  → LLM.chat_stream() breaks the tool loop (no further LLM calls)
  → LLMAgent.run() finishes, yields DONE with turn_messages in metadata
  → WorkerSupervisor._consume_stream() detects ask_user in TOOL_RESULT events
  → Returns _AskUserResult to _drive_to_completion()
  → WorkerStore.pause(task_id, messages=full_history, question=...)
  → Bus event "waiting" posted
  → NotificationHub queues high-priority notification
  → Brain surfaces question to user on next turn

User answers (via ChatAgent calling agent_reply):
  → AgentReplyTool.execute(task_id, answer)
  → WorkerSupervisor.resume_with_answer(task_id, answer)
    → Appends answer to persisted messages
    → WorkerStore.resume(task_id) → status back to "running"
    → Re-dispatches _drive_to_completion with accumulated messages
    → LLM sees full history + answer, continues naturally
```

### Detection Mechanism

The `ask_user` tool is detected by its tool name in the event stream metadata (`event.metadata.get("name") == "ask_user"`). There is no magic sentinel string — the tool returns the question text as its content.

Two components collaborate:
1. **`llm.py`** — breaks the tool iteration loop after executing any tool named `ask_user`, so the agent run ends cleanly.
2. **`supervisor._consume_stream`** — watches for `TOOL_RESULT` events with `name="ask_user"`, captures the question, and returns it via `_AskUserResult` when `DONE` arrives.

### Sub-Agent Prompt Injection

`AgentRunner._build_sub_agent_prompt()` appends clarification guidance to every sub-agent's system prompt, instructing them to call `ask_user` instead of writing questions as text output.

## How It Works

### Main Agent

The main agent has access to every registered tool — file operations, shell commands, web search, skills, and the `agent` tool. The system prompt guides when to delegate vs handle directly:

- Simple tasks (weather, time, calculations, quick file reads): handle directly
- Complex tasks (multi-step coding, research, planning): spawn a sub-agent
- Parallel tasks: call `agent` multiple times with `run_in_background=True`

### Sub-Agents via `agent` Tool

When the LLM calls `agent(prompt="...", subagent_type="coder")`:

1. `AgentTool.execute()` looks up the agent definition
2. Calls `WorkerSupervisor.run_foreground()` which:
   - Checks depth limit (max 3 levels deep)
   - Checks concurrent agent limit (max 5)
   - Creates a `WorkerRunRow` in the database
   - Calls `AgentRunner.run_agent()`:
     - Creates an `LLMAgent` with the definition's system prompt + ask_user guidance
     - Filters tools: all tools minus `disallowed_tools` minus global disallowed set, plus `ask_user`
     - Passes `approval_manager` and `approval_policy` (inherited from parent)
     - Streams all `AgentOutput` items back
3. The result text is returned to the main agent as the tool result

### Agent Definitions

Agents are defined as markdown files with YAML frontmatter in `backend/agents/`:

```yaml
# backend/agents/coder.md
---
name: coder
description: "Execute code, manage files, run shell commands"
disallowed-tools: []
skills: []
max-turns: 25
---

You are a coding agent. Execute commands and modify files to complete tasks.
Do NOT just describe what you would do — actually execute the commands.
```

Default agents:

| Agent | Description | Disallowed Tools |
|-------|-------------|-----------------|
| `coder` | Code execution, file ops, shell | None |
| `researcher` | Web search, information gathering | file_write, file_delete, run_command, persistent_shell, manage_process |
| `tasker` | Task planning, coordination | file_write, file_delete, run_command, persistent_shell |
| `verifier` | Code verification (background) | file_write, file_delete, persistent_shell, manage_process, agent |

Definition loading priority: project (`backend/agents/`) > user (`~/.tank/agents/`).

### Tool Filtering

Sub-agents use a **disallowed tools** pattern (not an allowlist):

1. Start with ALL registered tools
2. Remove the agent definition's `disallowed_tools`
3. For sub-agents, also remove global disallowed set: `agent`, `use_skill`, `list_skills`, `create_skill`, `install_skill`
4. Add `ask_user` (available to sub-agents only, excluded from the main ChatAgent)

This means sub-agents can't spawn further sub-agents by default (the `agent` tool is globally disallowed for sub-agents).

### Parallel Execution

When the LLM calls multiple `agent` tools in a single turn, they can run concurrently. The `agent` tool supports `run_in_background=true` for parallel execution. The concurrency mechanism in `LLM.chat_stream()` detects concurrent-safe tool calls and runs them via `asyncio.gather`.

### Langfuse Tracing

Each `LLMAgent` passes trace metadata to `LLM.chat_stream()`:
- `name`: `agent:{agent_name}` (e.g., `agent:chat`, `agent:agent_coder`)
- `metadata`: `{"agent_name": name}`

This appears in Langfuse as separate traces per agent, filterable by name.

The OpenAI integration registers tracing automatically when imported; Tank does
not register it again. `LANGFUSE_TRACING_ENABLED=false` skips initialization and
instrumentation at startup even when keys are configured. Restart the backend
after changing this setting.

### Thinking History

`LLM.chat_stream` preserves streamed `reasoning_content` (or the compatible
`reasoning` field) on assistant messages. `LLMAgent` exposes completed turn
messages in `state.metadata` while streaming, so errors or interruption still
allow Brain to persist their original reasoning and tool results.

For `deepseek-flash` and `deepseek-pro` requests with tools, assistant history
without reasoning triggers a request using `thinking.type=disabled`, with a
warning listing the affected message indices. This supports older or non-thinking
history without inventing reasoning or changing stored messages/profile settings.
Complete history follows the configured thinking behavior. This also applies to
background completion notifications, which append a system message to history.

## Approval System

### Two-Tier Approval

| Tool category | Mechanism | Granularity |
|---------------|-----------|-------------|
| Sandbox tools (`run_command`, `persistent_shell`) | `ToolApprovalPolicy` in `LLMAgent` | Per-tool-name |
| File tools (`file_read`, `file_write`, etc.) | `ApprovalCallback` inside `execute()` | Per-path + per-operation |

### Approval Flow

1. `LLMAgent` intercepts `TOOL_EXECUTING` output
2. Checks `ToolApprovalPolicy.needs_approval(tool_name)`
3. If approval needed: creates `ApprovalRequest`, yields `APPROVAL_NEEDED`
4. `ApprovalManager` holds a Future — client notified via WebSocket
5. User approves/rejects via REST API or voice
6. Agent resumes with tool result or rejection notice

Sub-agents inherit the parent's `approval_manager` and `approval_policy` — same approval rules apply.

### Approval Policies

Configured in `config.yaml`:

```yaml
approval_policies:
  always_approve:
    - get_weather
    - get_time
    - calculate
  require_approval:
    - run_command
    - persistent_shell
    - manage_process
  require_approval_first_time:
    - web_search
    - web_fetch
```

## Configuration

```yaml
agents:
  llm_profile: default
  dirs:
    - ../agents              # project-level agent definitions
    - ~/.tank/agents         # user-level agent definitions
  max_depth: 3               # max sub-agent nesting depth
  max_concurrent: 5          # max parallel background agents

notifications:
  enabled: true
  proactive_delivery: true
  settle_seconds: 1.0        # wait after cohort settles before delivering
  max_wait_seconds: 60.0     # safety net — deliver even if workers still in-flight
```

### Limits

| Limit | Default | Where |
|-------|---------|-------|
| Max agent depth | 3 | `WorkerSupervisor` |
| Max concurrent agents | 5 | `WorkerSupervisor` |
| Max turns per agent | 25 | `AgentDefinition.max_turns` |
| AgentGraph iterations | 5 | `AgentGraph` |
| LLM tool iterations | 10 | `LLM.chat_stream()` |
| Approval timeout | 120s | `ApprovalManager` |

## Gotchas

1. **Main agent has ALL tools.** Unlike the old orchestrator/worker pattern, the main agent can call `run_command`, `file_write`, etc. directly. The system prompt guides when to delegate vs handle directly — this is an LLM judgment call, not a code constraint.

2. **Sub-agents can't spawn sub-agents by default.** The `agent` tool is in the global disallowed set for sub-agents. This prevents infinite recursion. To allow it, remove `agent` from a specific agent definition's `disallowed_tools` — but be careful with depth limits.

3. **Agent definitions are loaded at startup.** Changes to `backend/agents/*.md` files require a server restart (or hot-reload via watchfiles). The definitions are not re-scanned per request.

4. **Concurrent execution requires the `agent` tool to be concurrent-safe.** Currently, `agent` tool calls run sequentially unless `run_in_background=true` is set. The `_CONCURRENT_PREFIXES` in `llm.py` controls which tools run in parallel.

5. **Approval timeout is silent.** If the user doesn't respond within 120s, the approval request times out and the tool call fails. The agent sees a timeout error.

6. **Langfuse tracing uses `name` and `metadata` kwargs only.** The Langfuse v4 SDK's `OpenAiArgsExtractor` only extracts `name`, `metadata`, `trace_id`, `parent_observation_id` from kwargs. Other keys (`tags`, `session_id`) leak through to the OpenAI API and cause errors.

7. **`ask_user` is sub-agent only.** The main ChatAgent does NOT have `ask_user` — it talks to the user directly. Only workers dispatched via `agent(...)` get this tool injected.

8. **Worker pause persists full message history.** When a worker calls `ask_user`, all messages up to that point (including the ask_user tool call and result) are serialized to `messages_json` in the database. On resume, the LLM sees the complete conversation history.

## Plugin task agents

An agent definition may select `extension: plugin:extension` with a manifest
`type: subagent`. This is mutually exclusive with the retained `engine` field.
Factories receive only `subagents.<extension>.config`; runtime authority is
provided separately in SubAgentContext. Requests contain the task, assembled
context (definition prompt, applicable workspace and security rules), stable
worker task_id and optional `task_input`, not the main conversation's history.
`task_input` is an extension-only JSON object, limited to 64 KiB of compact UTF-8
JSON and 16 nesting levels. Core validates JSON types and size; the plugin owns
domain validation. Detached input is persisted independently of chat messages.
The existing Markdown directory loader supplies the dispatch catalog.

AgentTool parks one task approval listing all manifest permissions (desktop,
shell, filesystem, network); a one-use token is bound to the original task/type,
permissions and canonical structured input.
The token remains inactive until ConfirmActionTool invokes the runtime-only
on_confirmation callback; rejection invalidates it. Re-entry also checks that
the manifest permission scope is unchanged. Supervisor passes the explicit grant
and task deadline into Runner. SubAgent
plugins are trusted Python code; these approvals are not a sandbox or substitutes
for OS file/network isolation. SDK native adapters reuse the host file/command
policies; hard denials remain effective even with an approved task grant.

SubAgentAdapter defers DONE until producer/environment/client cleanup completes.
It binds `context.runtime` to the original task ID and closes its business gate
before cleanup. After closing the output iterator, it closes the runtime (joining
in-flight operations and releasing runtime-owned resources), then calls plugin
`aclose()` even if runtime cleanup failed. `SubAgent` owns the plugin resource
collection and closed state and provides the cleanup implementation. Subclasses
call `super().__init__(cleanup_timeout=...)`, register release callbacks through
`own_resource(name, release)`, and call `check_open()` at run entry; they do not
implement a cleanup loop or close the borrowed runtime. The inherited cleanup
works before the first run and shares its outcome, including failures, across
repeated calls. Computer Use registers its channels; N2 SDK registers producer,
SDK, environment and client releases, preserving producer-first shutdown. Provider
release details remain in callbacks; reverse order, timeouts and failure continuation
belong to the shared implementation. Neither concrete plugin closes its resource
collection from `run()`; direct consumers outside the Adapter must use `aclose()`
in `finally`. Factories
assemble configuration/strategy objects without opening external resources; resource
injection remains supported for tests and compatibility. Synchronous output iterator
creation failures also enter the Adapter cleanup path.

Registered trusted adapters use core `TaskOperation` handles;
arguments cannot select permissions or substitute another operation. The runtime
checks original authority, cancellation, deadline and read/action quotas before
and after asynchronous preflight, retains bounded call records, and never replays
an operation with an unknown effect. `returned` means the adapter returned, not
that its business postcondition succeeded. Computer Use's offline observation and
dispatch paths, N2 SDK primitives and the legacy N2 desktop executor use this
entry. LLMAgent retains AllowlistExecutor/ApprovalGateExecutor and rechecks the
same task context after asynchronous approval.

Core `TaskResources` handles idempotent reverse-order release, bounded waits and
continuation after failures. Borrowed leases must register detach callbacks; shared
host clients are not task-owned. Runtime cleanup joins cooperative in-flight work,
then releases registered resources even after authorization/deadline expiry. An
uncooperative callback produces unconfirmed cleanup, not a claim of OS termination.
An optional host audit callback is required when configured: failure or cancellation
latches the runtime closed to subsequent business calls. Ordinary observer failures
are logged without changing execution. Supervisor injects required WorkerStore audit for managed extension/engine tasks.
TaskResources.acquire validates capacity before synchronous creation/registration.
Ordinary model telemetry uses bounded Bus publication; required audit failures
stop business calls. Unwired benchmark transports remain rejected.

Legacy `stop_reason=final_answer` still completes. Plugins can instead return
`TaskResult.to_output()`: a versioned result with completed / partial / unknown /
needs_input / stopped, summary, reason and opaque JSON details. Its status must
match stop_reason. These are distinct terminal worker states, persisted and
returned by agent/agent_status and the REST API, with matching background
notifications. The existing HUD marks incomplete outcomes as unsuccessful and
shows their status and summary. Bare unknown or absent terminal reasons still
fail; timeout maps to timeout, and cooperative cancellation maps to cancelled.
Cleanup failure overrides completion and quarantines the desktop. If a structured
result was already received, its evidence survives with status/cleanup unknown.
Only successful host cleanup sets cleanup=confirmed.
Cleanup runs as a bounded task that is joined even if the caller is cancelled
repeatedly. A stop or deadline during cleanup keeps the desktop lock until cleanup
finishes. On successful cleanup the worker still reports cancelled/timeout, with
any received TaskResult preserved as stopped and cleanup=confirmed. Cleanup failure
takes precedence, produces unknown, and quarantines the desktop. If both the
producer and its cleanup fail, the producer's received evidence is retained.
REST and worker tools use the same public WorkerRun serializer.
`core.token_usage.TokenUsageLedger` records usage by call ID, distinguishing known,
estimated and unknown counts. SubAgentBudget is only a compatibility wrapper for
an explicitly configured cumulative task limit (`0` means recording only). Runner,
LLMAgent/SDK task contexts, AgentGraph logging and TokenUsageObserver reuse this
accounting implementation; a task context and its model transports share one ledger.
Runner does not add context-owned usage again. Session observers have their own
aggregation scope, never execution authority. Graph logs provider usage, not text
fragment counts. Legacy events without call IDs receive a local ID; only identified
repeated events can be deduplicated.

Bundled `backend/agents` definitions no longer set token budgets. User-defined
positive `token-budget` values remain supported, and an explicit `token_budget=0`
Runner override disables the definition's limit. These compatibility limits are
checked after responses, not prepaid hard cost ceilings. Context window/compaction
budgets and request `max_tokens` are separate capacity constraints.

TaskModelTransport records into the supplied context and takes no
prices, cumulative limits, trial or batch arguments. Optional ModelCallPolicy
hooks allow the benchmark-owned BenchmarkModelPolicy to reserve/settle against
`benchmarks.spend_ledger.SpendLedger`; the experiment owns trial/batch/journal
lifecycle and transport close does not close a batch. Core never imports benchmark
implementations. Default accounting does not latch a token stop on unknown usage;
the failed request still fails protocol validation and its usage remains unknown.
The strict benchmark policy retains unknown reservations and refuses further sends.
Runner binds ordinary task LLMs (including locator/classifier clients), legacy N2
and N2 SDK to this transport. TaskOpenAI retains SDK serialization without global
payload tracing or implicit retries. Text TaskModel.complete reuses
LLM.complete_response(retry=False); approved compatibility routes also accept
inline images, tool messages and SSE. Streaming checks stop state between delivered
SSE lines, preventing buffered SDK frames from bypassing cancellation. Partial
responses without validated usage remain unknown; close and settlement occur once.
Host profile references resolve credentials before plugin execution. API version 1
is checked before factory/resource creation. Existing n2_sdk api_key configuration
is accepted by the host for compatibility but removed from factory configuration.
Task clients close with the runtime; a bound ordinary LLM borrows its host pool.
BenchmarkTaskPolicy supplies request limits, spend admission and raw HTTP capture,
using the same call_id; no production module imports benchmarks. Model records
currently aggregate per task/call, without provider/model dimensions.

Observer events support API timing and screenshot traces without participating
in execution.

Runner-managed computer_use, old n2 and n2_sdk tasks share one desktop lock.
Lock wait counts against the task deadline; authorization precedes locking and
initialization. This covers one event loop, not direct main-session tools or
other processes. An operator must verify cleanup before explicitly clearing a
quarantine using DESKTOP_RESOURCE.clear_quarantine().

The [N2 SDK plugin](../../backend/plugins/agent-n2-sdk/README.md) uses the official
pinned N2ComputerAgent and MacOSComputer. The existing n2/engine path is retained.
Current SDK platform scope is macOS; Linux X11 is unvalidated and Wayland
unsupported. The native adapter emulates held input while delivering atomic
gestures. Real input/process cleanup and business outcomes need macOS acceptance.
Session-bound SDK driver RPCs are not replayed after connection failure: reconnect
ends the old MCP lease and task session. The plugin preserves the original tool
failure, blocks further actions and allows only end_session cleanup on the existing
connection; uncertain cleanup still quarantines the desktop. Actual screen capture
readiness requires the driver's direct capture permission check.
Plugin pause/resume/persistent resume remain disabled. `needs_input` returns to
the parent as a terminal outcome; it does not start a fresh run on agent_reply.
The legacy chat-history resume path rejects extension agents because it cannot
restore plugin progress, the original grant or cumulative budgets. Built-in
LLM agents retain the existing ask_user/waiting behavior.
