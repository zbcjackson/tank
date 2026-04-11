# Agent Orchestration Design

## Part 1: Claude Code's Agent Architecture — Key Findings

### Core Principle: Agents Are Just Recursive Query Calls

Claude Code has ONE execution engine: `query()`. The main conversation runs through it. Sub-agents also run through it. The `Agent` tool is just another tool that calls `query()` recursively with different parameters.

```
query(systemPrompt, tools, messages)
  ├── LLM generates response
  ├── Tool calls detected
  │     ├── Bash, Read, Edit, etc. → execute directly
  │     ├── Skill tool → load instructions, inject as messages
  │     └── Agent tool → runAgent() → query() recursively
  │           Same engine, different params:
  │           - Own system prompt (from agent definition)
  │           - Own tool set (filtered from parent)
  │           - Own conversation (fresh or forked from parent)
  │           - Own agent ID (for tracking/cleanup)
  └── Tool results → append to messages → next LLM turn
```

### Agent Definitions: Markdown Files with Frontmatter

```yaml
# .claude/agents/coder.md
---
agentType: coder
description: "Code execution and file operations"
disallowedTools: [Agent]           # prevent recursive spawning
skills: [commit, review-pr]        # preload these skills
permissionMode: acceptEdits        # permission level
background: false                  # foreground by default
maxTurns: 25                       # limit iterations
model: sonnet                      # optional model override
---

System prompt content here as markdown.
```

Built-in agents: `general-purpose` (all tools), `Explore` (read-only), `Plan` (read-only), `verification` (background), `claude-code-guide` (docs lookup).

### Tool Filtering: Disallowed, Not Allowed

Claude Code starts with ALL tools and removes what's dangerous for each agent type:

```
ALL_AGENT_DISALLOWED_TOOLS (for all sub-agents):
  - Agent (no recursive spawning, unless special user type)
  - AskUserQuestion (sub-agents can't prompt user)
  - ExitPlanMode
  - EnterPlanMode
  - TaskOutput, TaskStop

Per-agent disallowedTools (from definition):
  - Explore agent: + Edit, Write, NotebookEdit (read-only)
  - Plan agent: + Edit, Write, NotebookEdit (read-only)
```

### Agent-to-Agent Communication: SendMessageTool

Claude Code has a `SendMessage` tool for "in-process teammates" (swarm mode):
- Agents write to each other's mailboxes (file-based)
- Supports: direct message, broadcast, request/response patterns
- Only available to "in-process teammates", not regular sub-agents
- Used in team/swarm scenarios where multiple agents collaborate

### Background Agents

- Defined via `background: true` in agent definition or `run_in_background: true` parameter
- Get their own AbortController (independent lifecycle)
- Can't show UI permission prompts → must be pre-approved
- Parent gets notified when background agent completes
- Used for: verification, long-running tasks, parallel work

### Skill Preloading in Agents

```typescript
// runAgent.ts line 577-645
const skillsToPreload = agentDefinition.skills ?? []
for (const skill of validSkills) {
  const content = await skill.getPromptForCommand('', toolUseContext)
  initialMessages.push(createUserMessage({
    content: [metadata, ...content],
    isMeta: true,
  }))
}
```

Skills are loaded as user messages injected into the agent's initial conversation. The agent "knows" the skill's workflow from the start — no need to call `use_skill`.

### Context Forking

Two modes in Claude Code:
1. **Normal sub-agent**: Fresh conversation (system prompt + task only). No parent history.
2. **Fork sub-agent**: Inherits parent's full conversation history + system prompt. Used for prompt cache sharing.

### Depth/Limits

- `Agent` tool is in `ALL_AGENT_DISALLOWED_TOOLS` by default → sub-agents can't spawn sub-agents (unless special override)
- `maxTurns` per agent (default varies by type)
- No explicit total agent count limit, but depth is effectively 1 (main → sub-agent, no deeper)

---

## Part 2: Tank's Proposed Agent Architecture

### Design Goals

