# Design: Agent Orchestration Redesign

## Status

Phase 1 implemented — 2026-04-06. Single agent, no router. See git history for the migration.
Phase 2 implemented — 2026-04-06. Orchestrator + Workers. Workers are tools on the agent (`WorkerTool`). Enable by adding a `workers:` section under `agents:` in config.yaml.

## Problem

Tank's current multi-agent system uses a **horizontal split** — four agents (chat, search, task, code) that all do the same job (answer the user) with different tool subsets. This causes several problems:

1. **Routing failures.** "Check disk usage of my download folder" doesn't match any code-agent keywords, the LLM classifier doesn't reliably map it to "code execution," so it falls to the chat agent — which has all tools but a generic prompt. The user's request goes unanswered or gets routed to web search.

2. **Stale tool names.** Tools were renamed (`sandbox_exec` → `run_command`, etc.) but config and code references weren't updated. The code agent's `tool_filter` matched zero real tools. The approval policy's hardcoded set didn't match real tool names, so sandbox tools bypassed approval gates entirely. (Fixed in the same session that produced this document.)

3. **Tool walls.** If the user says "search for how to check disk usage, then run the command," no single specialized agent can do both. Only the chat agent can, but it has the weakest prompt.

4. **Extra latency.** The slow-path router makes an LLM call (500ms–2s) just to classify intent before the actual agent starts. For a voice assistant, this is noticeable.

5. **Minimal differentiation.** All four agents are `ChatAgent` subclasses. The only differences are a system prompt and a `tool_filter`. No different reasoning logic, execution strategy, or output handling.

## Current Architecture

```
User message
  → Router (fast-path: keyword regex, slow-path: LLM classification)
  → One of:
      chat:   ALL tools + generic prompt        (default)
      search: web_search, web_scraper           + "cite sources" prompt
      task:   calculate, get_time, get_weather  + "show your work" prompt
      code:   run_command, persistent_shell, manage_process + "explain before running" prompt
  → Response streamed to TTS
```

### What works

- `AgentGraph` loop with streaming `AgentOutput` — clean, low-overhead
- `AgentState` with shared message history across handoffs
- Approval gates integrated into the agent loop
- The `Agent` ABC and `AgentOutput` protocol are well-designed

### What doesn't work

- Router is a lossy, latency-adding decision point
- Tool filtering creates artificial walls between capabilities
- Specialized prompts add ~5 lines of guidance each — not worth the routing overhead
- Agents cannot collaborate, review each other, or work in parallel
- No way for an agent to delegate a subtask and stay responsive to the user

## Industry Survey

### OpenAI Agents SDK

Two patterns:

- **Handoffs (decentralized):** Agent declares `handoffs=[agent_b]`. When the LLM decides to hand off, the full conversation transfers to the target. Peer-to-peer, no hierarchy.
- **Agent-as-tool (centralized):** Orchestrator uses `agent.as_tool()` to invoke specialists. Orchestrator retains control, specialists return results. This is the pattern most relevant to Tank.

Also supports deterministic code-based orchestration: structured outputs for classification, chaining, evaluator loops (`while` loop with critic), and parallel execution via `asyncio.gather`.

Philosophy: very few primitives (Agent, Handoff, Tool, Guardrail, Runner). Multi-agent is just agents calling other agents.

### Anthropic — "Building Effective Agents" (Dec 2024)

Explicitly skeptical of multi-agent. Recommended escalation path:

```
1. Single LLM call with good prompt          ← start here
2. Prompt chaining (A → B → C)
3. Routing (classify → specialized prompt)    ← Tank is here
4. Parallelization (multiple calls, aggregate)
5. Orchestrator-workers                       ← proposed target
6. Evaluator-optimizer (generate + critique loop)
7. Full multi-agent                           ← only if 1–6 fail
```

Key quote (paraphrased): "Don't build a multi-agent system when a single agent with good tools will do. The complexity of agent-to-agent communication rarely pays off unless the task genuinely requires different expertise domains."

