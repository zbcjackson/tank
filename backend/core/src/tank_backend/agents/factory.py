"""Agent factory — creates a ChatAgent from the ``agents:`` config section."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .chat_agent import ChatAgent
from .worker_tool import WorkerTool

if TYPE_CHECKING:
    from ..llm.llm import LLM
    from ..tools.manager import ToolManager
    from .approval import ApprovalManager, ToolApprovalPolicy

logger = logging.getLogger(__name__)

_DEFAULT_ORCHESTRATOR_PROMPT = """\
You are an orchestrator. For simple tasks (weather, time, calculations, casual chat), \
handle them directly using the available tools. For complex tasks that require \
multiple steps, code execution, file operations, or web research, delegate to a \
specialist using the appropriate tool.

Delegation strategy:
- delegate_to_*: Use for straightforward tasks that need a single specialist
- VERIFICATION: After delegate_to_coder completes a task that modifies files or \
produces code, ALWAYS call delegate_to_verifier to check the result. If the verifier \
reports VERDICT: FAIL, fix the issues by calling delegate_to_coder again with the \
feedback, then re-verify. Do NOT report completion to the user until the verifier \
passes or you have exhausted retries
- PARALLEL EXECUTION: When the user's request needs multiple specialists, call \
multiple delegate_to_* tools in the SAME response. They will be executed concurrently. \
For example, if the user asks "search the web for X and check my disk usage", call \
both delegate_to_researcher and delegate_to_coder in a single response — do NOT call \
them one at a time

When delegating:
- Provide a clear, specific task description
- Synthesize the specialist's results into a concise, conversational response
- Do NOT repeat the specialist's raw output verbatim — summarize it naturally

{worker_descriptions}"""

_DEFAULT_VERIFIER_PROMPT = """\
You are a verification specialist. Your job is not to confirm the work is correct — \
it is to try to break it.

You are STRICTLY READ-ONLY. Do NOT modify, create, or delete any files. \
You may only read files and run non-destructive commands to verify output.

=== VERIFICATION STEPS ===
1. Read the files that were created or modified
2. Run the code or command if applicable (use run_command for non-destructive checks)
3. Check for correctness, edge cases, and obvious bugs
4. Verify the output matches what was requested

=== OUTPUT FORMAT (REQUIRED) ===
End your response with exactly one of these lines:

VERDICT: PASS
VERDICT: FAIL

