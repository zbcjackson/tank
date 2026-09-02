# Agentic Harness Features

Technical reference for the agentic harness infrastructure added to Tank's tool system.

---

## Tool Metadata & Conditional Registration

### ToolMetadata

Every tool declares its behavioral profile via `get_metadata()`:

```python
from tank_backend.tools.base import BaseTool, ToolMetadata

class MyTool(BaseTool):
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            category="command",       # "command" | "file" | "web" | "general"
            idempotent=False,         # True for read-only tools
            requires_network=True,    # Hint for conditional availability
            requires_filesystem=False,
        )
```

**Category** drives approval routing — `ToolApprovalPolicy` evaluates command tools through `CommandSecurityPolicy`, file tools through `FileAccessPolicy`, web tools through `NetworkAccessPolicy`. Tools declaring `"general"` auto-allow.

**Idempotency** is used by the guardrail controller for no-progress detection (identical results from the same idempotent tool trigger warnings).

### Conditional Registration

Tools can opt out of registration at startup:

```python
class MyTool(BaseTool):
    def is_available(self) -> bool:
        return os.environ.get("MY_API_KEY") is not None
```

`ToolManager.register_tool()` checks `is_available()` and skips tools that return False.

---

## Tool Loop Guardrails

Detects three failure patterns and injects guidance into the LLM context:

| Pattern | Warn after | Block after | Description |
|---------|-----------|-------------|-------------|
| Exact repeat failure | 2 | 4 | Same tool + same args hash fails repeatedly |
| Same-tool failure | 3 | 6 | Same tool (any args) fails repeatedly |
| No-progress loop | 3 | 5 | Idempotent tool returns identical results |

### Configuration

```yaml
# config.yaml
tool_guardrails:
  enabled: true
  exact_repeat_warn_after: 2
  exact_repeat_block_after: 4
  same_tool_fail_warn_after: 3
  same_tool_fail_block_after: 6
  no_progress_warn_after: 3
  no_progress_block_after: 5
```

Set `enabled: false` to disable entirely.

### Behavior

- **Warn**: Appends `[GUARDRAIL] ...` message to the tool result, suggesting the LLM try a different approach.
- **Block**: Adds the tool to `rejected_tools` (removed from the schema for the rest of the turn) and appends the guardrail message.

Implementation: `backend/core/src/tank_backend/agents/guardrails.py`

---

## Durable Command Approvals

When a user approves an unknown command via the interactive confirm flow, the base command is persisted to SQLite so it auto-allows on subsequent sessions.

### How It Works

1. Command arrives (e.g., `terraform plan`)
2. `CommandSecurityPolicy._evaluate_segment()` checks:
   - Dangerous patterns → DENY
   - Always-require list → REQUIRE_APPROVAL
   - Git subcommand check → varies
   - Safe allowlist → ALLOW
   - **Durable approvals** → ALLOW (if previously approved)
   - Unknown → REQUIRE_APPROVAL
3. User approves via confirm_action
4. `CommandApprovalStore.grant("terraform")` persists it
5. Next session: `terraform apply` auto-allows (base command matches)

### Storage

- Table: `command_approvals` (command_pattern, session_id, created_at)
- Store: `backend/core/src/tank_backend/policy/command_approvals.py`
- Migration: `20260608_100000_add_command_approvals.py`

---

## Safe-Bin Argument Validation

Commands in the safe allowlist can escape safety with certain arguments. Per-command regex patterns detect dangerous argument combinations:

| Command | Blocked patterns |
|---------|-----------------|
| python/python3 | `-c` with `import os/subprocess/shutil`, `exec()`, `eval()`, `__import__` |
| python/python3 | `-m http.server` (exposes filesystem) |
| node | `-e`/`--eval` with `require('child_process'\|'fs'\|'net')` |
| ruby/perl | `-e` with `system()`, `unlink`, `exec`, backticks |
| curl | `-o`/`--output` (can overwrite files) |
| wget | `-O`/`--output-document` (except `/dev/null`) |
| pip/pip3 | `install` (arbitrary setup.py execution) |
| npm | `install`, `exec` (lifecycle scripts, arbitrary packages) |
| cargo | `install` (compiles arbitrary code) |

Safe simple usage remains auto-allowed: `python script.py`, `npm list`, `curl https://...`, etc.

Implementation: `_check_safe_command_args()` in `backend/core/src/tank_backend/policy/command_security.py`

