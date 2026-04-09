# Agent Orchestration

This document describes Tank's agent orchestration system — how the LLM handles conversations, delegates work to specialist workers, verifies results, and manages tool approval.

## Architecture Overview

Tank uses an **orchestrator-workers** pattern inspired by Anthropic's "Building Effective Agents" guidance and OpenAI's `agent.as_tool()` pattern.

```
User message
  → AgentGraph
    → Orchestrator (ChatAgent with all delegate_to_* tools)
      ├─ Handles simple tasks directly (weather, time, chat)
      ├─ Delegates complex tasks to workers via delegate_to_* tool calls
      ├─ Multiple delegate_to_* calls in one turn run concurrently
      └─ Synthesizes worker results into a response
        → Streamed to TTS
```

Key files:

| File | Purpose |
|------|---------|
| `agents/base.py` | `Agent` ABC, `AgentState`, `AgentOutput`, `AgentOutputType` |
| `agents/chat_agent.py` | `ChatAgent` — conversational agent with tool calling and approval gating |
| `agents/graph.py` | `AgentGraph` — orchestrator loop, streams outputs, tracks stats |
| `agents/worker_tool.py` | `WorkerTool` — wraps a `ChatAgent` as a callable tool |
| `agents/factory.py` | `create_agent()` — builds orchestrator + workers from config |
| `agents/approval.py` | `ApprovalManager`, `ToolApprovalPolicy` |
| `llm/llm.py` | `LLM.chat_stream()` — parallel tool execution for concurrent-safe tools |

## How It Works

### Single Agent (No Workers)

Without a `workers:` section in config, Tank runs a single `ChatAgent` with access to all registered tools. No routing, no delegation overhead. This is the simplest mode.

### Orchestrator + Workers

When `workers:` is defined under an agent in `config.yaml`, the factory:

1. Creates a `ChatAgent` for each worker with a restricted `tool_filter`
2. Wraps each worker in a `WorkerTool` (registered as `delegate_to_{name}`)
3. Excludes worker-owned tools from the orchestrator via `exclude_tools`
4. Injects delegation instructions into the orchestrator's system prompt

The orchestrator sees workers as regular tools. The LLM decides when to delegate — no separate router.

### Parallel Fan-Out

When the LLM calls multiple `delegate_to_*` tools in a single turn, they execute concurrently via `asyncio.gather`. This is handled in `llm.py`:

- `_CONCURRENT_PREFIXES = ("delegate_to_", "review_")` defines which tools are safe to parallelize
- `_is_concurrent_safe(name)` checks the prefix
- All concurrent tool calls in the same turn are gathered and awaited together

The orchestrator prompt explicitly instructs: *"call multiple delegate_to_* tools in the SAME response — do NOT call them one at a time."*

### Verifier (Auto-Created)

When a `coder` worker exists and no `verifier` is explicitly configured, the factory auto-creates one:

- Read-only tools: `run_command`, `file_read`, `file_list`
- System prompt enforces: "STRICTLY READ-ONLY. Do NOT modify, create, or delete any files."
- Must end response with `VERDICT: PASS` or `VERDICT: FAIL`
- Orchestrator prompt instructs: "After delegate_to_coder completes, ALWAYS call delegate_to_verifier"

The orchestrator's natural tool loop handles retries — if the verifier fails, the orchestrator can re-delegate to the coder with feedback. No hardcoded review loop needed.

To disable auto-verification when a coder worker exists, explicitly define a custom verifier or remove the coder worker.

## Approval System

### Two-Tier Approval

| Tool category | Mechanism | Granularity |
|---------------|-----------|-------------|
| Sandbox tools (`run_command`, `persistent_shell`) | `ToolApprovalPolicy` in `ChatAgent` | Per-tool-name |
| File tools (`file_read`, `file_write`, etc.) | `ApprovalCallback` inside `execute()` | Per-path + per-operation |

### Approval Flow

1. `ChatAgent` intercepts `TOOL_EXECUTING` output
2. Checks `ToolApprovalPolicy.needs_approval(tool_name)`
3. If approval needed: creates `ApprovalRequest`, yields `APPROVAL_NEEDED`
4. `ApprovalManager` holds a Future — client notified via WebSocket
5. User approves/rejects via REST API (`POST /api/approvals/{id}/respond`) or voice
6. Agent resumes with tool result or rejection notice

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
    - web_scraper
```

`require_approval_first_time` asks once per session, then auto-approves subsequent calls to the same tool.

## Configuration

### Basic (Single Agent)

```yaml
agents:
  chat:
    type: chat
    llm_profile: default
```

### With Workers

```yaml
agents:
  chat:
    type: chat
    llm_profile: default
    workers:
      coder:
        description: "Execute code and modify files"
        tools: [run_command, persistent_shell, file_write, file_delete]
        system_prompt: |
          You are a code execution specialist...
        timeout: 120
      researcher:
        description: "Search the web and gather information"
        tools: [web_search, web_scraper]
        timeout: 60
```

### AgentGraph Limits

- Max iterations per turn: **5** (configurable in `AgentGraph`)
- Worker timeout: **120s** default (per-worker, set in config)
- Approval timeout: **120s** (in `ApprovalManager`)
- LLM bounded tool iterations: **10** (in `llm.py`, `MAX_TOOL_ITERATIONS`)

## Gotchas

1. **Worker tools are hidden from the orchestrator.** Tools assigned to workers are excluded from the orchestrator's tool list via `exclude_tools`. The orchestrator can only call `delegate_to_*` tools, not worker-owned tools directly.

2. **Concurrent execution requires matching prefixes.** Only tools starting with `delegate_to_` or `review_` run concurrently. All other tools execute sequentially. Adding a new concurrent-safe prefix requires updating `_CONCURRENT_PREFIXES` in `llm.py`.

3. **Verifier must end with a VERDICT line.** If the verifier's response doesn't end with `VERDICT: PASS` or `VERDICT: FAIL`, the orchestrator won't recognize the verification result. This is enforced by the verifier's system prompt, not by code.

4. **Worker timeout is independent of LLM iteration limit.** A worker can time out at 120s even if the LLM hasn't hit its 10-iteration limit. These are separate safety bounds.

5. **Approval timeout is silent.** If the user doesn't respond within 120s, the approval request times out and the tool call fails. There's no retry — the orchestrator sees a timeout error and must decide what to do.

6. **Orchestrator prompt is auto-injected.** When workers exist, `factory.py` appends delegation instructions to the orchestrator's system prompt. This includes worker descriptions and usage guidance. Custom system prompts should not duplicate this.

## Streaming Behavior

Every `AgentOutput` is yielded immediately as an async generator — no batching:

| Output Type | What Happens |
|-------------|-------------|
| `TOKEN` | Streamed to TTS immediately |
| `THOUGHT` | Sent to client as thinking indicator |
| `TOOL_CALLING` | Sent to client as tool call notification |
| `TOOL_EXECUTING` | Intercepted for approval check |
| `TOOL_RESULT` | Fed back into LLM for next iteration |
| `APPROVAL_NEEDED` | Pauses agent, awaits user response |
| `DONE` | Ends the turn |

This is the critical difference from LangGraph: tokens stream to TTS the moment they're produced, not in batches.