Their **orchestrator-workers** pattern: a central LLM dynamically breaks down tasks and delegates to worker LLM calls. Workers don't talk to each other — the orchestrator passes context down and collects results up.

Their **evaluator-optimizer** pattern: one LLM generates, another evaluates, loop until quality threshold met. This is the review/verification pattern.

### LangGraph

Most architecturally flexible. Models everything as a state graph.

- **Supervisor:** Supervisor agent invokes workers as tools, retains control, decides next steps.
- **Swarm:** Agents hand off to each other via `create_handoff_tool()`. No central coordinator.
- **Hierarchical:** Supervisors managing other supervisors. Enables organizational structures.
- **Network:** Any agent can route to any other. No hierarchy.

Agents communicate via **shared state** (`TypedDict` with reducers for concurrent updates). This is LangGraph's distinguishing feature — explicit, typed state that flows through the graph.

### Google ADK

Three structural composition primitives:

- **SequentialAgent:** A → B → C pipeline. Output of each step flows via shared session state with `output_key`.
- **ParallelAgent:** Fan-out/gather. Multiple agents run concurrently, write to distinct state keys, a subsequent agent synthesizes.
- **LoopAgent:** Iterative refinement. Repeat [worker → reviewer] until condition met.

Communication is via shared session state. Agent A writes to `state["analysis"]`, Agent B reads it. Clean, explicit data flow.

### AutoGen (Microsoft)

Core insight: agents collaborate by talking in a shared group chat.

- **RoundRobinGroupChat:** Agents take turns. Writer → Critic → Writer → Critic until "APPROVE." Built-in review loop.
- **SelectorGroupChat:** LLM picks who speaks next based on conversation context. Dynamic routing without a separate router.
- **Swarm:** Explicit handoffs via `HandoffMessage`. Agent decides locally whether to handle or transfer.
- **MagenticOneGroupChat:** Generalist multi-agent with orchestrator (see below).

### Magentic-One (Microsoft)

Most sophisticated orchestrator pattern. The Orchestrator maintains a **ledger** — a structured plan that tracks:

- Task breakdown into subtasks
- Current progress and which subtask is active
- Which specialist agent to call next
- What's been tried and failed (for replanning)

The Orchestrator doesn't do work itself. It plans, delegates to specialists (WebSurfer, FileSurfer, Coder, ComputerTerminal), monitors results, and replans when things go wrong.

This is the closest match to the "chat agent talks to user, other agents do the work" idea.

## When Multi-Agent Beats Single-Agent

Based on the survey, multi-agent genuinely helps in these scenarios:

| Scenario | Why |
|----------|-----|
| Long-running tasks | Orchestrator reports progress while workers execute |
| Review / verification | Separate critic catches errors the generator is blind to |
| Parallel information gathering | Fan-out to multiple sources simultaneously |
| Different LLM models per role | Cheap model for routing, expensive model for reasoning |
| Separation of concerns | User-facing agent stays responsive while background agents work |
| Complex multi-step workflows | Planner breaks down, workers execute, orchestrator synthesizes |

Multi-agent does NOT help for:

| Scenario | Why not |
|----------|---------|
| Simple tool selection | A good system prompt achieves the same focus |
| Tasks that fit in one LLM turn | Overhead of routing exceeds benefit |
| Same LLM with different tool subsets | This is Tank's current design — the "agents" add no value |

## Proposed Design

### Phase 1: Simplify to Single Agent (Short-term)

Merge the four agents into one. This is Anthropic's level 1–2 and eliminates the routing problem entirely.

```
User message
  → ChatAgent (ALL tools, comprehensive system prompt)
  → Response streamed to TTS
```

Changes:
- Remove the Router and its LLM classification call (saves 500ms–2s per turn)
- Merge the 4 specialized prompts into the main `system_prompt.txt` (add ~15 lines of guidance)
- Remove `agents` and `router` sections from `config.yaml`
- Keep the agent classes in the codebase for Phase 2
- `AgentGraph` becomes a pass-through (single agent, no handoffs)

