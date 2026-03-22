"""Agent factory — creates agents from config dictionaries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import Agent
from .chat_agent import ChatAgent
from .code_agent import CodeAgent
from .search_agent import SearchAgent
from .task_agent import TaskAgent

if TYPE_CHECKING:
    from ..llm.llm import LLM
    from ..tools.manager import ToolManager
    from .approval import ApprovalManager, ApprovalPolicy

logger = logging.getLogger(__name__)

# Registry of agent type → class
_AGENT_TYPES: dict[str, type[ChatAgent]] = {
    "chat": ChatAgent,
    "search": SearchAgent,
    "task": TaskAgent,
    "code": CodeAgent,
}


def create_agent(
    name: str,
    agent_type: str,
    llm: LLM,
    tool_manager: ToolManager | None = None,
    config: dict[str, Any] | None = None,
    approval_manager: ApprovalManager | None = None,
    approval_policy: ApprovalPolicy | None = None,
    session_id: str = "",
) -> Agent:
    """Create an agent instance from a type string and config.

    Args:
        name: Agent name (used as key in AgentGraph).
        agent_type: One of "chat", "search", "task", "code".
        llm: LLM instance for this agent.
        tool_manager: Shared ToolManager (agents filter tools internally).
        config: Optional dict with keys: ``tools`` (list[str]), ``system_prompt`` (str).
        approval_manager: Optional ApprovalManager for tool approval gates.
        approval_policy: Optional ApprovalPolicy for determining which tools need approval.
        session_id: Session ID for approval tracking.

    Returns:
        Agent instance.

    Raises:
        ValueError: If agent_type is unknown.
    """
    cls = _AGENT_TYPES.get(agent_type)
    if cls is None:
        raise ValueError(
            f"Unknown agent type {agent_type!r}. "
            f"Available: {sorted(_AGENT_TYPES.keys())}"
        )

    cfg = config or {}
    kwargs: dict[str, Any] = {
        "llm": llm,
        "tool_manager": tool_manager,
    }

    if "tools" in cfg:
        kwargs["tool_filter"] = cfg["tools"]
    if "system_prompt" in cfg:
        kwargs["system_prompt"] = cfg["system_prompt"]

    # Pass approval params through to all ChatAgent subclasses
    if approval_manager is not None:
        kwargs["approval_manager"] = approval_manager
    if approval_policy is not None:
        kwargs["approval_policy"] = approval_policy
    if session_id:
        kwargs["session_id"] = session_id

    # For the base ChatAgent, we need to pass the name explicitly
    if cls is ChatAgent:
        agent = ChatAgent(name=name, **kwargs)
    else:
        agent = cls(**kwargs)
        # Override name if config specifies a different one
        agent.name = name

    logger.info("Created agent %r (type=%s)", name, agent_type)
    return agent
