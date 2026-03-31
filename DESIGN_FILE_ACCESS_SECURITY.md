# Design: Unified File Access & Security Policy

## Status

Draft — 2026-03-31

## Problem

Tank's code agent runs commands in a Docker sandbox, but the agent has no way to
read or write files on the host. Users want Tank to help with files across their
system (projects, documents, app config), but unrestricted access risks:

- Accidental deletion or overwrite of important files
- Exposure of secrets (SSH keys, API credentials, `.env` files)
- Damage to OS configuration

Meanwhile, Tank already has sandbox backends (Docker, Seatbelt, Bubblewrap) and
an approval system — but they are not connected. The Docker sandbox mounts only
`./workspace`, the native backends are not wired into the assistant, and there is
no file-level access policy.

## Goals

1. Unified file access policy that works identically across sandbox and host execution
2. Unified network access policy with secret injection (agent never sees raw secrets)
3. Backend-agnostic sandbox config that translates to Docker, Seatbelt, and Bubblewrap
4. Same-path mounts so the agent sees the same paths the user talks about
5. Defense in depth: LLM instructions → file access policy → approval gate → sandbox boundary → auto-backup
6. Secure by default, but open enough to be useful out of the box

## Non-Goals

- Multi-user access control (Tank is single-user)
- Defending against a malicious user (user is trusted)
- Real-time file watching or sync
- Sandboxing the LLM transport or audio pipeline

## Trust Model

- **User**: fully trusted — can override any policy
- **Agent**: not trusted — may do something stupid (not malicious)
- **Goal**: prevent agent mistakes, not defend against attacks

The agent might:
- Read `~/.ssh/id_rsa` because it misunderstands a request
- Overwrite `~/.bashrc` while trying to "fix" shell config
- Delete files in the wrong directory
- Send file contents to an unintended network endpoint

The policy prevents these accidents while keeping the agent useful.

## Terminology

All code, config, and documentation use these terms consistently:

| Concept | Term | NOT |
|---------|------|----|
| The three access levels | `allow` / `require_approval` / `deny` | ~~ask~~, ~~prompt~~, ~~block~~, ~~permission~~ |
| The config section | `approval_policies` | ~~permissions~~, ~~access_control~~ |
| The runtime gate | `ApprovalManager` | ~~PermissionManager~~ |
| The policy evaluator | `ApprovalPolicy` | ~~PermissionPolicy~~ |
| The user interaction | "approval request" | ~~prompt~~, ~~permission dialog~~ |
| File operations | `read` / `write` / `delete` | ~~get~~, ~~put~~, ~~remove~~ |
| Network operations | `connect` | ~~access~~, ~~fetch~~ |

These align with Tank's existing `ApprovalManager`, `ApprovalPolicy`,
`approval_policies` config section, and `AgentOutputType.APPROVAL_NEEDED`.

## Architecture

### Defense in Depth (5 Layers)

```
Layer 1: LLM Instructions (weakest — free, catches obvious mistakes)
         System prompt tells agent: "Don't read ~/.ssh, confirm before deleting"
         ↓ agent calls file_read("~/.ssh/id_rsa") anyway

Layer 2: File/Network Access Policy (medium — code-enforced, configurable)
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

Any single layer catching a mistake is sufficient. All five failing simultaneously
is required for damage.

### Two Enforcement Planes

```
┌─────────────────────────────────────────────────────────────┐
│  Plane A: Sandbox Backend (OS/container enforcement)        │
│                                                             │
│  Controls what the process CAN physically access.           │
│  - Docker: only mounted paths exist in container            │
│  - Seatbelt: deny rules block syscalls                      │
│  - Bubblewrap: only bound paths are visible                 │
│                                                             │
│  Enforces: mounts, denied_mounts(_hardcoded), network_enabled│
│  Cannot enforce: allow vs require_approval distinction      │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│  Plane B: Access Policy (application-level)                 │
│                                                             │
│  Controls what the agent is ALLOWED to access.              │
│  - allow: proceed silently                                  │
│  - require_approval: ask user via ApprovalManager           │
│  - deny: refuse even if sandbox would allow it              │
│                                                             │
│  Enforces: file_access rules, network_access rules          │
│  Works identically for sandboxed and unsandboxed execution  │
└─────────────────────────────────────────────────────────────┘
```

Both planes use the same config. Plane A enforces the hard boundary (what's
physically possible). Plane B enforces the soft boundary (what's permitted by
policy). If either blocks access, the operation fails.

## Detailed Design

### 1. File Access Policy

#### Config Schema

```yaml
file_access:
  # Defaults when no rule matches
  default_read: allow                    # allow | require_approval | deny
  default_write: require_approval
  default_delete: require_approval

  # Rules evaluated top-down, first match wins
  rules:
    # Secrets — hard deny (even reads)
    - paths:
        - "~/.ssh/**"
        - "~/.gnupg/**"
        - "~/.aws/**"
        - "~/.config/gcloud/**"
        - "~/Library/Keychains/**"
        - "**/.env"
        - "**/.env.*"
        - "**/*.pem"
        - "**/*.key"
        - "**/id_rsa*"
        - "**/id_ed25519*"
        - "**/credentials*"
        - "**/*secret*"
      read: deny
      write: deny
      delete: deny
      reason: "Secrets and credentials"

    # OS safety — read ok, write needs approval, delete denied
    - paths:
        - "~/.bashrc"
        - "~/.zshrc"
        - "~/.profile"
        - "~/.bash_profile"
        - "~/.gitconfig"
        - "~/Library/**"
        - "/etc/**"
        - "/System/**"
        - "/usr/**"
        - "/bin/**"
        - "/sbin/**"
      read: allow
      write: require_approval
      delete: deny
      reason: "System configuration"

    # Package manager directories — read ok, write needs approval
    - paths:
        - "/opt/**"
        - "/usr/local/**"
      read: allow
      write: require_approval
      delete: require_approval
      reason: "Package manager directory"

  # Auto-backup before any approved write or delete
  backup:
    enabled: true
    path: ~/.tank/backups
    max_age_days: 30