Benefits:
- Zero routing latency
- No tool walls — every request can use any tool
- No misclassification — the LLM decides which tools to call naturally
- Simpler debugging — one agent, one prompt, one conversation

Risk: The system prompt grows larger. Mitigation: the current specialized prompts are 5–10 lines each. Merging them adds ~20 lines to a 55-line prompt. This is well within LLM capacity.

### Phase 2: Orchestrator + Workers (Medium-term)

When Tank needs to handle complex, multi-step, or long-running tasks, evolve to the orchestrator-workers pattern.

```
┌──────────────────────────────────────────────────────────┐
│  Orchestrator (user-facing, always responsive)            │
│                                                           │
│  - Talks to user, streams tokens to TTS                   │
│  - Handles simple tasks directly (weather, time, chat)    │
│  - Delegates complex tasks to workers (as tools)          │
│  - Asks for approval on behalf of workers                 │
│  - Synthesizes worker results into voice-friendly output  │
│  - Reports progress: "Let me check that for you..."       │
│                                                           │
│  Tools: calculate, get_time, get_weather,                 │
│         delegate_to_code_worker,                          │
│         delegate_to_research_worker                       │
├──────────────────────────────────────────────────────────┤
│  Workers (background, return results to orchestrator)     │
│                                                           │
│  CodeWorker                                               │
│    Tools: run_command, persistent_shell, manage_process,  │
│           file_read, file_write, file_delete, file_list   │
│    Prompt: "Execute commands, return structured results"  │
│                                                           │
│  ResearchWorker                                           │
│    Tools: web_search, web_scraper                         │
│    Prompt: "Search, extract, summarize with sources"      │
│                                                           │
│  (Future workers as needed)                               │
└──────────────────────────────────────────────────────────┘
```

Key design decisions:

