# Policy Redesign — Unified Security Verdict Protocol

## Problem

Tank has three security policies with inconsistent verdict types:

| Policy | Verdict type | Outcomes |
|--------|-------------|----------|
| `CommandSecurityPolicy` | `CommandVerdict(allowed: bool, reason: str)` | Binary: allowed or not. "Dangerous" and "unknown" collapse into `allowed=False`. |
| `FileAccessPolicy` | `AccessDecision(level: AccessLevel, reason: str)` | Three-way: `"allow"`, `"require_approval"`, `"deny"` |
| `NetworkAccessPolicy` | `NetworkAccessDecision(level: AccessLevel, reason: str)` | Three-way: `"allow"`, `"require_approval"`, `"deny"` |

File and network policies already have the right three-way design. Command policy is the outlier — it collapses two distinct outcomes into one boolean.

This causes problems for autonomous mode: when `CommandVerdict.allowed=False`, we can't tell if the command is genuinely dangerous (should always block) or just unknown (could be auto-approved by a trusted job). The headless runner has to choose between "block everything" or "allow everything" — no middle ground.

## Design Goals

1. **Unified verdict protocol** — all policies return the same three-way verdict type
2. **Pluggable approval resolvers** — the approval gate accepts a resolver that decides what to do with `require_approval` verdicts (interactive: ask user, headless: auto-approve or auto-reject)
3. **Policy protocol** — a common interface so new policies can be added without changing the gate

## Unified Verdict

Replace all policy-specific verdict types with a single `PolicyVerdict`:

```python
from enum import Enum
from dataclasses import dataclass
from typing import Any


class AccessLevel(Enum):
    """Three-way security verdict."""
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyVerdict:
    """Result of any security policy evaluation."""

    level: AccessLevel
    reason: str
    policy: str = ""          # Which policy produced this ("command", "file", "network")
    context: dict[str, Any] = field(default_factory=dict)  # Policy-specific metadata
```

### Migration from current types

| Current | New |
|---------|-----|
| `CommandVerdict(allowed=True, reason=...)` | `PolicyVerdict(level=ALLOW, reason=..., policy="command")` |
| `CommandVerdict(allowed=False, reason="dangerous pattern: ...")` | `PolicyVerdict(level=DENY, reason=..., policy="command")` |
| `CommandVerdict(allowed=False, reason="unknown command: ...")` | `PolicyVerdict(level=REQUIRE_APPROVAL, reason=..., policy="command")` |
| `AccessDecision(level="allow", reason=...)` | `PolicyVerdict(level=ALLOW, reason=..., policy="file")` |
| `AccessDecision(level="require_approval", reason=...)` | `PolicyVerdict(level=REQUIRE_APPROVAL, reason=..., policy="file")` |
| `AccessDecision(level="deny", reason=...)` | `PolicyVerdict(level=DENY, reason=..., policy="file")` |
| `NetworkAccessDecision(level=..., reason=...)` | Same mapping as file, with `policy="network"` |

### CommandSecurityPolicy changes

The key fix: `evaluate()` must distinguish "dangerous" from "unknown":

```python
# Before (binary)
def evaluate(self, command: str) -> CommandVerdict:
    danger = self._check_dangerous(command)
    if danger is not None:
        return danger                    # allowed=False
    verdict = self._evaluate_segment(segment)
    if not verdict.allowed:
        return verdict                   # allowed=False (same!)
    return CommandVerdict(allowed=True)

# After (three-way)
def evaluate(self, command: str) -> PolicyVerdict:
    danger = self._check_dangerous(command)
    if danger is not None:
        return PolicyVerdict(level=AccessLevel.DENY, ...)        # Hard block
    if self._is_safe(segment):
        return PolicyVerdict(level=AccessLevel.ALLOW, ...)       # Known safe
    return PolicyVerdict(level=AccessLevel.REQUIRE_APPROVAL, ...)  # Unknown
```

## Policy Protocol

A common interface for all security policies:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class SecurityPolicy(Protocol):
    """Protocol for security policies that produce three-way verdicts."""

    @property
    def name(self) -> str:
        """Policy identifier (e.g. 'command', 'file', 'network')."""
        ...

    def evaluate(self, **context: Any) -> PolicyVerdict:
        """Evaluate synchronously. Each policy defines its own context kwargs."""
        ...

    async def evaluate_async(self, **context: Any) -> PolicyVerdict:
        """Evaluate asynchronously (e.g. with LLM). Falls back to sync."""
        ...
