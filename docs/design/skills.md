# Skills

Skills are reusable, composable capabilities that Tank can learn, create, install, and execute. A skill is a structured prompt (markdown) with optional scripts and metadata that teaches Tank how to do something specific.

## Architecture

```
skills/                              # Module: backend/core/src/tank_backend/skills/
├── models.py                        # SkillMetadata, SkillDefinition, ReviewResult
├── parser.py                        # Parse SKILL.md (YAML frontmatter + markdown)
├── registry.py                      # Discover, index, deduplicate skills from disk
├── reviewer.py                      # Security review: static analysis + risk scoring
├── manager.py                       # Orchestration: invoke, create, install, remove
└── source.py                        # SkillSource ABC + GitSource, LocalSource

tools/
├── skill_tools.py                   # UseSkillTool, ListSkillsTool, CreateSkillTool, InstallSkillTool
└── groups.py                        # SkillToolGroup — registers skill tools
```

Key files:

| File | Purpose |
|------|---------|
| `skills/models.py` | `SkillMetadata`, `SkillDefinition`, `ReviewResult` dataclasses |
| `skills/parser.py` | Parse SKILL.md, compute content hash, validate frontmatter |
| `skills/registry.py` | `SkillRegistry` — scan directories, deduplicate by name |
| `skills/reviewer.py` | `SecurityReviewer` — static analysis, risk scoring |
| `skills/manager.py` | `SkillManager` — invoke, create, install, remove, catalog |
| `skills/source.py` | `SkillSource` ABC, `GitSource`, `LocalSource`, `find_skill_dirs()` |
| `tools/skill_tools.py` | Tool wrappers: `UseSkillTool`, `ListSkillsTool`, `CreateSkillTool`, `InstallSkillTool` |

## Skill Definition Format

Skills follow the Agent Skills open standard — a directory containing a `SKILL.md` file with YAML frontmatter:

```
my-skill/
├── SKILL.md          # Required: metadata + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: documentation
└── assets/           # Optional: templates, config files
```

### SKILL.md

```yaml
---
name: hello-world
description: "A simple greeting skill"
version: "1.0.0"
allowed-tools: []
approval: auto
tags: [example]
context: inline
---

Greet the user warmly. If arguments are provided, treat them as the person's name.
```

### Frontmatter Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | Yes | — | Lowercase alphanumeric + hyphens, 1-64 chars |
| `description` | Yes | — | Short description for the skill catalog |
| `version` | No | `1.0.0` | Semantic version |
| `author` | No | `""` | Author name |
| `allowed-tools` | No | `[]` | Tools this skill needs (triggers fork mode if non-empty) |
| `approval` | No | `auto` | `auto`, `always`, or `first-time` |
| `tags` | No | `[]` | Tags for categorization |
| `context` | No | `inline` | `inline` or `fork` — execution mode |

`allowed-tools` accepts both YAML list syntax and comma-separated strings:
```yaml
allowed-tools: [web_search, web_fetch]
# or
allowed-tools: web_search, web_fetch
```

## How Skills Work

### Discovery and Registration

On startup, `SkillToolGroup` creates a `SkillRegistry` that scans configured directories for subdirectories containing `SKILL.md`:

```yaml
# config.yaml
skills:
  enabled: true
  dirs:
    - ../skills              # project-level
    - ~/.tank/skills         # user-level
  auto_approve_threshold: low
```

Priority: first directory wins on name conflict (project overrides user).

### Security Review

Every skill goes through `SecurityReviewer` before activation:

1. **Structure validation** — valid SKILL.md, valid frontmatter, only `.py`/`.sh`/`.bash` in `scripts/`
2. **Script static analysis** — scan for dangerous patterns: dynamic code execution, subprocess, network libraries, destructive file ops
3. **Tool scope check** — flag if instructions reference tools not declared in `allowed-tools`
4. **Risk scoring**:

| Risk | Criteria | Auto-approve at threshold |
|------|----------|--------------------------|
| `low` | Prompt-only, no scripts, safe tools | `low` (default) |
| `medium` | Has scripts/ or uses network tools | `medium` |
| `high` | Uses sandbox or file tools | `high` |
| `critical` | Dangerous patterns in scripts | Never auto-approved |

Review state is persisted in a `.review` file (YAML with content hash). On startup, if the hash doesn't match, the skill is disabled until re-reviewed.

### Skill Catalog (System-Reminder Injection)

The skill catalog is injected per-turn as a system-reminder in the system prompt — not baked into the static system prompt. This means:

- The catalog is always fresh (new skills appear immediately)
- Budget-constrained: max 8000 chars, descriptions truncated to 250 chars
- Updated mid-conversation when skills are created/installed