**Workers are tools on the orchestrator** (OpenAI's `agent.as_tool()` pattern). The orchestrator's LLM decides when to delegate — no separate router. This is a single tool call from the orchestrator's perspective:

```python
# Conceptual — orchestrator sees workers as tools
tools = [
    calculate, get_time, get_weather,
    code_worker.as_tool(
        name="run_on_machine",
        description="Run shell commands or file operations on the user's machine. "
                    "Use for: disk usage, file search, system info, code execution, "
                    "package management, and any other shell task.",
    ),
    research_worker.as_tool(
        name="search_web",
        description="Search the web and extract information from pages. "
                    "Use for: current events, documentation, product info, "
                    "anything requiring up-to-date web knowledge.",
    ),
]
```

**Workers don't talk to the user.** They return structured results to the orchestrator, which synthesizes a voice-friendly response. This keeps the user-facing conversation coherent.

**Workers can run concurrently.** "Check disk usage and find cleanup tools" fans out to CodeWorker + ResearchWorker in parallel. The orchestrator waits for both, then synthesizes.

**Approval stays in the orchestrator.** Workers request approval through the orchestrator, which relays to the user. The user sees "Tank wants to run `du -sh ~/Downloads` — approve?" not "CodeWorker wants to..."

Implementation approach:

1. Create a `WorkerAgent` base class that wraps an agent as a callable tool
2. Workers use the existing `ChatAgent` with a focused prompt and tool filter
3. The orchestrator is a `ChatAgent` with worker tools added to its tool list
4. Workers return structured results (not streamed tokens) to the orchestrator
5. `AgentGraph` is not needed — the orchestrator handles everything via tool calls

### Phase 3: Review and Verification Loops (Long-term)

Add the evaluator-optimizer pattern for high-stakes tasks.

```
Orchestrator
  → CodeWorker produces result
  → ReviewerWorker checks result (different prompt, same tools for verification)
  → If issues found → CodeWorker retries with feedback
  → If approved → Orchestrator reports to user
```

This is AutoGen's `RoundRobinGroupChat` pattern or Google ADK's `LoopAgent`. Useful for:

- File modifications (reviewer checks the diff before confirming)
- Complex shell commands (reviewer validates the command is safe)
- Multi-step tasks (reviewer checks each step's output before proceeding)

Implementation: a `ReviewLoop` utility that takes a worker and a reviewer, runs them in alternation, and returns when the reviewer approves or max iterations reached.

### Phase 4: Parallel Fan-Out (Long-term)

For tasks that benefit from multiple perspectives or data sources:

```
Orchestrator
  → ParallelFanOut([
      ResearchWorker("search for X on Google"),
      ResearchWorker("search for X on Stack Overflow"),
      CodeWorker("check local docs for X"),
    ])
  → Orchestrator synthesizes all results
```

This is Google ADK's `ParallelAgent` pattern. Implementation: `asyncio.gather` over multiple worker invocations, collect results, pass to orchestrator for synthesis.

## Migration Path

```
Phase 1 (short-term):  Single agent, no router
  ↓                     Eliminates routing bugs, reduces latency
  ↓                     Low risk, high immediate value
Phase 2 (medium-term): Orchestrator + workers
  ↓                     Enables delegation, progress reporting, parallel work
  ↓                     Moderate complexity, high value for complex tasks
Phase 3 (long-term):   Review loops
  ↓                     Enables verification for high-stakes operations
  ↓                     Incremental addition, low risk
Phase 4 (long-term):   Parallel fan-out
                        Enables multi-source research, faster complex tasks
                        Incremental addition, low risk
```

Each phase is independently valuable and backward-compatible. Phase 1 can ship immediately. Phases 2–4 build on each other but don't require all-or-nothing adoption.

## Appendix: Current Code Inventory

Files involved in the current agent system:

| File | Purpose | Phase 1 impact |
|------|---------|----------------|
| `agents/base.py` | Agent ABC, AgentState, AgentOutput | Keep as-is |
| `agents/graph.py` | AgentGraph orchestrator loop | Simplify to single-agent pass-through |
| `agents/router.py` | Intent classifier (keyword + LLM) | Remove |
| `agents/factory.py` | Agent type → instance | Simplify |
| `agents/chat_agent.py` | Base conversational agent | Keep, becomes the only agent |
| `agents/code_agent.py` | Code execution agent | Remove (merge prompt into system_prompt.txt) |
| `agents/search_agent.py` | Web search agent | Remove (merge prompt into system_prompt.txt) |
| `agents/task_agent.py` | Task agent | Remove (merge prompt into system_prompt.txt) |
| `agents/approval.py` | Approval gates | Keep as-is |
| `prompts/system_prompt.txt` | Main system prompt | Expand with merged guidance |
| `prompts/code_prompt.txt` | Code agent prompt | Remove (merge) |
| `prompts/search_prompt.txt` | Search agent prompt | Remove (merge) |
| `prompts/task_prompt.txt` | Task agent prompt | Remove (merge) |
| `config.yaml` (agents section) | Agent definitions | Remove |
| `config.yaml` (router section) | Router config | Remove |

## Appendix: Bugs Fixed in This Session

During the investigation that led to this design document, the following bugs were discovered and fixed:

1. **Stale tool names in config** — `config.yaml` referenced `sandbox_exec`, `sandbox_bash`, `sandbox_process` but actual tool names are `run_command`, `persistent_shell`, `manage_process`. Code agent had zero working tools.

2. **Stale tool names in approval policy** — `HARDCODED_REQUIRE_APPROVAL` in `approval.py` checked for old names. Sandbox tools bypassed approval gates entirely. (Security fix.)

3. **Stale tool names in code agent defaults** — `_DEFAULT_TOOLS` in `code_agent.py` used old names.

4. **System prompt didn't guide `run_command` usage** — The TOOL USAGE section only mentioned "calculations, weather, time, and web searches." Added guidance to use `run_command` for system queries.

5. **Tool description too narrow** — `run_command` description only listed dev-oriented examples (ls, grep, python, git). Added system diagnostics (du, df, ps, top) and broadened to "any shell command."

6. **Stale names in tests** — 8 test files referenced old tool names. All updated, 1050 tests passing.

7. **Stale names in docs** — ARCHITECTURE.md, DEVELOPMENT.md, TESTING.md all referenced old tool names. Updated.