If FAIL, explain what specifically is wrong and how to fix it. \
Be concrete — file paths, line numbers, exact errors."""


def create_agent(
    name: str,
    llm: LLM,
    tool_manager: ToolManager | None = None,
    config: dict[str, Any] | None = None,
    approval_manager: ApprovalManager | None = None,
    approval_policy: ToolApprovalPolicy | None = None,
    session_id: str = "",
) -> ChatAgent:
    """Create a ChatAgent from config.

    If ``config`` contains a ``workers`` section, WorkerTools are registered
    in the ToolManager and worker-owned tools are excluded from the agent's
    view. Otherwise a plain ChatAgent with all tools is returned.

    A ``verifier`` worker is auto-created when a ``coder`` worker exists.
    The verifier is read-only — it can read files and run commands but
    cannot write or delete. The orchestrator calls it after the coder
    finishes to verify the result.

    Args:
        name: Agent name (used as key in AgentGraph).
        llm: LLM instance.
        tool_manager: Shared ToolManager (WorkerTools are registered here).
        config: Optional dict with keys: ``llm_profile``, ``system_prompt``,
                ``workers``.
        approval_manager: Optional ApprovalManager for tool approval gates.
        approval_policy: Optional ToolApprovalPolicy for tool approval.
        session_id: Session ID for approval tracking.

    Returns:
        ChatAgent instance (with or without worker delegation).
    """
    cfg = config or {}
    workers_cfg = cfg.get("workers", {})

    worker_owned_tools: set[str] = set()
    worker_lines: list[str] = []
    inner_agents: dict[str, ChatAgent] = {}
    worker_tools: dict[str, WorkerTool] = {}

    for worker_name, worker_cfg in workers_cfg.items():
        tool_name = f"delegate_to_{worker_name}"
        w_tools = worker_cfg.get("tools", [])
        worker_owned_tools.update(w_tools)

        inner_agent = ChatAgent(
            name=f"worker_{worker_name}",
            llm=llm,
            tool_manager=tool_manager,
            system_prompt=worker_cfg.get("system_prompt"),
            tool_filter=w_tools or None,
            approval_manager=approval_manager,
            approval_policy=approval_policy,
            session_id=session_id,
        )
        inner_agents[worker_name] = inner_agent

        worker_tool = WorkerTool(
            name=tool_name,
            description=worker_cfg.get("description", f"Delegate tasks to {worker_name}"),
            worker_agent=inner_agent,
            timeout=float(worker_cfg.get("timeout", 120)),
        )
        worker_tools[worker_name] = worker_tool

        if tool_manager is not None:
            tool_manager.register_tool(worker_tool)

        worker_lines.append(f"- {tool_name}: {worker_cfg.get('description', '')}")

        logger.info(
            "Worker %r: tools=%s, timeout=%.0fs",
            worker_name, w_tools, worker_tool._timeout,
        )

    # --- Auto-create verifier when coder exists ---
    if "coder" in inner_agents and "verifier" not in workers_cfg:
        verifier_cfg = cfg.get("verifier", {})
        # Read-only tools — can inspect but not modify
        verifier_tools = verifier_cfg.get(
            "tools", ["run_command", "file_read", "file_list"],
        )

        verifier_agent = ChatAgent(
            name="worker_verifier",
            llm=llm,
            tool_manager=tool_manager,
            system_prompt=verifier_cfg.get("system_prompt", _DEFAULT_VERIFIER_PROMPT),
            tool_filter=verifier_tools,
            approval_manager=approval_manager,
            approval_policy=approval_policy,
            session_id=session_id,
        )

        verifier_tool = WorkerTool(
            name="delegate_to_verifier",
            description=(
                "Verify that code or file changes are correct. "
                "Call AFTER delegate_to_coder completes a task that modifies "
                "files or produces code. Returns VERDICT: PASS or VERDICT: FAIL "
                "with specific feedback."
            ),
            worker_agent=verifier_agent,
            timeout=float(verifier_cfg.get("timeout", 120)),
        )

        if tool_manager is not None:
            tool_manager.register_tool(verifier_tool)

        worker_lines.append(
            "- delegate_to_verifier: Verify code/file changes are correct "
            "(call after delegate_to_coder for tasks that modify files)",
        )

        logger.info(
            "Auto-created verifier worker: tools=%s, timeout=%.0fs",
            verifier_tools, verifier_tool._timeout,
        )

    # --- Parallel fan-out ---
    # No longer auto-registered as a tool. The LLM runtime in llm.py
    # detects multiple delegate_to_* calls in the same turn and runs
    # them concurrently via asyncio.gather. This is more natural for
    # the LLM than constructing a JSON array for a special tool.

    # Build system prompt — only inject orchestrator prompt when workers exist
    system_prompt = cfg.get("system_prompt")
    if system_prompt is None and worker_lines:
        worker_desc = "Available specialists:\n" + "\n".join(worker_lines)
        system_prompt = _DEFAULT_ORCHESTRATOR_PROMPT.format(
            worker_descriptions=worker_desc,
        )

    agent = ChatAgent(
        name=name,
        llm=llm,
        tool_manager=tool_manager,
        system_prompt=system_prompt,
        exclude_tools=worker_owned_tools or None,
        approval_manager=approval_manager,
        approval_policy=approval_policy,
        session_id=session_id,
    )

    if workers_cfg:
        logger.info(
            "Created agent %r with %d workers, excluding %d direct tools",
            name, len(workers_cfg), len(worker_owned_tools),
        )
    else:
        logger.info("Created agent %r (no workers)", name)

    return agent