```

#### Evaluation Logic

```python
class FileAccessPolicy:
    """Evaluates file access rules. Backend-agnostic."""

    def evaluate(self, path: str, operation: str) -> AccessDecision:
        """
        Args:
            path: Absolute or ~-prefixed path
            operation: "read" | "write" | "delete"

        Returns:
            AccessDecision with level (allow/require_approval/deny) and reason
        """
        resolved = os.path.realpath(os.path.expanduser(path))

        # Check rules top-down, first match wins
        for rule in self.rules:
            if self._path_matches(resolved, rule.paths):
                level = getattr(rule, operation, None)
                if level is not None:
                    return AccessDecision(level=level, reason=rule.reason)

        # Fall back to defaults
        return AccessDecision(
            level=self._defaults[operation],
            reason="default policy",
        )
```

Path matching supports:
- `~` expansion to user home
- `**` recursive glob
- `*` single-level glob
- Exact paths
- Paths are resolved (symlinks followed) before matching

#### File Tools

Four new tools, all using the same `FileAccessPolicy`:

| Tool | Operation | Default Policy |
|------|-----------|---------------|
| `file_read` | Read file contents | `allow` |
| `file_write` | Write/overwrite file | `require_approval` |
| `file_delete` | Delete file | `require_approval` |
| `file_list` | List directory contents | `allow` |

Why 4 tools, not 5 or 6:

- **No `file_edit` (string replacement)**: This is a coding-specific optimization
  (change 5 lines in a 500-line file without rewriting). For Tank's current use
  case as a voice/file assistant, `file_write` with full content is sufficient.
  Add `file_edit` later if Tank becomes a coding assistant.

- **No `file_search` (grep/glob)**: File discovery can be done through
  `sandbox_exec("find ...")` or `sandbox_exec("grep ...")`. The sandbox mount
  restrictions protect sensitive paths, and `file_read`'s policy check catches
  sensitive results when the agent reads what it found.

- **`sandbox_exec` bypass risk**: The agent could use `sandbox_exec("cat ~/.ssh/id_rsa")`
  to bypass `file_read`'s policy. This is mitigated by:
  - Layer 4: `~/.ssh` is in `denied_mounts_hardcoded` — not visible in sandbox
  - Layer 1: LLM instructions tell agent to use file tools for file operations
  - For mounted paths, the sandbox `ro` mount prevents writes via shell
  - Sufficient for the "agent is stupid, not malicious" threat model

Tool execution flow:

```
Agent calls file_write("/Users/alice/projects/app.py", content)
  │
  ├─ FileAccessPolicy.evaluate(path, "write")
  │   ├─ Check rules: no match for ~/projects/**
  │   └─ Fall back to default_write: require_approval
  │
  ├─ ApprovalManager.request_approval(...)
  │   └─ User approves via voice/UI
  │
  ├─ BackupManager.snapshot(path)  [if file exists]
  │   └─ Copy to ~/.tank/backups/2026-03-31T14:22:01/projects/app.py
  │
  └─ Execute write
      ├─ Sandboxed: sandbox.exec_command("cat > '{path}' << 'EOF'\n{content}\nEOF")
      └─ Unsandboxed: Path(path).write_text(content)
```

#### Reads: Host-Side vs Sandbox

File reads can execute either on the host or through the sandbox. The choice
depends on whether the sandbox is active and the file is accessible inside it:

- If sandbox is active and path is within a mounted scope → read through sandbox
- If sandbox is active but path is not mounted → read on host (policy still applies)
- If sandbox is not active → read on host

This means `FileAccessPolicy` is always the gatekeeper, regardless of execution path.

### 2. Network Access Policy

#### Config Schema

```yaml
network_access:
  # Default for unlisted hosts
  default: allow                         # allow | require_approval | deny

  rules:
    # Content sharing — could leak data
    - hosts:
        - "pastebin.com"
        - "hastebin.com"
        - "0x0.st"
        - "transfer.sh"
        - "dpaste.org"
      policy: require_approval
      reason: "Content sharing service — could leak data"

    # Anonymous networks
    - hosts:
        - "*.onion"
        - "*.i2p"
      policy: deny
      reason: "Anonymous network"

  # Secrets injected at tool level, never visible to LLM
  service_credentials:
    - name: serper
      env_var: SERPER_API_KEY
      allowed_hosts:
        - "google.serper.dev"

    - name: github
      env_var: GITHUB_TOKEN
      allowed_hosts:
        - "api.github.com"
```

#### Service Credentials

The agent sometimes needs to call APIs that require secrets. The secret must
never appear in the LLM context.

```
Agent sees:  "You have access to the 'serper' web search service"
Agent calls: web_search(query="python tutorials")
Tool layer:  Injects SERPER_API_KEY into HTTP request headers
LLM context: Never contains the key value
```

Implementation:

```python
class ServiceCredentialManager:
    """Injects credentials at tool execution time."""

    def get_env_for_sandbox(self) -> dict[str, str]:
        """Env vars to inject into sandbox container."""
        return {
            c.env_var: os.environ[c.env_var]
            for c in self.credentials
            if os.environ.get(c.env_var)
        }

    def validate_host(self, host: str, credential_name: str) -> bool:
        """Check if host is allowed to receive this credential."""
        cred = self._by_name.get(credential_name)
        if not cred:
            return False
        return any(fnmatch(host, pattern) for pattern in cred.allowed_hosts)
```

Credentials are:
- Stored in `.env` (existing pattern)
- Injected as env vars into Docker containers
- Available to host-side tools via `os.environ`
- Never included in LLM message history
- Bound to specific hosts — credential X can only be sent to its `allowed_hosts`

### 3. Sandbox Configuration (Backend-Agnostic)

#### Config Schema

```yaml
sandbox:
  enabled: true
  backend: auto                          # auto | docker | seatbelt | bubblewrap

  # What the sandbox can physically see (Plane A enforcement)
  mounts:
    - host: "~"
      mode: ro                           # ro | rw

  # Never mountable — hardcoded, not overridable by user config
  # Reading these files IS the security breach
  denied_mounts_hardcoded:
    - ~/.ssh
    - ~/.gnupg
    - ~/Library/Keychains
    - /var/run/docker.sock

  # Configurable denied mounts — sensible defaults, user can modify
  denied_mounts:
    - ~/.aws
    - ~/.azure
    - ~/.config/gcloud

  # Resource limits
  memory_limit: 1g
  cpu_count: 2
  network_enabled: true

  # Docker-specific
  docker:
    image: tank-sandbox:latest
    workspace_host_path: ./workspace

  # Seatbelt-specific (macOS)
  seatbelt:
    extra_allows: []

  # Bubblewrap-specific (Linux)
  bubblewrap:
    extra_args: []
```

#### Same-Path Mounts

All backends mount host paths at the same absolute path inside the sandbox:

```
Host:      /Users/alice/projects/app.py
Docker:    /Users/alice/projects/app.py    (not /workspace/app.py)
Seatbelt:  /Users/alice/projects/app.py    (native path, no translation)
Bubblewrap:/Users/alice/projects/app.py    (--ro-bind path path)
```

This means:
- Agent sees the same paths the user talks about
- No path translation layer needed
- Error messages reference real paths
- `pwd`, `.gitconfig` paths, file references in code — all just work

For Docker, this requires:
- Setting container `HOME` to match host user's home
- Creating the directory structure inside the container
- Mounting at absolute paths: `{abs_path: {"bind": abs_path, "mode": mode}}`

#### Backend Translation

The universal config translates to each backend:

| Universal concept | Docker | Seatbelt | Bubblewrap |
|-------------------|--------|----------|------------|
| `mounts[].mode: ro` | Volume `:ro` | `(allow file-read* (subpath ...))` | `--ro-bind path path` |
| `mounts[].mode: rw` | Volume `:rw` | `file-read*` + `file-write*` | `--bind path path` |
| `denied_mounts_hardcoded` | Not mounted | `(deny file-read* ...)` + `(deny file-write* ...)` | Not bound (invisible) |
| `denied_mounts` | Not mounted | `(deny file-read* ...)` + `(deny file-write* ...)` | Not bound (invisible) |
| `network_enabled: false` | `network_mode: "none"` | `(deny network*)` | `--unshare-net` |
| `memory_limit` | `--memory` | Not supported | `--rlimit-as` (limited) |
| `cpu_count` | `--cpus` | Not supported | Not supported |

#### Factory Wiring

The existing `SandboxFactory` is already implemented but not wired into the
assistant. The change is:

```python
# Current (assistant.py):
sandbox_config = SandboxConfig.from_dict(config.get("sandbox", {}))
self._sandbox = SandboxManager(sandbox_config)

# New:
sandbox_policy = SandboxPolicy.from_config(config.get("sandbox", {}))
self._sandbox = SandboxFactory.create(sandbox_policy)
```

`SandboxFactory.create()` already handles:
- Platform detection (macOS → Seatbelt, Linux → Bubblewrap, fallback → Docker)
- Availability probing (checks if `sandbox-exec` / `bwrap` / Docker is installed)
- Policy translation to backend-specific format

### 4. Auto-Backup

Before any approved write or delete on host files, the original is snapshotted:

```
~/.tank/backups/
  2026-03-31T14:22:01/
    Users/alice/projects/app.py
    Users/alice/.gitconfig
```

```python
class BackupManager:
    """Snapshots files before modification."""

    async def snapshot(self, path: str) -> str | None:
        """Backup file before overwrite. Returns backup path or None."""
        if not self.enabled:
            return None

        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            return None  # New file, nothing to back up

        timestamp = datetime.now().isoformat(timespec="seconds")
        # Strip leading / to create relative path under backup dir
        relative = str(resolved).lstrip("/")
        backup_path = self.backup_dir / timestamp / relative

        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, backup_path)

        self._cleanup_old_backups()
        return str(backup_path)
```

Cleanup removes backups older than `max_age_days`.

### 5. LLM Instructions (Layer 1)

Added to the agent system prompt:

```
## File Access

You have access to the user's files through file tools. Be careful:
- NEVER attempt to read files in ~/.ssh, ~/.gnupg, ~/.aws, or .env files
- ALWAYS confirm with the user before deleting files or modifying system config
- NEVER write secrets, passwords, or API keys into files
- When modifying config files, explain what you're changing and why
- For app installation or system changes, generate the command and let the user run it

IMPORTANT: Always use file tools (file_read, file_write, file_delete, file_list)
for file operations. Do NOT use sandbox_exec to read, write, or delete files.
File tools enforce access policy and create backups. sandbox_exec does not.

You may use sandbox_exec for file discovery (find, grep) when searching across
many files, but always use file_read to read the results.

The file access policy will block dangerous operations automatically, but you
should avoid triggering denials by being thoughtful about which files you access.
```

This is the weakest layer (bypassable via prompt injection) but costs nothing
and catches the common case where the agent "decides" to do something before
calling a tool.

## Config Reference

### Complete Default Config

```yaml
# ─── File Access Policy (Plane B — application-level) ───────────────
file_access:
  default_read: allow
  default_write: require_approval
  default_delete: require_approval

  rules:
    - paths:
        - "~/.ssh/**"
        - "~/.gnupg/**"
        - "~/.aws/**"
        - "~/.config/gcloud/**"
        - "~/Library/Keychains/**"
        - "**/.env"
        - "**/.env.*"
        - "**/*.pem"
        - "**/*.key"
        - "**/id_rsa*"
        - "**/id_ed25519*"
        - "**/credentials*"
        - "**/*secret*"
      read: deny
      write: deny
      delete: deny
      reason: "Secrets and credentials"

    - paths:
        - "~/.bashrc"
        - "~/.zshrc"
        - "~/.profile"
        - "~/.bash_profile"
        - "~/.gitconfig"
        - "~/Library/**"
        - "/etc/**"
        - "/System/**"
        - "/usr/**"
        - "/bin/**"
        - "/sbin/**"
      read: allow
      write: require_approval
      delete: deny
      reason: "System configuration"

    - paths:
        - "/opt/**"
        - "/usr/local/**"
      read: allow
      write: require_approval
      delete: require_approval
      reason: "Package manager directory"

  backup:
    enabled: true
    path: ~/.tank/backups
    max_age_days: 30

