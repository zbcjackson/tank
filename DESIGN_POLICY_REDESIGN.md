# Policy Redesign — Unified Security Verdict Protocol

## Status: IMPLEMENTED

All changes described below have been implemented and tested (1684 tests pass).

## Problem (solved)

Tank had three security policies with inconsistent verdict types and a fragmented approval flow. File/network tools handled approval internally via `ApprovalCallback`, while command tools went through the `ApprovalGateExecutor`. This made it impossible to have a unified approval flow for autonomous mode.

## Solution

### Unified Verdict

All policies return `PolicyVerdict` with a three-way `AccessLevel`:

```python
class AccessLevel(Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"

@dataclass(frozen=True)
class PolicyVerdict:
    level: AccessLevel
    reason: str
    policy: str = ""  # "command", "file", "network", "tool"
```

### Centralized Approval Gate

`ToolApprovalPolicy` evaluates ALL tool types — command, file, and network:

```python
class ToolApprovalPolicy:
    def __init__(self, command_policy, file_policy, network_policy, llm):
        ...

    async def evaluate_async(self, tool_name, tool_args) -> PolicyVerdict:
        if tool_name in COMMAND_TOOLS:  # run_command, persistent_shell
            return command_policy.evaluate_async(command)
        if tool_name in FILE_TOOLS:    # file_read, file_write, etc.
            return file_policy.evaluate(path, operation)
        if tool_name in WEB_TOOLS:     # web_fetch, web_search
            return network_policy.evaluate(host)
        return PolicyVerdict(ALLOW)    # other tools auto-approved
```

`ApprovalGateExecutor` handles ALL `REQUIRE_APPROVAL` verdicts via a pluggable resolver:

```
Tool call → ToolApprovalPolicy.evaluate_async() → verdict:
  ├─ ALLOW            → execute tool
  ├─ DENY             → return error (hard block, no resolver can override)
  └─ REQUIRE_APPROVAL → resolver.resolve() → decision:
       ├─ InteractiveResolver  → REQUIRE_APPROVAL → gate parks, confirm agent asks user
       ├─ AlwaysApproveResolver → ALLOW → execute (autonomous trusted)
       └─ AlwaysDenyResolver    → DENY → block (autonomous safe default)
```

File and web tools no longer handle approval internally — they only keep `DENY` checks as a safety net. The `ApprovalCallback` protocol has been removed entirely.

### InteractiveResolver

Returns `REQUIRE_APPROVAL` for all tool types, causing the gate to park the call and ask the user via the confirm agent flow. This applies equally to command tools, file tools, and network tools.

### Autonomous Mode

Jobs specify `approval_mode`:
- `always_deny` (default) — `AlwaysDenyResolver` blocks unknown commands and unapproved file writes
- `always_approve` — `AlwaysApproveResolver` auto-approves everything the security policy doesn't hard-block (DENY)

DENY verdicts are never sent to the resolver — they're hard blocks regardless of mode.

## File Changes (completed)

### New files
```
policy/verdict.py          # PolicyVerdict, AccessLevel, ApprovalResolver protocol,
                           # AlwaysApproveResolver, AlwaysDenyResolver
tests/test_policy_integration.py  # 23 integration tests covering all seams
```

### Modified files
```
policy/command_security.py  # Three-way verdict (ALLOW/REQUIRE_APPROVAL/DENY)
policy/file_access.py       # Returns PolicyVerdict, uses AccessLevel enum
policy/network_access.py    # Returns PolicyVerdict, uses AccessLevel enum
policy/__init__.py          # Updated exports
agents/approval.py          # ToolApprovalPolicy evaluates ALL tool types
                           # ApprovalGateExecutor uses resolver pattern
                           # InteractiveResolver always parks for user
agents/llm_agent.py         # Passes resolver to ApprovalGateExecutor
agents/runner.py            # Passes resolver through to LLMAgent
tools/base.py               # Removed ApprovalCallback protocol
tools/manager.py            # Creates FileAccessPolicy, passes to ToolApprovalPolicy
tools/groups.py             # Removed approval_callback from FileToolGroup/WebToolGroup
tools/file_*.py             # Removed REQUIRE_APPROVAL handling (6 files)
tools/web_*.py              # Removed REQUIRE_APPROVAL handling (2 files)
jobs/runner.py              # Uses AlwaysApproveResolver / AlwaysDenyResolver
jobs/models.py              # approval_mode: "always_approve" / "always_deny"
```

### Removed
- `CommandVerdict`, `AccessDecision`, `NetworkAccessDecision` — replaced by `PolicyVerdict`
- `ApprovalCallback` protocol — no longer needed
- `ResolverApprovalCallback` — no longer needed
- `_AutonomousApprovalPolicy` — replaced by resolver pattern
