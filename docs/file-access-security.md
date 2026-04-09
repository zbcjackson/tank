# File Access Security

This document describes Tank's file access security system — how the agent accesses host files safely through a defense-in-depth strategy.

## Trust Model

- **User**: fully trusted — can override any policy
- **Agent**: not trusted — may do something stupid (not malicious)
- **Goal**: prevent agent mistakes, not defend against attacks

The agent might read `~/.ssh/id_rsa` by mistake, overwrite `~/.bashrc` while "fixing" shell config, or delete files in the wrong directory. The security system prevents these accidents.

## Defense in Depth (5 Layers)

```
Layer 1: LLM Instructions (weakest — free, catches obvious mistakes)
         System prompt tells agent: "Don't read ~/.ssh, confirm before deleting"
         ↓ agent calls file_read("~/.ssh/id_rsa") anyway

Layer 2: File Access Policy (medium — code-enforced, configurable)
         policy.evaluate("~/.ssh/id_rsa", "read") → deny
         ↓ if result is require_approval:

Layer 3: ApprovalManager (medium — human in the loop)
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

## Two Enforcement Planes

**Plane A — Sandbox Backend (OS/container enforcement):**
Controls what the process CAN physically access. Enforces mounts, denied paths, network. Cannot distinguish `allow` from `require_approval`.

**Plane B — Access Policy (application-level):**
Controls what the agent is ALLOWED to access. Works identically for sandboxed and unsandboxed execution. Enforces `allow` / `require_approval` / `deny` per path and operation.

Both planes use the same config. If either blocks access, the operation fails.

## File Access Policy

Key files:

| File | Purpose |
|------|---------|
| `policy/file_access.py` | `FileAccessPolicy` — evaluates rules with most-specific-match-wins |
| `policy/backup.py` | `BackupManager` — snapshots files before modification |
| `policy/audit.py` | `AuditLogger` — append-only JSONL audit trail |
| `tools/file_read.py` | Read file with policy check |
| `tools/file_write.py` | Write file with policy + approval + backup |
| `tools/file_delete.py` | Delete file with policy + approval + backup |
| `tools/file_list.py` | List directory with policy check |

### Evaluation Logic

`FileAccessPolicy.evaluate(path, operation)` uses **most-specific-match-wins**:

1. Resolve path: `os.path.realpath(os.path.expanduser(path))` — follows symlinks
2. Collect all matching rules with specificity scores
3. Sort by priority (descending), then specificity (descending)
4. First match wins
5. If no match: fall back to defaults (`default_read`, `default_write`, `default_delete`)

Specificity scoring:
- Exact path: `1000 + len(path)` (most specific)
- Single glob (`*`): `500 + len(prefix)` (medium)
- Recursive glob (`**`): `len(prefix)` (least specific)

Conflicts (same priority + specificity, different levels) produce a warning log.

### File Tool Execution Flow

All four file tools follow the same pattern:

```
Agent calls file_write(path, content)
  │
  ├─ FileAccessPolicy.evaluate(path, "write")
  │   ├─ deny → return error immediately
  │   ├─ allow → proceed
  │   └─ require_approval → call ApprovalCallback
  │
  ├─ ApprovalCallback (if require_approval)
  │   ├─ Bridges to ApprovalManager.request_approval(...)
  │   ├─ User sees: "write /path/to/file (reason)"
  │   └─ Approved → proceed; Denied → return error
  │
  ├─ BackupManager.snapshot(path)  [write/delete only, if file exists]
  │   └─ Copy to ~/.tank/backups/{timestamp}/{relative_path}
  │
  └─ Execute: await asyncio.to_thread(write_file, path, content)
```

### Approval Callback

File tools enforce approval **inside** `execute()` via an `ApprovalCallback` protocol. This is critical because it works on ALL execution paths — whether the tool is called through `ChatAgent` (which has its own tool-level approval) or through `Brain` directly.

```python
@runtime_checkable
class ApprovalCallback(Protocol):
    async def __call__(
        self, tool_name: str, path: str, operation: str, reason: str,
    ) -> bool: ...
```

The callback is injected at tool registration time and bridges to `ApprovalManager`. If no callback is available, the safe default is to deny.

### Two-Tier Approval Architecture

| Tool category | Mechanism | Granularity |
|---------------|-----------|-------------|
| Sandbox tools (`run_command`, `persistent_shell`) | Hardcoded in `ToolApprovalPolicy` | Per-tool-name |
| File tools (`file_read`, `file_write`, etc.) | `ApprovalCallback` inside `execute()` | Per-path + per-operation |

Sandbox tools run arbitrary commands — tool-level approval is the only practical gate. File tools have structured arguments that `FileAccessPolicy` can evaluate per-path.

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

## Sandbox Configuration

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

## Configuration

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

  backup:
    enabled: true
    path: ~/.tank/backups
    max_age_days: 30

  audit:
    enabled: true
    log_path: ~/.tank/audit.jsonl

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

## Gotchas

1. **Symlinks are resolved before matching.** `os.path.realpath()` follows symlinks, so a rule for `/tmp/link` won't match if it's a symlink to `/home/user/file`. The resolved path is evaluated.

2. **Glob patterns are not recursive by default.** `*.txt` matches files in the current directory only. Use `**/*.txt` for recursive matching.

3. **`sandbox_exec` can bypass file tools.** The agent could use `sandbox_exec("cat ~/.ssh/id_rsa")` to bypass `file_read`'s policy. Mitigated by: (a) `~/.ssh` is in `denied_mounts_hardcoded` — not visible in sandbox, (b) LLM instructions tell agent to use file tools, (c) `ro` mounts prevent writes via shell. Sufficient for the "stupid, not malicious" threat model.

4. **Audit log has no rotation.** The JSONL log grows unbounded. Implement log rotation for production use.

5. **Backup directory is created on demand.** `BackupManager` creates `~/.tank/backups/` and subdirectories via `mkdir(parents=True, exist_ok=True)`.

6. **No callback = deny.** If `ApprovalCallback` is not injected (e.g., tool registered without approval system), `require_approval` decisions default to deny. This is the safe default.

## Example Walkthrough

```
User: "Delete ~/.bashrc"

Layer 1 — LLM instructions:
  System prompt says "confirm before modifying system config"
  → Agent might still call file_delete (prompt injection, confusion)

Layer 2 — File access policy:
  rules match "~/.bashrc" → "System configuration"
  delete: deny
  → BLOCKED. Tool returns "Access denied: ~/.bashrc (System configuration)"

(If this were a write instead of delete:)
  write: require_approval
  → ApprovalCallback fires
  → User sees: "write ~/.bashrc (System configuration)"
  → User approves or denies

Layer 4 — Sandbox boundary:
  ~ is mounted as ro
  → Even if Layers 1-3 all failed, rm would fail with read-only filesystem

Layer 5 — Auto-backup:
  (For approved writes, original is snapshotted before modification)
```
