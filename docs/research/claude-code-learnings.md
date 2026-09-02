# Learnings from Claude Code for Tank

> Source: Analysis of Claude Code architecture document and source code (~1,900 files, 512,000+ LOC).
> Purpose: Actionable patterns to borrow into Tank's voice assistant architecture.
> Date: 2026-04-05

---

## Table of Contents

1. [Resilience & Error Recovery](#1-resilience--error-recovery)
2. [Context Management & Compaction](#2-context-management--compaction)
3. [Tool System Improvements](#3-tool-system-improvements)
4. [Performance Optimizations](#4-performance-optimizations)
5. [UX & Interaction Patterns](#5-ux--interaction-patterns)
6. [Extensibility](#6-extensibility)
7. [Safety & Permissions](#7-safety--permissions)
8. [Multi-Agent Orchestration](#8-multi-agent-orchestration)
9. [Implementation Priority](#9-implementation-priority)

---

## 1. Resilience & Error Recovery

### 1.1 Error Classification + Differentiated Retry

Claude Code classifies every API error and applies a different strategy per class. Tank's `LLM` client currently retries all errors uniformly with `MAX_RETRY_ATTEMPTS = 3`.

| Error | HTTP Code | Strategy | Rationale |
|-------|-----------|----------|-----------|
| `prompt_too_long` | 413 | Compact context, then retry | Context exceeded, recoverable |
| `max_output_tokens` | — | Retry up to 3× with adjusted budget | Model rambled, recoverable |
| `rate_limit` | 429 | Fail immediately, no retry | Retrying makes congestion worse |
| `overloaded` | 529 | Retry 3× for foreground only | Background retries cause cascade amplification |
| `transient` | 5xx / network | Exponential backoff + jitter, up to 10× | Transient, recoverable |

**Implementation sketch for `llm/llm.py`:**

```python
from enum import Enum

class LLMErrorType(Enum):
    PROMPT_TOO_LONG = "prompt_too_long"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    TRANSIENT = "transient"

def classify_error(e: Exception) -> LLMErrorType:
    status = getattr(e, "status_code", None)
    if status == 429:
        return LLMErrorType.RATE_LIMIT
    if status == 529:
        return LLMErrorType.OVERLOADED
    if status == 413:
        return LLMErrorType.PROMPT_TOO_LONG
    if status and status >= 500:
        return LLMErrorType.TRANSIENT
    # Check for max_output_tokens in error body
    if "max_output_tokens" in str(e):
        return LLMErrorType.MAX_OUTPUT_TOKENS
    return LLMErrorType.TRANSIENT
```

Key rule: **429 should never be retried** (you're rate-limited, retrying makes it worse). **529 should be retried only for foreground queries** (retrying background work during overload creates cascade amplification).

### 1.2 Explicit Continuation Reasons in the Agentic Loop

Claude Code's `query.ts` loop carries a `State` object with a `transition: Continue` field that explains *why* the loop is continuing. Each recovery path is a named, testable code path.

**Continuation sites:**

| Site | Trigger | Action |
|------|---------|--------|
| `TOOL_RESULT` | Tools executed | Normal continuation |
| `COMPACT` | Context too long | Auto-compact history, retry |
| `REACTIVE_COMPACT` | `max_output_tokens` mid-turn | Compact then resume same turn |
| `RECOVER` | Model hit output limit | Retry up to 3× with adjusted `max_tokens` |
| `BUDGET_EXCEEDED` | Token/cost budget exhausted | Stop loop, surface reason |

**For Tank's `AgentGraph` / `BrainProcessor`:**

```python
from enum import Enum

class ContinueReason(Enum):
    TOOL_RESULT = "tool_result"
    COMPACT = "compact"
    REACTIVE_COMPACT = "reactive_compact"
    RECOVER_MAX_TOKENS = "recover_max_tokens"
    BUDGET_EXCEEDED = "budget_exceeded"

@dataclass
class LoopState:
    messages: list[dict]
    max_output_tokens_recovery_count: int = 0  # max 3
    has_attempted_reactive_compact: bool = False
    turn_count: int = 0
    transition: ContinueReason | None = None
```

### 1.3 Auto-Compact Circuit Breaker

Claude Code tracks `consecutiveAutocompactFailures` and stops trying after 3 failures. Prevents infinite compaction loops when the summarization model itself is failing.

```python
MAX_COMPACT_FAILURES = 3

async def _maybe_compact(self, messages: list[dict]) -> list[dict]:
    if self._compact_failures >= MAX_COMPACT_FAILURES:
        # Fall back to snip (drop oldest messages)
        return messages[len(messages) // 2:]
    try:
        result = await self._summarize(messages)
        self._compact_failures = 0  # reset on success
        return result
    except Exception:
        self._compact_failures += 1
        return messages  # skip compaction this turn
```

---

## 2. Context Management & Compaction

### 2.1 Layered Compaction Pipeline

Claude Code runs compaction in a specific order, where each layer can prevent the next from firing. Tank currently has one strategy (LLM-based summarization). Adding cheaper layers first saves tokens and latency.

```
1. Snip         → drop oldest messages entirely (cheapest, no LLM call)
2. Microcompact → clear old tool results by ID (no LLM call)
3. Autocompact  → LLM-based summarization (most expensive)
```

### 2.2 Microcompact — Clear Old Tool Results

The single highest-value compaction strategy Tank is missing. After 2-3 turns, replace old tool results with a placeholder. No LLM call required.

**Compactable tools in Tank:** `web_search`, `web_fetch`, `run_command`, `persistent_shell`
**Non-compactable:** `calculate`, `get_time`, `get_weather` (results are small)

```python
COMPACTABLE_TOOLS = {"web_search", "web_fetch", "run_command", "persistent_shell"}
KEEP_RECENT_RESULTS = 2  # keep last N tool results

def microcompact(messages: list[dict], keep_recent: int = KEEP_RECENT_RESULTS) -> list[dict]:
    """Replace old tool results with placeholders to free context."""
    tool_results = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool" and msg.get("name") in COMPACTABLE_TOOLS:
            tool_results.append(i)

    # Keep the most recent N, clear the rest
    to_clear = tool_results[:-keep_recent] if len(tool_results) > keep_recent else []

    for idx in to_clear:
        original_len = len(messages[idx]["content"])
        messages[idx]["content"] = (
            f"[Tool result cleared: {messages[idx]['name']} "
            f"returned {original_len:,} chars — content no longer in context]"
        )
    return messages
```

### 2.3 Snip Compaction — Emergency Drop

When history exceeds 2× the token budget, drop the oldest messages entirely. This is the emergency valve — no LLM call, no summarization, just truncation.

```python
def snip_compact(messages: list[dict], max_messages: int) -> list[dict]:
    """Drop oldest messages, preserving system message and tool_use/tool_result pairs."""
    if len(messages) <= max_messages:
        return messages

    # Always keep system message (index 0) and last max_messages
    system = [messages[0]] if messages[0].get("role") == "system" else []
    recent = messages[-max_messages:]

    # Ensure we don't split tool_use/tool_result pairs
    if recent and recent[0].get("role") == "tool":
        # Find the matching tool_use and include it
        for i in range(len(messages) - max_messages - 1, -1, -1):
            if messages[i].get("tool_calls"):
                recent = messages[i:-(len(messages) - max_messages)] + recent
                break

    return system + recent
```

### 2.4 Reactive Compaction — Resume Mid-Turn

When the LLM hits `max_output_tokens` mid-turn, compact immediately and *resume the same turn*. Tank currently loses the partial response.

**Flow:**
1. LLM returns partial response with `finish_reason: "length"`
2. Save partial response tokens
3. Run microcompact + autocompact on history
4. Retry the same turn with compacted context
5. Guard: `has_attempted_reactive_compact` prevents infinite loops

### 2.5 Oversized Result Spill / Truncation

When a tool result exceeds a threshold, truncate it to prevent context pollution. Claude Code spills to disk; for Tank, truncation with a note is simpler.

```python
MAX_TOOL_RESULT_CHARS = 8000

def truncate_result(result: str, tool_name: str) -> str:
    if len(result) <= MAX_TOOL_RESULT_CHARS:
        return result
    return (
        result[:MAX_TOOL_RESULT_CHARS]
        + f"\n\n[Result truncated — {tool_name} returned {len(result):,} chars total. "
        f"Only first {MAX_TOOL_RESULT_CHARS:,} shown.]"
    )
```

---

## 3. Tool System Improvements

### 3.1 Tool Result Pairing Guarantee

After every turn, verify that every `tool_use` has a matching `tool_result`. Missing pairs are synthesized as error messages. Prevents protocol violations that confuse the LLM on the next turn.

```python
def ensure_tool_result_pairing(messages: list[dict]) -> list[dict]:
    """Guarantee every tool_use has a matching tool_result."""
    pending: dict[str, dict] = {}
    for msg in messages:
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                pending[tc["id"]] = tc
        if msg.get("role") == "tool":
            pending.pop(msg.get("tool_call_id", ""), None)

    # Synthesize missing results
    for tc_id, tc in pending.items():
        messages.append({
            "role": "tool",
            "tool_call_id": tc_id,
            "content": (
                f"Error: tool execution failed or timed out "
                f"for {tc['function']['name']}"
            ),
        })
    return messages
```

### 3.2 Concurrent Tool Execution

Claude Code classifies tools as `isConcurrencySafe` and runs safe tools in parallel (up to 10). Tank's agents currently run tools sequentially.

**Safe tools (concurrent):** `calculate`, `get_time`, `get_weather`, `web_search`
**Unsafe tools (serial):** `run_command`, `persistent_shell`, `manage_process`

```python
import asyncio

async def execute_tool_calls(tool_calls: list, tool_manager) -> list:
    safe = [tc for tc in tool_calls if is_concurrency_safe(tc["function"]["name"])]
    unsafe = [tc for tc in tool_calls if not is_concurrency_safe(tc["function"]["name"])]

    # Run safe tools in parallel
    results = list(await asyncio.gather(
        *[tool_manager.execute(tc) for tc in safe],
        return_exceptions=True,
    ))

    # Run unsafe tools sequentially
    for tc in unsafe:
        results.append(await tool_manager.execute(tc))

    return results

CONCURRENT_SAFE_TOOLS = {"calculate", "get_time", "get_weather", "web_search", "web_fetch"}

def is_concurrency_safe(tool_name: str) -> bool:
    return tool_name in CONCURRENT_SAFE_TOOLS
```

### 3.3 Deferred Tool Loading

When the tool set grows large, mark some tools as deferred — their schemas aren't sent to the LLM until the model explicitly searches for them. Auto-enable when deferred tool descriptions exceed 10% of context window.

**Not urgent with Tank's current 7 tools.** Plan for when the tool set grows past ~15.

**Pattern:**
- Always load: `calculate`, `get_time`, `get_weather` (small, frequently used)
- Defer: `web_search`, `web_fetch`, `run_command`, `persistent_shell` (large schemas)
- Add a `find_tool` meta-tool that returns matching schemas on demand

---

## 4. Performance Optimizations

### 4.1 Context Injection — Auto-Inject Background Context

Claude Code automatically injects git status, platform info, and memory files into every conversation. Tank can inject session context to save tool calls.

**Inject into system prompt:**
- Current time and timezone (saves a `get_time` tool call)
- User's preferred language (detected from first utterance)
- Speaker identity (from `SpeakerIDProcessor`)
- Session duration and turn count
- Summary of last 3 tool results

### 4.2 Memory / Context Prefetch

Claude Code prefetches memory files asynchronously *while the user is still typing*. By the time the user hits Enter, context is already loaded.

**For Tank:**
- Pre-warm conversation history from checkpointer during WebSocket handshake
- Prefetch speaker enrollment data during session setup
- Cache system prompt across turns (invalidate only when config changes)

### 4.3 Dependency Injection for Testability

Claude Code's `query.ts` accepts a `deps` parameter for all external dependencies. Production uses real implementations; tests inject mocks.

```python
from dataclasses import dataclass
from typing import Callable, AsyncIterator, Any

@dataclass
class BrainDeps:
    call_model: Callable[..., AsyncIterator[Any]]  # LLM streaming call
    compact: Callable[..., Any]                     # context compaction
    count_tokens: Callable[[list[dict]], int]        # token estimation
    microcompact: Callable[[list[dict]], list[dict]] # tool result clearing

def production_deps() -> BrainDeps:
    return BrainDeps(
        call_model=llm.stream_completion,
        compact=summarize_history,
        count_tokens=tiktoken_count,
        microcompact=microcompact_messages,
    )
```

---

## 5. UX & Interaction Patterns

### 5.1 Effort Levels

Claude Code lets users set `low / medium / high / max` effort, controlling thinking budget and response quality. Maps directly to voice assistant latency expectations.

| Level | Thinking Budget | Latency | Use Case |
|-------|----------------|---------|----------|
| `low` | None | <2s | Factual queries, time, weather |
| `medium` | 5,000 tokens | 5-10s | General conversation (voice default) |
| `high` | 15,000 tokens | 15-30s | Complex questions, multi-step tasks |

**Voice-specific UX:**
- Default to `medium` for voice (users expect ~5-10s response time)
- Auto-detect from intent: `task` agent → `low`, `chat` agent → `medium`, `code` agent → `high`
- Voice trigger: "think carefully about this" → bump effort for that turn
- Effort-aware status signal: `"thinking_deeply"` via WebSocket update message

**Implementation:** Add `effort` field to `AgentState`, pass to LLM call as thinking budget.

### 5.2 Per-Session Cost Tracking

Claude Code tracks per-session costs with cache differentiation and displays via `/cost` command.

```python
from dataclasses import dataclass, field

@dataclass
class SessionCost:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    api_duration_ms: int = 0
    tool_duration_ms: int = 0
    model_usage: dict[str, dict] = field(default_factory=dict)

    def accumulate(self, usage: dict, model: str, cost_per_million: dict):
        input_cost = (usage["prompt_tokens"] / 1_000_000) * cost_per_million["input"]
        output_cost = (usage["completion_tokens"] / 1_000_000) * cost_per_million["output"]
        self.input_tokens += usage["prompt_tokens"]
        self.output_tokens += usage["completion_tokens"]
        self.cost_usd += input_cost + output_cost
```

**Surface to user via WebSocket:**
- After each turn: `{"type": "update", "metadata": {"update_type": "COST", "cost_usd": 0.012}}`
- Session budget warning when approaching limit
- Persist cost state in checkpointer for resume

### 5.3 Effort-Aware Status Signals

Tank already sends `processing_started` / `processing_ended` signals. Add effort-aware variants:

```json
{"type": "signal", "content": "thinking_started", "metadata": {"effort": "high"}}
{"type": "signal", "content": "thinking_ended", "metadata": {"duration_ms": 8500}}
```

The client can show different UI states: quick spinner for `low`, animated thinking indicator for `high`.

### 5.4 Extended Thinking with Keyword Triggers

Claude Code detects keywords like "ultrathink" to enable deep thinking for a single turn.

**For Tank:** Detect phrases in ASR transcript:
- "think carefully" / "仔细想想" → enable thinking for this turn
- "quick answer" / "快速回答" → disable thinking for this turn
- Keyword detection happens in `BrainProcessor` before LLM call

### 5.5 Session Resume with Full State Restoration

Claude Code restores multiple facets on resume: messages, file snapshots, cost state, todo lists.

**Extend Tank's checkpointer to save:**
- Conversation messages (already done)
- Cumulative cost state
- Speaker enrollment state
- Last detected language
- Agent history (which agents were used)
- Pending approval requests

**On reconnect:** Send `signal: "resumed"` with summary:
```json
{
  "type": "signal",
  "content": "resumed",
  "metadata": {
    "turns": 12,
    "cost_usd": 0.23,
    "last_agent": "search",
    "elapsed_minutes": 5
  }
}
```

---

## 6. Extensibility

### 6.1 Skills / Prompt Templates

Claude Code's skills are reusable prompt templates stored as markdown files with frontmatter. For Tank, this maps to voice command templates.

```yaml
# backend/skills/summarize-article.yaml
name: summarize
trigger_keywords: [summarize, summary, tldr, 总结]
agent: search
tools: [web_fetch]
effort: medium
prompt: |
  Fetch the URL the user mentioned and provide a concise summary
  in 3-5 bullet points. Respond in the same language as the article.
```

**Benefits:**
- Adding new capabilities is a config change, not a code change
- Skills can restrict tools and override effort level
- Skills can specify which agent handles them

### 6.2 Pre/Post Tool Hooks

Claude Code has 26 hook events. The most relevant for Tank:

| Hook | When | What It Can Do |
|------|------|----------------|
| `PreToolUse` | Before tool execution | Validate args, block, modify |
| `PostToolUse` | After tool execution | Auto-format, lint, verify |
| `Stop` | Agent finishes turn | Run tests, quality check |
| `SessionStart` | Pipeline startup | Load config, warm caches |

**Config in `config.yaml`:**

```yaml
hooks:
  post_tool_use:
    - tool: run_command
      command: "ruff check {file}"
      on_failure: feed_to_agent  # restart agent with error
  pre_tool_use:
    - tool: web_fetch
      command: "check_url_allowlist.sh {url}"
      on_failure: block  # prevent tool execution
  stop:
    - agent: code
      command: "cd backend && uv run ruff check src/"
      on_failure: restart  # feed errors back to agent
```

**Execution model:** Spawn subprocess, pass JSON input via stdin, parse JSON output from stdout. Exit code 0 = success, 2 = feed stderr to agent.

### 6.3 Slash Commands / Voice Commands

Claude Code has a command registry with two types:
- `PromptCommand` — expands into a prompt (like skills)
- `LocalCommand` — executes locally (like `/cost`, `/status`)

**For Tank:** Add voice-invocable commands:
- "show cost" → display session cost summary
- "clear history" → compact/reset conversation
- "switch to search mode" → force search agent for next turn
- "approve" / "reject" → respond to pending approval

---

## 7. Safety & Permissions

### 7.1 Per-Pattern Approval Rules

Claude Code supports content-specific approval rules, not just per-tool:

```json
{
  "always_approve": ["run_command(ls)", "run_command(cat *)"],
  "require_approval": ["run_command(rm *)", "run_command(sudo *)"]
}
```

**For Tank:** Extend approval policies to support argument patterns:

```yaml
approval_policies:
  always_approve:
    - get_weather
    - get_time
    - calculate
    - "run_command:ls *"      # approve ls with any args
    - "run_command:cat *"     # approve cat with any args
  require_approval:
    - "run_command:rm *"      # always ask for rm
    - "run_command:sudo *"    # always ask for sudo
    - "persistent_shell:*"    # always ask for shell
```

### 7.2 Structured Abort Controller Hierarchy

Claude Code uses parent-child `AbortController` with `WeakRef` to prevent memory leaks.

```
Session AbortController (user closes app)
  ├── Turn AbortController (user interrupts mid-response)
  │   ├── LLM Call AbortController
  │   ├── Tool Execution AbortController
  │   └── TTS AbortController
  └── Audio Capture AbortController
```

**For Tank:** Wrap each turn's work in a cancellation scope. When VAD detects an interrupt, cancel the turn scope — all child operations stop cleanly. Use `asyncio.TaskGroup` or a custom cancellation token.

```python
import asyncio

class CancellationToken:
    def __init__(self, parent: "CancellationToken | None" = None):
        self._cancelled = False
        self._children: list[CancellationToken] = []
        if parent:
            parent._children.append(self)

    def cancel(self):
        self._cancelled = True
        for child in self._children:
            child.cancel()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def child(self) -> "CancellationToken":
        return CancellationToken(parent=self)
```

### 7.3 File State Cache with Stale Detection

Claude Code tracks file hashes in an LRU cache. Before editing, it checks whether the file on disk still matches what the model last read.

**For Tank:** Less directly applicable (Tank doesn't edit files often), but useful for:
- Checkpointer: detect if a session was modified by another process before overwriting
- Config: detect if `config.yaml` changed during a session and reload

---

## 8. Multi-Agent Orchestration

### 8.1 Sub-Agent Forking with Isolation

Claude Code's `AgentTool` spawns sub-agents in three modes:

| Mode | Context | Token Budget | Use Case |
|------|---------|-------------|----------|
| `inline` | Shared with parent | Shared | Quick lookups |
| `fork` | Cloned, isolated | Separate | Parallel research |
| `remote` | Separate machine | Separate | Heavy computation |

**For Tank's `AgentGraph`:**
- Run search agent in parallel with main conversation (fork mode)
- Give code agent its own token budget (prevent context consumption)
- Run summarization in background while user continues talking

**Implementation:** Spawn `asyncio.Task` with cloned `AgentState` and child cancellation token.

### 8.2 Inter-Agent Communication

Claude Code's `SendMessageTool` enables agents to communicate. For Tank, this maps to agent handoff with context passing.

**Current Tank flow:** Router → Agent → Done
**Enhanced flow:** Router → Agent → Handoff(with context) → Agent → Done

The handoff should carry:
- Summary of what the previous agent found
- Relevant tool results
- User's original intent

### 8.3 Task Output Streaming to Disk

Claude Code streams task outputs to disk files. The model receives a file path and reads chunks via `TaskOutputTool`. This handles arbitrarily large outputs without context overflow.

**For Tank:** When `run_command` or `persistent_shell` produces large output, write to a temp file and give the LLM a summary + file path reference.

---

## 9. Implementation Priority

### Phase 1 — Quick Wins (1-2 days each)

| # | Feature | Effort | Impact | Where |
|---|---------|--------|--------|-------|
| 1 | Error classification + differentiated retry | Low | High resilience | `llm/llm.py` |
| 2 | Tool result pairing guarantee | Low | Prevents subtle bugs | `agents/chat_agent.py` |
| 3 | Microcompact (clear old tool results) | Low | Free context savings | `pipeline/processors/brain.py` |
| 4 | Oversized result truncation | Low | Prevents context pollution | `tools/manager.py` |
| 5 | Auto-compact circuit breaker | Low | Prevents infinite loops | `pipeline/processors/brain.py` |
| 6 | Context injection (time, language, speaker) | Low | Saves tool calls | `pipeline/processors/brain.py` |

### Phase 2 — Moderate Effort (3-5 days each)

| # | Feature | Effort | Impact | Where |
|---|---------|--------|--------|-------|
| 7 | Concurrent tool execution | Medium | Latency improvement | `agents/chat_agent.py` |
| 8 | Explicit continuation reasons in loop | Medium | Better error recovery | `agents/graph.py` |
| 9 | Snip compaction (emergency drop) | Low | Safety valve | `pipeline/processors/brain.py` |
| 10 | Per-session cost tracking | Medium | User visibility | `pipeline/processors/brain.py`, `api/` |
| 11 | Effort levels (low/medium/high) | Medium | UX improvement | `agents/`, `pipeline/processors/brain.py` |
| 12 | Dependency injection for BrainDeps | Medium | Testability | `pipeline/processors/brain.py` |

### Phase 3 — Structural Investments (1-2 weeks each)

| # | Feature | Effort | Impact | Where |
|---|---------|--------|--------|-------|
| 13 | Skills / prompt templates | Medium | Extensibility | New: `backend/skills/` |
| 14 | Pre/Post tool hooks | High | Extensibility | `tools/manager.py`, `config/` |
| 15 | Stop hooks (auto-verify) | High | Quality assurance | `agents/graph.py` |
| 16 | Sub-agent forking with isolation | High | Parallel work | `agents/graph.py` |
| 17 | Per-pattern approval rules | Medium | Better safety | `agents/approval.py` |
| 18 | Session resume with full state | Medium | UX improvement | `persistence/checkpointer.py` |
| 19 | Structured abort hierarchy | Medium | Clean cancellation | `pipeline/`, `agents/` |
| 20 | Reactive compaction (resume mid-turn) | Medium | Better long conversations | `pipeline/processors/brain.py` |
| 21 | Deferred tool loading | Low | Token savings (when tools grow) | `tools/manager.py` |
| 22 | Extended thinking with keyword triggers | Medium | Voice UX | `pipeline/processors/brain.py` |

### Decision Guide

- **Start with Phase 1** — each item is a focused change to a single file, immediately improves robustness
- **Phase 2 when** — you're seeing real issues with latency (concurrent tools), context overflow (snip), or user confusion (cost tracking, effort)
- **Phase 3 when** — the tool set grows past ~15 tools, you need plugin-like extensibility, or you're building multi-agent workflows

---

## Design Philosophy (from Claude Code)

Six principles that Tank should adopt:

1. **Always have a fallback.** Compaction fails? Snip. Model overloaded? Don't retry background work. Tool times out? Synthesize an error result. Classifier rejects? Fall back to user prompt. Silence is the worst failure mode for a voice assistant.

2. **Generator-based streaming.** Every token flows immediately — no batching, no superstep synchronization. Tank already does this for TTS; extend it to the session level.

3. **Defense in depth.** Multiple layers of protection, each independent. Echo guard has two layers. Compaction has three strategies. Approval has three tiers. No single layer is trusted to be complete.

4. **Reliability through recovery.** The agentic loop has explicit recovery paths for every error class. Make recovery a first-class concept, not an afterthought.

5. **Feature-gated modularity.** New features should be toggleable via config. Skills, hooks, effort levels — all configurable in `config.yaml`, not hardcoded.

6. **Extensibility by design.** Tools, agents, skills, hooks — all have clean extension points. Users and operators can customize behavior at different levels of scope.
