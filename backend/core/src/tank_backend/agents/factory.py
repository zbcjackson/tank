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
specialist using the appropriate delegate_to_* tool.

When delegating:
- Provide a clear, specific task description
- The specialist will execute the task and return results
- Synthesize the specialist's results into a concise, conversational response
- Do NOT repeat the specialist's raw output verbatim — summarize it naturally

{worker_descriptions}"""


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

    Args:
        name: Agent name (used as key in AgentGraph).
        llm: LLM instance.
        tool_manager: Shared ToolManager (WorkerTools are registered here).
        config: Optional dict with keys: ``llm_profile``, ``system_prompt``,
                ``workers`` (dict of worker configs).
        approval_manager: Optional ApprovalManager for tool approval gates.
        approval_policy: Optional ToolApprovalPolicy for tool approval.
        session_id: Session ID for approval tracking.
        bus: Optional Bus for forwarding worker approval requests to the UI.

    Returns:
        ChatAgent instance (with or without worker delegation).
    """
    cfg = config or {}
    workers_cfg = cfg.get("workers", {})

    worker_owned_tools: set[str] = set()
    worker_lines: list[str] = []

    for worker_name, worker_cfg in workers_cfg.items():
        tool_name = f"delegate_to_{worker_name}"
        worker_tools = worker_cfg.get("tools", [])
        worker_owned_tools.update(worker_tools)

        inner_agent = ChatAgent(
            name=f"worker_{worker_name}",
            llm=llm,
            tool_manager=tool_manager,
            system_prompt=worker_cfg.get("system_prompt"),
            tool_filter=worker_tools or None,
            approval_manager=approval_manager,
            approval_policy=approval_policy,
            session_id=session_id,
        )

        worker_tool = WorkerTool(
            name=tool_name,
            description=worker_cfg.get("description", f"Delegate tasks to {worker_name}"),
            worker_agent=inner_agent,
            timeout=float(worker_cfg.get("timeout", 120)),
        )

        # Register in ToolManager so it's visible and executable like any other tool
        if tool_manager is not None:
            tool_manager.register_tool(worker_tool)

        worker_lines.append(f"- {tool_name}: {worker_cfg.get('description', '')}")

        logger.info(
            "Worker %r: tools=%s, timeout=%.0fs",
            worker_name, worker_tools, worker_tool._timeout,
        )

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
