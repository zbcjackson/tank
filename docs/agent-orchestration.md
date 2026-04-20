# Agent Orchestration

This document describes Tank's agent orchestration system — how the main agent handles conversations, delegates work to sub-agents, and manages tool approval.

## Architecture Overview

Tank uses a single main agent with access to ALL tools. For complex tasks, the main agent spawns sub-agents via the `agent` tool. Sub-agents are defined as markdown files and run through the same `AgentRunner.run_agent()` execution path.

```
User message
  → BrainProcessor
    → AgentGraph
      → Main LLMAgent (all tools including `agent`)
        ├─ Handles simple tasks directly (weather, time, chat, file ops, shell)
        ├─ Spawns sub-agents via `agent` tool for complex/isolated tasks
        │    → AgentRunner.run_agent()
        │      → LLMAgent with filtered tools + own system prompt
        │      → Approval inherited from parent
        │      → Outputs streamed via Bus
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
| `agents/approval.py` | `ApprovalManager`, `ToolApprovalPolicy` |
| `llm/llm.py` | `LLM.chat_stream()` — streaming with tool execution loop |

## How It Works

### Main Agent

The main agent has access to every registered tool — file operations, shell commands, web search, skills, and the `agent` tool. The system prompt guides when to delegate vs handle directly:

- Simple tasks (weather, time, calculations, quick file reads): handle directly
- Complex tasks (multi-step coding, research, planning): spawn a sub-agent
- Parallel tasks: call `agent` multiple times in one response

### Sub-Agents via `agent` Tool

When the LLM calls `agent(prompt="...", subagent_type="coder")`:

1. `AgentTool.execute()` looks up the agent definition
2. Calls `AgentRunner.run_agent()` which:
   - Checks depth limit (max 3 levels deep)
   - Checks concurrent agent limit (max 5)
   - Creates an `LLMAgent` with the definition's system prompt
   - Filters tools: all tools minus `disallowed_tools` minus global disallowed set
   - Passes `approval_manager` and `approval_policy` (inherited from parent)
   - Streams all `AgentOutput` items back
3. The result text is returned to the main agent as the tool result

### Agent Definitions

Agents are defined as markdown files with YAML frontmatter in `.tank/agents/`:

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

This means sub-agents can't spawn further sub-agents by default (the `agent` tool is globally disallowed for sub-agents).

### Parallel Execution

When the LLM calls multiple `agent` tools in a single turn, they can run concurrently. The `agent` tool supports `run_in_background=true` for parallel execution. The concurrency mechanism in `LLM.chat_stream()` detects concurrent-safe tool calls and runs them via `asyncio.gather`.

### Langfuse Tracing

Each `LLMAgent` passes trace metadata to `LLM.chat_stream()`:
- `name`: `agent:{agent_name}` (e.g., `agent:chat`, `agent:agent_coder`)
- `metadata`: `{"agent_name": name}`

This appears in Langfuse as separate traces per agent, filterable by name.

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
```

### Limits

| Limit | Default | Where |
|-------|---------|-------|
| Max agent depth | 3 | `AgentRunner` |
| Max concurrent agents | 5 | `AgentRunner` |
| Max turns per agent | 25 | `AgentDefinition.max_turns` |
| AgentGraph iterations | 5 | `AgentGraph` |
| LLM tool iterations | 10 | `LLM.chat_stream()` |
| Approval timeout | 120s | `ApprovalManager` |

## Gotchas

1. **Main agent has ALL tools.** Unlike the old orchestrator/worker pattern, the main agent can call `run_command`, `file_write`, etc. directly. The system prompt guides when to delegate vs handle directly — this is an LLM judgment call, not a code constraint.

2. **Sub-agents can't spawn sub-agents by default.** The `agent` tool is in the global disallowed set for sub-agents. This prevents infinite recursion. To allow it, remove `agent` from a specific agent definition's `disallowed_tools` — but be careful with depth limits.

3. **Agent definitions are loaded at startup.** Changes to `.tank/agents/*.md` files require a server restart (or hot-reload via watchfiles). The definitions are not re-scanned per request.

4. **Concurrent execution requires the `agent` tool to be concurrent-safe.** Currently, `agent` tool calls run sequentially unless `run_in_background=true` is set. The `_CONCURRENT_PREFIXES` in `llm.py` controls which tools run in parallel.

5. **Approval timeout is silent.** If the user doesn't respond within 120s, the approval request times out and the tool call fails. The agent sees a timeout error.

6. **Langfuse tracing uses `name` and `metadata` kwargs only.** The Langfuse v4 SDK's `OpenAiArgsExtractor` only extracts `name`, `metadata`, `trace_id`, `parent_observation_id` from kwargs. Other keys (`tags`, `session_id`) leak through to the OpenAI API and cause errors.