```

Each policy implements this with its own context:

```python
# CommandSecurityPolicy
def evaluate(self, *, command: str) -> PolicyVerdict: ...

# FileAccessPolicy
def evaluate(self, *, path: str, operation: str) -> PolicyVerdict: ...

# NetworkAccessPolicy
def evaluate(self, *, host: str) -> PolicyVerdict: ...
```

## Approval Resolver

The approval gate currently has hardcoded behavior: `require_approval` → park and ask user. Replace this with a pluggable resolver:

```python
class ApprovalResolver(Protocol):
    """Decides what to do with REQUIRE_APPROVAL verdicts."""

    async def resolve(self, verdict: PolicyVerdict, tool_name: str,
                      tool_args: dict[str, Any]) -> AccessLevel:
        """Return ALLOW or DENY for a REQUIRE_APPROVAL verdict."""
        ...


class InteractiveResolver:
    """Park the call and ask the user. Used in normal interactive mode."""

    async def resolve(self, verdict, tool_name, tool_args) -> AccessLevel:
        # Park in PendingToolCallStore, post UI message, wait for user
        # (This is what ApprovalGateExecutor does today)
        ...
        return AccessLevel.ALLOW  # or DENY based on user response


class AlwaysApproveResolver:
    """Auto-approve all REQUIRE_APPROVAL verdicts. For trusted autonomous jobs."""

    async def resolve(self, verdict, tool_name, tool_args) -> AccessLevel:
        return AccessLevel.ALLOW


class AlwaysDenyResolver:
    """Auto-deny all REQUIRE_APPROVAL verdicts. Safe default for autonomous jobs."""

    async def resolve(self, verdict, tool_name, tool_args) -> AccessLevel:
        return AccessLevel.DENY


class LLMResolver:
    """Use an LLM to decide. For semi-trusted autonomous jobs."""

    def __init__(self, llm: Any, system_prompt: str = ""):
        self._llm = llm
        self._prompt = system_prompt

    async def resolve(self, verdict, tool_name, tool_args) -> AccessLevel:
        # Ask LLM: "Should this tool call be approved?"
        # Return ALLOW or DENY based on response
        ...
```

## Revised Approval Gate

The `ApprovalGateExecutor` becomes simpler — it evaluates the policy, then delegates `REQUIRE_APPROVAL` to the resolver:

```python
class ApprovalGateExecutor:
    def __init__(
        self,
        tool_manager: ToolManager,
        policy: ToolApprovalPolicy,
        resolver: ApprovalResolver,
        ...
    ):
        self._policy = policy
        self._resolver = resolver

    async def execute_openai_tool_call(self, tool_call) -> dict:
        verdict = await self._policy.evaluate_async(tool_name, tool_args)

        if verdict.level == AccessLevel.ALLOW:
            return await self._tool_manager.execute_openai_tool_call(tool_call)

        if verdict.level == AccessLevel.DENY:
            return {"error": f"Blocked by {verdict.policy} policy: {verdict.reason}"}

        # REQUIRE_APPROVAL — delegate to resolver
        resolved = await self._resolver.resolve(verdict, tool_name, tool_args)
        if resolved == AccessLevel.ALLOW:
            return await self._tool_manager.execute_openai_tool_call(tool_call)
        else:
            return {"error": f"Denied by approval resolver: {verdict.reason}"}
```

## Autonomous Mode Integration

With this design, the headless runner becomes trivial:

```python
# In AutonomousRunner._build_resolver()
if job.approval_mode == "always_approve":
    return AlwaysApproveResolver()
elif job.approval_mode == "always_deny":
    return AlwaysDenyResolver()
```

No more `_AutonomousApprovalPolicy` wrapper. The security policies run exactly the same way as interactive mode. Only the resolver changes.

### Approval mode naming

| Mode | Resolver | Behavior |
|------|----------|----------|
| `always_approve` | `AlwaysApproveResolver` | Unknown commands execute. Dangerous commands still blocked (DENY). |
| `always_deny` | `AlwaysDenyResolver` | Only pre-approved safe commands run. Unknown commands blocked. |

Note: `DENY` verdicts are never sent to the resolver — they're hard blocks. The resolver only handles `REQUIRE_APPROVAL`. So even `always_approve` can't override a dangerous-pattern block.

## Full Flow Diagram

```
Tool call
  │
  ▼