# ─── Network Access Policy ──────────────────────────────────────────
network_access:
  default: allow

  rules:
    - hosts:
        - "pastebin.com"
        - "hastebin.com"
        - "0x0.st"
        - "transfer.sh"
        - "dpaste.org"
      policy: require_approval
      reason: "Content sharing service"

    - hosts:
        - "*.onion"
        - "*.i2p"
      policy: deny
      reason: "Anonymous network"

  service_credentials:
    - name: serper
      env_var: SERPER_API_KEY
      allowed_hosts:
        - "google.serper.dev"

# ─── Sandbox (Plane A — OS/container enforcement) ───────────────────
sandbox:
  enabled: true
  backend: auto

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

  docker:
    image: tank-sandbox:latest
    workspace_host_path: ./workspace

  seatbelt:
    extra_allows: []

  bubblewrap:
    extra_args: []

# ─── Tool Approval Policies (existing, extended) ────────────────────
approval_policies:
  always_approve:
    - get_weather
    - get_time
    - calculate
    - file_read
    - file_list
  require_approval:
    - sandbox_exec
    - sandbox_bash
    - file_write
    - file_delete
  require_approval_first_time:
    - web_search
    - web_scraper
```

### How Layers Interact — Example Walkthrough

```
User: "Delete ~/.bashrc"

