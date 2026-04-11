# Skills System — Known Issues for Future Fix

## Issue 1: Fork Sub-Agent Runs Tools Without Approval

**Symptom**: When a skill runs in fork mode, the sub-agent (`skill_agent-browser`) calls `run_command` without going through the approval system.

**Root Cause**: The fork sub-agent is created as a plain `ChatAgent` without `approval_manager` or `approval_policy`. The `UseSkillTool._execute_fork()` bypasses the orchestration layer.

**Fix**: Use the new `run_agent()` method which always includes approval. This is resolved by the agent orchestration redesign.

---

## Issue 2: No UI Updates During Fork Execution

**Symptom**: When the fork sub-agent runs, the user sees no tool execution updates in the UI. The entire fork runs silently.

**Root Cause**: The fork sub-agent's `AgentOutput` items are consumed in a tight loop inside `UseSkillTool._execute_fork()`. Only `TOKEN` outputs are collected. `TOOL_EXECUTING` and `TOOL_RESULT` outputs are silently dropped. The normal flow goes through `BrainProcessor` which posts `BusMessage` events for each output.

**Fix**: Use `run_agent()` which streams all outputs through the Bus. Resolved by the agent orchestration redesign.

---

## Issue 3: Socket Permission Error (`Operation not permitted`)

**Symptom**: `agent-browser open https://weibo.com` fails with `Failed to create socket directory: Operation not permitted (os error 1)`.

**Root Cause**: The `agent-browser` CLI tries to create a Unix socket in a directory the process can't write to. This is an `agent-browser` configuration issue, not a Tank skills issue.

**Fix**: Configure `agent-browser` socket directory to a writable path (e.g., `/tmp/agent-browser/`).

---

## Issue 4: `allowed-tools` Format Mismatch

**Symptom**: SKILL.md uses Claude Code-style tool patterns like `Bash(npx agent-browser:*)` which don't map to Tank tool names (`run_command`, `persistent_shell`, etc.).

**Root Cause**: The `allowed-tools` field was designed for Claude Code's permission system. Tank uses different tool names.

**Fix Options**:
- (a) Define Tank-specific tool naming for `allowed-tools`
- (b) Add a mapping layer (Claude Code patterns → Tank tool names)
- (c) Use `allowed-tools` only as a signal for fork mode, not for tool filtering

---

## Issue 5: YAML Comma-Separated String Parsing

**Symptom**: `allowed-tools: Bash(npx agent-browser:*), Bash(agent-browser:*)` was parsed as empty `()` because YAML treats it as a single string, not a list.

**Status**: Fixed. Parser now splits comma-separated strings.

---

## Issue 6: `str(result)` Dumping Python Dict Repr as Tool Result

**Symptom**: LLM received garbled Python dict syntax like `{'skill_name': 'hello-world', ...}` as the tool result content.

**Status**: Fixed. `LLM.chat_stream()` now uses `result["message"]` when available, falls back to `json.dumps` for dicts.

---

## Issue 7: Fork Sub-Agent Re-Delegates Instead of Executing

**Symptom**: Fork sub-agent sees `delegate_to_coder` in its tool list, delegates to the coder worker instead of executing directly. The coder worker doesn't have the skill instructions in its context, so it generates text describing what to do instead of doing it.

**Root Cause**: Fork sub-agent was created with `tool_filter=None` (all tools), which includes `delegate_to_*` tools. The sub-agent's LLM chose to delegate rather than execute directly.

**Fix**: Resolved by the agent orchestration redesign — sub-agents use `disallowed-tools` to exclude the `agent` tool and skill management tools, but keep all execution tools.