ToolApprovalPolicy.evaluate_async(tool_name, tool_args)
  │
  ├─ Non-command tool → PolicyVerdict(ALLOW)
  │
  └─ Command tool → CommandSecurityPolicy.evaluate_async(command)
       │
       ├─ Dangerous pattern match → PolicyVerdict(DENY, "dangerous: ...")
       ├─ Safe allowlist match    → PolicyVerdict(ALLOW, "safe command: ...")
       └─ Unknown command         → PolicyVerdict(REQUIRE_APPROVAL, "unknown: ...")
  │
  ▼
ApprovalGateExecutor
  │
  ├─ ALLOW            → execute tool
  ├─ DENY             → return error to agent (hard block)
  └─ REQUIRE_APPROVAL → resolver.resolve(verdict)
       │
       ├─ InteractiveResolver    → park, ask user, wait
       ├─ AlwaysApproveResolver  → execute tool
       ├─ AlwaysDenyResolver     → return error to agent
       └─ LLMResolver           → ask LLM, then execute or block
```

## File-level Changes

### New files
```
policy/verdict.py          # PolicyVerdict, AccessLevel enum, ApprovalResolver protocol,
                           # AlwaysApproveResolver, AlwaysDenyResolver
```

### Modified files
```
policy/command_security.py  # Return PolicyVerdict with three-way distinction (ALLOW/REQUIRE_APPROVAL/DENY)
policy/file_access.py       # Return PolicyVerdict, use AccessLevel enum
policy/network_access.py    # Return PolicyVerdict, use AccessLevel enum
policy/__init__.py          # Export new types, remove old verdict types
agents/approval.py          # ToolApprovalPolicy evaluates ALL tool types (command, file, network)
                           # ApprovalGateExecutor uses resolver pattern
                           # InteractiveResolver always parks for user confirmation
agents/llm_agent.py         # Pass resolver to ApprovalGateExecutor
agents/runner.py            # Pass resolver through to LLMAgent
tools/base.py               # Remove ApprovalCallback protocol (no longer needed)
tools/manager.py            # Create FileAccessPolicy, pass file_policy + network_policy to ToolApprovalPolicy
tools/groups.py             # Remove approval_callback from FileToolGroup and WebToolGroup
tools/file_read.py          # Remove REQUIRE_APPROVAL handling (gate handles it)
tools/file_write.py         # Remove REQUIRE_APPROVAL handling
tools/file_edit.py          # Remove REQUIRE_APPROVAL handling
tools/file_delete.py        # Remove REQUIRE_APPROVAL handling
tools/file_search.py        # Remove REQUIRE_APPROVAL handling
tools/file_list.py          # Remove REQUIRE_APPROVAL handling
tools/web_search.py         # Remove REQUIRE_APPROVAL handling
tools/web_fetch.py          # Remove REQUIRE_APPROVAL handling
core/assistant.py           # Pass resolver to ToolManager/AgentRunner
jobs/runner.py              # Use AlwaysApproveResolver / AlwaysDenyResolver
jobs/models.py              # Rename approval_mode: "always_approve" / "always_deny"
```

### Removed types
- `CommandVerdict` — replaced by `PolicyVerdict`
- `AccessDecision` — replaced by `PolicyVerdict`
- `NetworkAccessDecision` — replaced by `PolicyVerdict`
- `AccessLevel` literal type in file_access.py / network_access.py — replaced by `AccessLevel` enum
- `ApprovalCallback` protocol in tools/base.py — no longer needed
- `_AutonomousApprovalPolicy` in jobs/runner.py — replaced by resolver pattern
- `ResolverApprovalCallback` — no longer needed (gate handles all approvals)

## Implementation Order

1. **`policy/verdict.py`** — New unified types + resolver protocol
2. **`policy/command_security.py`** — Three-way verdict (the key fix)
3. **`policy/file_access.py`** + **`policy/network_access.py`** — Adapt to PolicyVerdict
4. **`agents/approval.py`** — Resolver-based gate
5. **`jobs/runner.py`** — Use AlwaysApproveResolver / AlwaysDenyResolver
6. **Tests** — Update all policy tests for three-way verdicts
7. **Remove** `_AutonomousApprovalPolicy` from runner.py

## Phase 2 Summary

This policy redesign is part of Phase 2 alongside the APScheduler migration:

- **APScheduler refactor** — Replace hand-built CronScheduler with AsyncScheduler
- **Policy protocol** — Unified PolicyVerdict, pluggable ApprovalResolver
- **CommandSecurityPolicy three-way** — Distinguish dangerous vs unknown
- **Approval mode rename** — `"auto"/"deny"` → `"always_approve"/"always_deny"`