Layer 1 — LLM instructions:
  System prompt says "confirm before modifying system config"
  → Agent might still call file_delete (prompt injection, confusion)

Layer 2 — File access policy:
  file_access.rules match "~/.bashrc" → "System configuration"
  delete: deny
  → BLOCKED. Tool returns "Access denied: ~/.bashrc (System configuration)"

  (If this were a write instead of delete, it would be require_approval,
   and Layer 3 would engage)

Layer 3 — ApprovalManager:
  (Not reached for deny. For require_approval, user sees approval request
   and can approve or reject)

Layer 4 — Sandbox boundary:
  ~ is mounted as ro in sandbox
  → Even if Layers 1-3 all failed, rm would fail with read-only filesystem

Layer 5 — Auto-backup:
  (Not reached for deny. For approved writes, original is snapshotted first)
```

## Industry Comparison

| Feature | Claude Code | OpenClaw | Tank (this design) |
|---------|------------|----------|--------------------|
| File read default | Unrestricted | Unrestricted (sandbox off) | `allow` with deny rules |
| File write default | CWD only | Unrestricted (sandbox off) | `require_approval` |
| Secret protection | Deny list (write only) | No built-in deny list | Deny list (read + write) |
| Sandbox backends | Seatbelt/bubblewrap | Docker/SSH/OpenShell | Docker/Seatbelt/bubblewrap |
| Network control | Domain proxy | Per-host in sandbox | Per-host allow/require_approval/deny |
| Secret injection | N/A | N/A | Tool-level, never in LLM context |
| Auto-backup | No | No | Yes |
| Same-path mounts | N/A (host-only) | No (/workspace) | Yes |

## Existing Code — What Changes

### Files Modified

| File | Change |
|------|--------|
| `sandbox/policy.py` | Extend `SandboxPolicy` with mount config, `denied_mounts_hardcoded`, `denied_mounts` |
| `sandbox/protocol.py` | Add `background` param to `exec_command`, add `list_processes`/`poll_process`/`kill_process`/`process_log` |
| `sandbox/factory.py` | Update Docker translation to use same-path mounts, pass `denied_mounts_hardcoded` + `denied_mounts` |
| `sandbox/manager.py` | Support same-path volume mounts, env injection, background exec via detached Docker exec |
| `sandbox/backends/seatbelt.py` | Add `denied_mounts` as explicit deny rules, background process support via `Popen` |
| `sandbox/backends/bubblewrap.py` | Add `denied_mounts` exclusion, background process support via `Popen` |
| `sandbox/types.py` | Add `ProcessHandle`, `ProcessOutput`, `SandboxCapabilities` |
| `core/assistant.py` | Use `SandboxFactory.create()` instead of direct `SandboxManager()` |
| `tools/manager.py` | Register file tools, accept `FileAccessPolicy` |
| `tools/sandbox_exec.py` | Add `background` parameter |
| `tools/sandbox_process.py` | Use protocol methods instead of Docker-specific session API |
| `agents/approval.py` | No changes (already supports the needed patterns) |
| `core/config.yaml` | Add `file_access`, `network_access` sections; update `sandbox` section |

### Files Created

| File | Purpose |
|------|---------|
| `policy/__init__.py` | Package init |
| `policy/file_access.py` | `FileAccessPolicy` — evaluates file access rules |
| `policy/network_access.py` | `NetworkAccessPolicy` — evaluates network rules |
| `policy/credentials.py` | `ServiceCredentialManager` — secret injection |
| `policy/backup.py` | `BackupManager` — auto-snapshot before writes |
| `tools/file_read.py` | `FileReadTool` — read file with policy check |
| `tools/file_write.py` | `FileWriteTool` — write file with policy + approval + backup |
| `tools/file_delete.py` | `FileDeleteTool` — delete file with policy + approval + backup |
| `tools/file_list.py` | `FileListTool` — list directory with policy check |

### Files Unchanged

| File | Why |
|------|-----|
| `agents/approval.py` | Already supports `allow`/`require_approval`/`deny` pattern |
| `tools/sandbox_bash.py` | Docker-only, no changes needed |

## Migration Plan

### Phase 1: File Access Policy + File Tools

1. Create `policy/file_access.py` with `FileAccessPolicy`
2. Create `policy/backup.py` with `BackupManager`
3. Create file tools (`file_read`, `file_write`, `file_delete`, `file_list`)
4. Add `file_access` section to `config.yaml`
5. Register file tools in `ToolManager`
6. Wire `FileAccessPolicy` into assistant initialization
7. Add file tools to `approval_policies` config

Deliverable: Agent can read/write/delete host files with policy enforcement
and auto-backup. File tools execute on host with `FileAccessPolicy` as gatekeeper.

### Phase 2: Wire SandboxFactory + Same-Path Mounts

1. Extend `SandboxPolicy` with mount config, `denied_mounts_hardcoded`, `denied_mounts`
2. Update `SandboxFactory` Docker translation for same-path mounts
3. Update `SandboxManager` to support same-path volume mounts
4. Change `assistant.py` to use `SandboxFactory.create()`
5. Update Seatbelt backend: `denied_mounts_hardcoded` as explicit deny rules, `denied_mounts` as deny rules
6. Update Bubblewrap backend: exclude both `denied_mounts_hardcoded` and `denied_mounts` from binds
7. Add `SandboxCapabilities` so tools can discover backend features

Deliverable: Sandbox backend is auto-selected per platform. Mounts use
same paths as host. Native backends (Seatbelt/Bubblewrap) are available.

### Phase 3: Background Processes on All Backends

1. Add `background` parameter to `Sandbox` protocol's `exec_command`
2. Add `list_processes`/`poll_process`/`kill_process`/`process_log` to protocol
3. Implement background process support in Seatbelt backend via `Popen` + PID tracking
4. Implement background process support in Bubblewrap backend via `Popen` + PID tracking
5. Update Docker backend to use protocol methods for process management
6. Update `sandbox_exec` tool to accept `background` parameter
7. Update `sandbox_process` tool to use protocol methods instead of Docker-specific API
8. Mark `sandbox_bash` as Docker-only in tool description and agent system prompt

Deliverable: `sandbox_exec(background=True)` and `sandbox_process` work on all
backends. `sandbox_bash` remains Docker-only. Agent adapts via capability discovery.

### Phase 4: Network Access Policy + Service Credentials

1. Create `policy/network_access.py` with `NetworkAccessPolicy`
2. Create `policy/credentials.py` with `ServiceCredentialManager`
3. Add `network_access` section to `config.yaml`
4. Inject credentials as env vars into sandbox containers
5. Validate outbound hosts against network policy in HTTP-calling tools

Deliverable: Network access is policy-controlled. API secrets are injected
at tool level, never visible to the LLM.

### Phase 5: LLM Instructions + Audit Log

1. Add file access instructions to agent system prompts
2. Add sandbox capability guidance to agent system prompts
3. Add audit logging for all file and network operations
4. Add `tank-backup list` / `tank-backup restore` CLI commands

Deliverable: Full defense-in-depth stack operational. Users can review
and restore from backups.

## Testing Strategy

### Unit Tests

- `FileAccessPolicy`: rule matching, glob patterns, defaults, first-match-wins
- `NetworkAccessPolicy`: host matching, wildcard patterns, defaults
- `BackupManager`: snapshot creation, cleanup, age-based expiry
- `ServiceCredentialManager`: env injection, host validation
- File tools: policy check → approval → backup → execute flow
- `SandboxCapabilities`: correct capabilities reported per backend
- Background process: start, poll, kill lifecycle on each backend
- `denied_mounts_hardcoded`: cannot be overridden by user config
- `denied_mounts`: can be modified by user config

### Integration Tests

- File tool + Docker sandbox: read/write through container with same-path mounts
- File tool + Seatbelt: read allowed path, deny blocked path
- File tool + Bubblewrap: read allowed path, deny blocked path
- File tool + policy deny: tool returns error without executing
- Approval flow: require_approval triggers ApprovalManager, deny skips it
- Background exec + poll + kill on Docker backend
- Background exec + poll + kill on Seatbelt backend
- Background exec + poll + kill on Bubblewrap backend
- `sandbox_bash` available on Docker, unavailable on native backends
- Same-path mounts: paths inside container match host paths
- `denied_mounts_hardcoded` paths not visible inside any backend

### E2E Tests

- User asks agent to read a project file → succeeds
- User asks agent to read ~/.ssh/id_rsa → denied with explanation
- User asks agent to write a file → approval requested → approved → file written + backup created
- User asks agent to delete system file → denied
- User asks agent to run a long build → background exec, agent polls for completion
- User asks agent to kill a stuck process → sandbox_process kill succeeds

## Resolved Design Decisions

### 1. file_write: host-side execution

**Decision**: `file_write` executes on the host, not through the sandbox.

Rationale:
- `FileAccessPolicy` is the primary defense — evaluates identically regardless
  of execution path
- `ApprovalManager` is the second defense — user confirms before any write
- `BackupManager` is the third defense — original is snapshotted before overwrite
- Three layers is sufficient for the trust model (preventing agent mistakes)
- Host-side avoids Docker exec latency (~50-100ms) and content piping complexity
- The sandbox `ro` mount is still defense-in-depth for `sandbox_exec`/`sandbox_bash`
  — if the agent tries to write via shell instead of `file_write`, the mount blocks it

If stronger isolation is needed later, the execution path can be changed inside
`FileWriteTool.execute()` without changing the tool interface.

### 2. denied_mounts: split into hardcoded + configurable

**Decision**: Two tiers of denied mounts.

Hardcoded (not overridable — data itself is the secret, even ro is dangerous):

```yaml
denied_mounts_hardcoded:       # Cannot be removed by user config
  - ~/.ssh                     # Private keys — reading IS the damage
  - ~/.gnupg                   # Private GPG keys
  - ~/Library/Keychains        # macOS keychain databases
  - /var/run/docker.sock       # Docker socket = full host control