```
AVAILABLE SKILLS:
When a user's request matches a skill, call the use_skill tool with the skill name.

- hello-world: A simple greeting skill [tags: example]
- agent-browser: Browser automation CLI for AI agents [tags: web]
```

### Execution: Inline vs Fork

**Inline mode** (`context: inline`, the default, no `allowed-tools`):

The skill instructions are returned as the `use_skill` tool result. The LLM reads them and follows them in subsequent turns of the same `chat_stream` loop. The `message` field is formatted as a directive:

```
SKILL ACTIVATED: hello-world
You MUST now follow these instructions step by step...
--- BEGIN SKILL INSTRUCTIONS ---
...
--- END SKILL INSTRUCTIONS ---
```

The `LLM.chat_stream()` tool result handling uses `result["message"]` as the content sent to the LLM (not `str(result)` which would dump the Python dict).

**Fork mode** (`context: fork`, or `allowed-tools` is non-empty):

The skill runs as a sub-agent via `AgentRunner.run_agent()`. A dynamic `AgentDefinition` is created from the skill with `disallowed_tools` set to prevent recursive skill/agent calls. The sub-agent gets all execution tools, approval inherited from parent, and outputs streamed via Bus.

Auto-escalation: if `allowed-tools` is non-empty, the skill automatically runs in fork mode even if `context: inline` is set.

### Tool Result Handling

`LLM.chat_stream()` converts tool results to the content string sent to the LLM:

1. If `result` is a dict with a `"message"` key, use `result["message"]`
2. If `result` is a dict without `"message"`, use `json.dumps(result)`
3. Otherwise, use `str(result)`

This gives tools control over what the LLM sees. Skills use this to send clean instruction text instead of garbled Python dict repr.

## Tools

### `use_skill`

The single router tool. The LLM calls it with a skill name and optional args.

```
use_skill(skill="hello-world", args="Jackson")
```

### `list_skills`

Lists all available skills with metadata.

### `create_skill`

Creates a new skill from a name, description, and instructions. Auto-reviews and registers.

### `install_skill`

Installs skills from a git URL or local path. Supports multi-skill repos.

```
install_skill(source="https://github.com/user/skills-repo")
install_skill(source="https://github.com/user/skills-repo", skill_name="pirate-speak")
install_skill(source="/tmp/my-skill")
```

The install flow: `SkillSource.fetch()` then `find_skill_dirs()` then filter by `skill_name` then copy to local skills dir then `install_from_path()` (review + register).

`GitSource` clones with `--depth 1`. `find_skill_dirs()` searches up to 2 levels deep for `SKILL.md` files, handling single-skill repos, multi-skill repos, and monorepo layouts.

## Configuration

```yaml
skills:
  enabled: true
  dirs:
    - ../skills
    - ~/.tank/skills
  auto_approve_threshold: low    # low | medium | high
```

## Gotchas

1. **`allowed-tools` format mismatch.** Claude Code uses patterns like `Bash(npx agent-browser:*)`. Tank stores these as-is and uses them as a signal for fork mode, but doesn't filter tools by these patterns. Fork sub-agents get all tools minus the global disallowed set.

2. **YAML comma-separated strings.** `allowed-tools: foo, bar` is parsed by YAML as a single string, not a list. The parser handles this by splitting on commas. Use YAML list syntax `[foo, bar]` for clarity.

3. **`.review` file and content hash.** The `.review` file is excluded from the content hash computation. If you modify a skill after review, the hash won't match and the skill is disabled until re-reviewed. Delete `.review` to force re-review.

4. **Inline mode relies on LLM compliance.** The skill instructions are returned as a tool result. The LLM should follow them, but there's no enforcement — it's a prompt-level directive. Fork mode is more reliable for complex skills.

5. **Sandbox blocks socket creation.** Tools like `agent-browser` that create Unix sockets need their socket directory added as an `rw` mount in the sandbox config. The default sandbox mounts `~` as read-only.

6. **Skill fork uses AgentRunner.** Skill fork mode creates a dynamic `AgentDefinition` and runs it through `AgentRunner.run_agent()`. This means skill sub-agents get the same approval, UI streaming, and lifecycle management as regular sub-agents. The `AgentRunner` is wired into `UseSkillTool` via `ToolManager.set_agent_runner()`.

7. **Skill preloading in agents.** Agent definitions can specify `skills: [skill-name]` to preload skill instructions into the agent's initial context. This is defined in the agent definition frontmatter but not yet implemented in `AgentRunner` — it's a future enhancement.