---

## Composable Toolset Profiles

Named tool subsets that agents and jobs reference by name instead of ad-hoc disallowed-lists.

### Configuration

```yaml
# config.yaml
toolsets:
  profiles:
    safe:
      description: "Read-only tools"
      tools: [file_read, file_list, file_search, web_search, calculate, get_time]
    research:
      description: "Web and file research"
      tools: [file_read, file_list, file_search, web_search, web_fetch, calculate]
    full:
      description: "All tools (default)"
      tools: []  # empty = no filtering
```

### Usage in Agent Definitions

```yaml
---
name: researcher
description: Research-only agent
toolset: research
---
You are a research agent. Only use research tools.
```

When `toolset` is specified, `AgentRunner._resolve_toolset()` converts the profile to a `tool_filter` allowlist passed to `LLMAgent`.

---

## Shell Hook System

User-defined shell scripts that fire on tool lifecycle events.

### Configuration

```yaml
# config.yaml
hooks:
  hooks:
    - event: pre_tool_call
      command: ~/.tank/hooks/audit.sh
      matcher: "run_command|persistent_shell"
      timeout: 3.0
    - event: post_tool_call
      command: ~/.tank/hooks/log-tools.sh
    - event: pre_llm_call
      command: ~/.tank/hooks/inject-context.sh
```

### Events

| Event | Timing | Can block? | Use case |
|-------|--------|-----------|----------|
| `pre_tool_call` | Before tool execution | Yes | Security audit, policy enforcement |
| `post_tool_call` | After tool execution | No (fire-and-forget) | Logging, monitoring |
| `pre_llm_call` | Before each LLM iteration | No (injects context) | Dynamic instructions, time awareness |

### Wire Protocol

**stdin** (JSON):
```json
{
  "hook_event_name": "pre_tool_call",
  "tool_name": "run_command",
  "tool_input": {"command": "rm -rf /tmp/cache"},
  "session_id": "conv_abc123",
  "cwd": "/home/user/project"
}
```

**stdout** (JSON, optional):
```json
{"action": "block", "reason": "Destructive command blocked by policy"}
```

For `pre_llm_call`:
```json
{"context": "Today is Monday. The user prefers concise answers."}
```

### Consent / Allowlist

Hooks must be approved before they run. Approvals are persisted to `~/.tank/hook-allowlist.json`.

```python
from tank_backend.hooks import HookAllowlist, HookIdentity

allowlist = HookAllowlist(path="~/.tank/hook-allowlist.json")
hook = HookIdentity(event="pre_tool_call", command="~/.tank/hooks/audit.sh")

allowlist.grant(hook)      # Approve
allowlist.is_allowed(hook) # True
allowlist.revoke(hook)     # Remove approval
```

Set `auto_accept=True` for headless/trusted environments that skip consent.

When no allowlist is configured (`allowlist=None` in HookManager), all hooks pass through (backward compatibility).

Implementation: `backend/core/src/tank_backend/hooks/`

---

## Session Lifecycle Events

Bus messages posted at session boundaries for observers and external integrations:

| Event | When | Payload |
|-------|------|---------|
| `session_start` | `Brain.new_conversation()` | `{event, session_id}` |
| `session_end` | `Brain.close()` | `{event, session_id}` |
| `turn_start` | Start of NORMAL mode processing | `{event, user, session_id}` |
| `turn_end` | After successful turn completion | `{event, user, session_id, latency_s}` |

All posted as `BusMessage(type="lifecycle", ...)`. Subscribe via:
```python
bus.subscribe("lifecycle", my_handler)
```

---

## Token Usage Observer

Bus observer that tracks per-turn and cumulative token consumption.

### Setup

```python
from tank_backend.pipeline.observers import TokenUsageObserver

observer = TokenUsageObserver(bus, budget_tokens=500_000)
```

### Events Published

| Bus type | When | Payload |
|----------|------|---------|
| `token_usage` | After each LLM iteration | Per-turn + cumulative counts |
| `token_budget_exceeded` | First time cumulative exceeds budget | `{budget, used, turn}` |

### API

```python
observer.total_tokens        # Cumulative tokens used
observer.turn_count          # Number of LLM iterations
observer.summary()           # Full stats dict
observer.reset()             # Clear counters (new conversation)
```

Implementation: `backend/core/src/tank_backend/pipeline/observers/token_usage.py`