```

Configurable defaults (user can remove if they have a reason):

```yaml
denied_mounts:                 # User can modify these
  - ~/.aws
  - ~/.azure
  - ~/.config/gcloud
```

Rationale: `~/.ssh` and `~/.gnupg` contain private keys where reading the file
IS the security breach — no policy bug or approval mistake can undo that exposure.
`~/.aws` contains credentials but also region/profile config that an agent might
legitimately need. The file access policy's per-file deny rules provide finer
control for these paths.

### 3. Persistent sessions: background processes on all backends, stateful shell Docker-only

**Decision**: Separate "long-running process management" from "stateful shell."

The existing `sandbox_bash` and `sandbox_process` tools conflate two distinct needs:

1. **Long-running process management** — start a build, poll output, kill if stuck
2. **Stateful shell** — `cd`, `export`, `pip install` carry over between commands

These are separable. Long-running processes can work on all backends. Stateful
shell is inherently a Docker feature.

#### Background process support (all backends)

Add `background` parameter to `sandbox_exec`:

```python
sandbox_exec(
    command="./build.sh",
    timeout=600,
    background=False,      # new parameter
)
```

Backend implementation:

| Backend | One-shot (background=False) | Background (background=True) |
|---------|---------------------------|------------------------------|
| Docker | `exec_run()`, wait | `exec_run(detach=True)`, track in sessions |
| Seatbelt | `subprocess.run()`, wait | `subprocess.Popen()`, track PID |
| Bubblewrap | `subprocess.run()`, wait | `subprocess.Popen()`, track PID |

For native backends, background means:
- Start sandboxed process with `Popen` instead of `run`
- Store `Popen` object (PID, stdout/stderr pipes)
- Return immediately with a session ID

#### sandbox_process: extended to all backends

`sandbox_process` actions work on all backends via PID tracking:

| Action | Docker | Seatbelt/Bubblewrap |
|--------|--------|---------------------|
| `list` | List Docker exec sessions | List tracked Popen objects |
| `poll` | Read from PTY buffer | Read from stdout pipe |
| `log` | Full output history | Buffered output history |
| `kill` | Send signal to exec | `proc.terminate()` / `proc.kill()` |
| `write` | Write to PTY stdin | Not supported (no PTY) |
| `clear` | Clear output buffer | Clear output buffer |
| `remove` | Remove session tracking | Remove session tracking |

The `write` action (sending stdin to a running process) remains Docker-only
because native backends don't have PTY sessions.

#### sandbox_bash: Docker-only

Stateful interactive shell sessions remain Docker-only. On native backends,
the agent compensates by chaining commands:

```bash
# Instead of relying on state across calls:
#   sandbox_bash("cd /projects")
#   sandbox_bash("pip install requests")
#   sandbox_bash("python app.py")