1. **One execution method** — `run_agent()` is the single way to run any agent. Brain uses it for the main agent. Sub-agents use it recursively. Skills use it for fork mode.
2. **Agents defined as markdown** — `.tank/agents/*.md` with YAML frontmatter, same format as skills.
3. **No orchestrator/worker terminology** — just "agents" with different capabilities.
4. **Inline and fork modes** — agents can run in the parent's conversation or in an isolated context.
5. **Consistent creation** — all agents go through the same `run_agent()` path, ensuring approval, UI updates, and lifecycle management.
6. **Skill preloading** — agents can have skills baked into their context.
7. **Background agents** — for parallel or long-running work.
8. **Depth and count limits** — prevent runaway agent spawning.

### Architecture

```
Brain.process(user_input)
  └── run_agent(main_agent, messages=conversation_history)
        ├── LLM generates response
        ├── Tool calls:
        │     ├── Regular tools → execute directly
        │     ├── use_skill → load skill, run_agent(skill_agent) in fork mode
        │     └── agent tool → run_agent(sub_agent) in fork mode
        └── Tool results → next LLM turn

run_agent(agent_def, messages, mode="fork"):
  1. Load agent definition (system prompt, tool config)
  2. Resolve tools (all tools minus disallowed)
  3. Preload skills (inject as initial messages)
  4. Set up approval (inherit from parent)
  5. Set up UI streaming (post to Bus)
  6. Run LLM chat loop with tools
  7. Return result + cleanup
```

### Inline vs Fork Mode

**Inline mode**: The agent runs within the parent's conversation context. The agent's instructions are injected as messages in the parent's `chat_stream` loop. The parent LLM follows them directly. Good for simple skills that don't need their own tool set.

When to use inline:
- Prompt-only skills (no `allowed-tools`)
- Simple instructions the main agent can follow directly
- When you want the result to be part of the main conversation flow

**Fork mode**: The agent gets its own conversation, system prompt, and tool set. It runs `run_agent()` recursively. The result is returned to the parent as a tool result. Good for complex tasks that need specialized tools or isolation.