# Agent chains in a single call:
sandbox_exec("cd /projects && pip install -r requirements.txt && python app.py")
```

This is the same pattern Claude Code uses — each Bash call is a fresh shell,
and the LLM chains commands with `&&`.

#### Protocol extension

The `Sandbox` protocol gains optional background process support:

```python
class Sandbox(Protocol):
    # Existing
    async def exec_command(self, command, timeout=None, working_dir=None,
                           background=False) -> ExecResult: ...
    async def cleanup(self) -> None: ...

    @property
    def is_running(self) -> bool: ...

    # New — background process management
    async def list_processes(self) -> list[ProcessInfo]: ...
    async def poll_process(self, session_id: str) -> ProcessOutput: ...
    async def kill_process(self, session_id: str) -> bool: ...
    async def process_log(self, session_id: str) -> str: ...
```

Native backend implementation sketch:

```python
class SeatbeltSandbox:
    def __init__(self, policy):
        self._processes: dict[str, ProcessHandle] = {}

    async def exec_command(self, command, timeout=120, background=False, **kw):
        if background:
            proc = subprocess.Popen(
                ["sandbox-exec", "-p", self._profile, "bash", "-c", command],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            session_id = f"proc-{proc.pid}"
            self._processes[session_id] = ProcessHandle(
                proc=proc,
                output_buffer=deque(maxlen=10000),
                started_at=datetime.now(),
            )
            self._start_reader(session_id)
            return ExecResult(
                stdout=f"Background process started: {session_id}",
                stderr="", exit_code=0,
            )
        else:
            return await self._exec_sync(command, timeout, **kw)

    async def kill_process(self, session_id: str) -> bool:
        handle = self._processes.get(session_id)
        if not handle:
            return False
        handle.proc.terminate()
        try:
            handle.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            handle.proc.kill()
        return True
```

#### Capability discovery

Tools advertise what the current backend supports:

```python
@dataclass(frozen=True)
class SandboxCapabilities:
    exec_command: bool = True          # All backends
    background_process: bool = True    # All backends
    kill_process: bool = True          # All backends
    stateful_shell: bool = False       # Docker only
    interactive_stdin: bool = False    # Docker only
```

The agent queries capabilities and adapts. If `stateful_shell` is False, it
chains commands with `&&`. If `interactive_stdin` is False, it avoids tools
that need stdin interaction.

#### Agent system prompt guidance

```
## Sandbox capabilities

sandbox_exec: Run a single command.
- Use background=true for long-running commands (builds, servers, installs)
- Chain related commands with && when state must carry over:
  GOOD: sandbox_exec("cd /projects && pip install -r requirements.txt && pytest")
  BAD:  sandbox_exec("cd /projects") then sandbox_exec("pytest")

sandbox_process: Manage background processes.
- poll: Check output of a running process
- kill: Stop a hung or stuck process
- log: View full output history
- list: See all running processes

sandbox_bash: Interactive shell sessions (Docker backend only).
- Persistent working directory and environment across commands
- Raw I/O mode for interactive programs
- Not available on Seatbelt/Bubblewrap backends
```

## Appendix: How Other Tools Compare

### Claude Code
- File tools (Read/Edit/Write) run in the Claude Code process, not sandboxed
- OS sandbox (Seatbelt/bubblewrap) only covers Bash commands
- Default: reads unrestricted, writes to CWD only, deny list for sensitive write paths
- Network: domain allowlist via proxy (the real exfiltration defense)

### OpenClaw
- Three layers: sandbox runtime + tool policy + exec approvals
- Sandbox off by default — user opts in
- When sandboxed: file tools routed through container filesystem
- When unsandboxed: file tools run on host with tool policy only
- Exec approvals: binary path allowlists, safe bins, strict inline eval
- No built-in file path deny list

### Aider
- No sandbox, no shell execution
- Explicit file list model: agent can only see files user `/add`s
- Git auto-commit for every change (easy rollback)
- Simplest and most restrictive model

### Tank (This Design)
- Unified policy across sandbox and host execution
- Default: reads allowed, writes need approval, secrets denied
- Same-path mounts (no path confusion)
- Auto-backup before writes (unique among all tools surveyed)
- Backend-agnostic config (Docker/Seatbelt/Bubblewrap)
- Service credentials injected at tool level (never in LLM context)
- Two-tier denied mounts: hardcoded (secrets) + configurable (credentials)
- Background processes on all backends; stateful shell Docker-only
- Capability discovery so agent adapts to backend automatically