When to use fork:
- Skills that need execution tools (`allowed-tools` is non-empty)
- Agent tool invocations (always fork)
- Background tasks
- When isolation is needed (don't pollute main conversation)

**How the main agent decides**: The system prompt guides the LLM:
```
You have access to all tools directly. For simple tasks, handle them yourself.
Use the `agent` tool when:
- The task is complex and benefits from a specialist's system prompt
- You want parallel execution (multiple agent calls in one turn)
- The task needs isolation (e.g., experimental code changes)
- A specific agent type has skills/knowledge you don't have
```

### Agent Definition Format

```
.tank/agents/coder.md
```

```yaml
---
name: coder
description: "Execute code, manage files, run shell commands"
disallowed-tools: []
skills: []
background: false
max-turns: 25
---

You are a coding agent. Execute commands and modify files to complete tasks.
Always verify your changes work before reporting completion.
```

```
.tank/agents/researcher.md
```

```yaml
---
name: researcher
description: "Search the web and gather information"
disallowed-tools: [file_write, file_delete, run_command, persistent_shell]
skills: []
background: false
max-turns: 15
---

You are a research agent. Search the web, read pages, and synthesize information.
Do not modify files or run commands.
```

```
.tank/agents/tasker.md
```

```yaml
---
name: tasker
description: "Plan and coordinate multi-step tasks, break down complex work"
disallowed-tools: [file_write, file_delete]
skills: []
background: false
max-turns: 20
---

You are a task planning agent. Break down complex requests into steps,
coordinate execution, and track progress. You can read files and search
the web to understand context, but delegate actual code changes to the
coder agent.
```

### Tasker vs Coder

The **tasker** agent focuses on planning and coordination — breaking down complex requests, understanding requirements, reading code for context. It can read files and search but can't write code.

The **coder** agent focuses on execution — writing code, running commands, modifying files. It gets the specific task from the tasker or directly from the user.

This separation is useful when:
- A complex request needs planning before coding
- The user wants to review the plan before execution
- Multiple coding tasks need coordination

But it's optional — the main agent can call the coder directly for simple tasks.

### The `agent` Tool

```python
class AgentTool(BaseTool):
    """Spawn a sub-agent to handle a task."""

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="agent",
            description="Launch a sub-agent for complex tasks. Available agents listed in system prompt.",
            parameters=[
                ToolParameter(name="prompt", type="string",
                    description="Task description for the agent", required=True),
                ToolParameter(name="subagent_type", type="string",
                    description="Agent type (e.g. 'coder', 'researcher', 'tasker')",
                    required=False),
                ToolParameter(name="description", type="string",
                    description="Short description (3-5 words) for tracking",
                    required=False),
                ToolParameter(name="run_in_background", type="boolean",
                    description="Run in background for parallel execution",
                    required=False),
            ],
        )

    async def execute(self, **kwargs) -> dict:
        # 1. Resolve agent definition
        # 2. Call run_agent() in fork mode
        # 3. Return result
```

### The `run_agent()` Function

This is the core execution method. Everything goes through it.

```python
async def run_agent(
    agent_def: AgentDefinition,
    messages: list[dict],           # Initial messages (task or full conversation)
    mode: str = "fork",             # "inline" or "fork"
    tool_manager: ToolManager,
    llm: LLM,
    bus: Bus,
    approval_manager: ApprovalManager,
    approval_policy: ToolApprovalPolicy,
    parent_agent_id: str | None = None,
    background: bool = False,
    max_turns: int | None = None,
) -> AsyncIterator[AgentOutput]:
    """
    The single execution method for all agents.

    1. Resolve tools: all tools minus agent_def.disallowed_tools
       minus global disallowed (agent tool itself, unless allowed)
    2. Preload skills: inject skill instructions as initial messages
    3. Create ChatAgent with:
       - system_prompt from agent_def
       - resolved tools (via exclude_tools)
       - approval_manager + approval_policy (inherited)
    4. Stream outputs through Bus (UI updates)
    5. Enforce max_turns limit
    6. Track agent lifecycle (ID, depth, cleanup)
    """
```

### How Brain Uses run_agent()

```python
class Brain:
    async def _process_via_agents(self, msg_id, language):
        # The main agent is just another agent definition
        main_agent_def = self._load_main_agent_def()

        async for output in run_agent(
            agent_def=main_agent_def,
            messages=self._conversation_history,
            mode="inline",  # Main agent runs inline (uses existing conversation)
            tool_manager=self._tool_manager,
            llm=self._llm,
            bus=self._bus,
            approval_manager=self._approval_manager,
            approval_policy=self._approval_policy,
        ):
            # Stream to UI (same as current code)
            self._bus.post(...)
```

### How Skills Use run_agent()

```python
class UseSkillTool(BaseTool):
    async def execute(self, **kwargs):
        result = await self._manager.invoke(skill_name, args)

        if should_fork(result):
            # Create a dynamic agent definition from the skill
            skill_agent_def = AgentDefinition(
                name=f"skill_{skill_name}",
                system_prompt=result["instructions"],
                disallowed_tools={"agent", "use_skill", "list_skills", ...},
                skills=[],  # Skill IS the instructions, no preloading needed
            )

            full_text = ""
            async for output in run_agent(
                agent_def=skill_agent_def,
                messages=[{"role": "user", "content": result["instructions"]}],
                mode="fork",
                ...  # Same params, inherited from parent
            ):
                if output.type == AgentOutputType.TOKEN:
                    full_text += output.content
                # UI updates happen automatically via Bus

            return {"status": "forked", "result": full_text}

        else:
            return self._execute_inline(result)
```

This is the key insight: **skill fork sub-agents are just dynamic agents**. They go through the same `run_agent()` path, getting approval, UI updates, and proper lifecycle management for free.

### Agent Communication

For Tank's current needs, agents communicate through:

1. **Parent → Sub-agent**: Task description as initial message (current pattern)
2. **Sub-agent → Parent**: Final result returned as tool result (current pattern)
3. **Agent → Agent (future)**: SendMessage tool for swarm/team scenarios

For now, fire-and-forget with result is sufficient. SendMessage can be added later for advanced coordination.

### Can Sub-Agents Create Sub-Agents?

By default, NO — the `agent` tool is in the global disallowed list for sub-agents. This prevents infinite recursion.

Exception: specific agent types can opt-in by NOT listing `agent` in their `disallowed-tools`. This should be rare and depth-limited.

### Depth and Count Limits

```python
# Global limits
MAX_AGENT_DEPTH = 3          # main → sub → sub-sub (rare)
MAX_CONCURRENT_AGENTS = 5    # parallel background agents
MAX_TOTAL_AGENTS = 10        # total agents per conversation turn

# Per-agent limits
default max_turns = 25       # iterations per agent
```

Enforcement:
- `run_agent()` tracks depth via `parent_agent_id` chain
- Refuses to spawn if depth >= MAX_AGENT_DEPTH
- Background agent count tracked globally
- Each agent has its own max_turns (from definition or default)

### Background Agents

```yaml
# .tank/agents/verifier.md
---
name: verifier
description: "Verify code changes are correct"
disallowed-tools: [file_write, file_delete, agent]
background: true
max-turns: 10
---
```

Background agents:
- Run in parallel with the main conversation
- Can't show UI approval prompts → must use auto-approve or pre-approved tools
- Post results to Bus when complete
- Parent gets notified via a system message on next turn
- Useful for: verification, monitoring, long-running analysis

### Skill Preloading

Agent definitions can specify skills to preload:

```yaml
---
name: browser-automation
description: "Automate browser tasks"
skills: [agent-browser]
---
```

When `run_agent()` starts this agent:
1. Load `agent-browser` skill from registry
2. Inject skill instructions as initial user messages
3. The agent "knows" the browser automation workflow from the start

**Skill fork sub-agents** are a special case: they're dynamic agents where the skill IS the system prompt. No preloading needed — the skill instructions are the agent's entire purpose.

But you could also create a persistent agent type that preloads multiple skills:

```yaml
---
name: web-specialist
description: "Web scraping and browser automation"
skills: [agent-browser, web-scraper-tips]
disallowed-tools: [file_write, file_delete]
---

You are a web specialist. Use the preloaded skills to automate browser
tasks and scrape web content.
```

### Parallel Execution (Replacing Current Workers Pattern)

Current pattern:
```
Orchestrator calls delegate_to_coder AND delegate_to_researcher in same turn
→ LLM.chat_stream() runs them concurrently via asyncio.gather
```

New pattern:
```
Main agent calls agent(type="coder", task="...") AND agent(type="researcher", task="...")
→ LLM.chat_stream() runs them concurrently (same mechanism)
```

The parallel execution mechanism stays the same — `LLM.chat_stream()` already detects multiple concurrent-safe tool calls and runs them in parallel. The `agent` tool just needs to be marked as concurrent-safe when `run_in_background=true`.

### Main Agent Tool Access

The main agent has ALL tools. The system prompt guides when to delegate:

```
You have direct access to all tools including file operations, shell commands,
web search, and browser automation.

For simple tasks, handle them directly — don't spawn agents unnecessarily.

Use the `agent` tool when:
- The task is complex and would benefit from a specialist's focused context
- You want to run multiple tasks in parallel (call agent multiple times in one response)
- The task needs isolation (experimental changes that might need rollback)
- A specific agent has preloaded skills relevant to the task

Available agents:
- coder: Code execution, file operations, shell commands
- researcher: Web search and information gathering
- tasker: Task planning and coordination
- verifier: Code verification (background)
```

### Migration from Current Design

1. `run_agent()` function replaces both `AgentGraph.run()` and `UseSkillTool._execute_fork()`
2. `.tank/agents/` directory replaces `config.yaml workers:` section
3. `agent` tool replaces `delegate_to_*` WorkerTools
4. Main agent gets all tools (no more `exclude_tools` for worker-owned tools)
5. Skill fork uses `run_agent()` instead of raw ChatAgent creation
6. Approval and UI streaming are built into `run_agent()`, not bolted on

### Summary: What This Design Solves

| Problem | Solution |
|---------|----------|
| Fork sub-agent has no approval | `run_agent()` always includes approval |
| Fork sub-agent has no UI updates | `run_agent()` always streams to Bus |
| Workers lose skill context | Skill preloading in agent definitions |
| Exclusive tool ownership | Main agent has all tools, sub-agents use disallowed list |
| Skill fork bypasses orchestration | Skill fork uses `run_agent()` |
| No recursive spawning | Depth-limited via `run_agent()` |
| Inconsistent agent creation | Single `run_agent()` entry point |
| No background agents | `background: true` in agent definition |
| No tasker/planner separation | Separate agent definitions |
| Naming confusion (orchestrator/worker) | Just "agents" |
