"""AgentRunner — single execution method for all agents.

Brain uses it for the main agent. The ``agent`` tool uses it for sub-agents.
Skills use it for fork mode. All agents get approval, UI streaming, and
lifecycle management consistently through this one entry point.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from .base import AgentOutput, AgentOutputType, AgentState
from .definition import AgentDefinition
from .llm_agent import LLMAgent

if TYPE_CHECKING:
    from ..llm.llm import LLM
    from ..pipeline.bus import Bus
    from ..tools.manager import ToolManager
    from .approval import PendingToolCallStore, ToolApprovalPolicy

logger = logging.getLogger(__name__)

MAX_AGENT_DEPTH = 3
MAX_CONCURRENT_AGENTS = 5

# Tools that sub-agents should never have (prevent recursion, meta-tools)
GLOBAL_DISALLOWED_FOR_SUBAGENTS: frozenset[str] = frozenset({
    "agent",          # prevent recursive spawning by default
    "list_skills",    # meta — not useful inside a sub-agent
    "create_skill",   # meta
    "install_skill",  # meta
})


class AgentRunner:
    """Unified agent execution engine."""

    def __init__(
        self,
        llm: LLM,
        tool_manager: ToolManager,
        bus: Bus,
        approval_policy: ToolApprovalPolicy,
        pending_store: PendingToolCallStore,
        definitions: dict[str, AgentDefinition],
        resolver: Any = None,
        max_depth: int = MAX_AGENT_DEPTH,
        max_concurrent: int = MAX_CONCURRENT_AGENTS,
        toolsets_config: Any = None,
    ) -> None:
        self._llm = llm
        self._tool_manager = tool_manager
        self._bus = bus
        self._approval_policy = approval_policy
        self._pending_store = pending_store
        self._definitions = definitions
        self._resolver = resolver
        self._max_depth = max_depth
        self._max_concurrent = max_concurrent
        self._active_agents: dict[str, _AgentTracker] = {}
        self._toolsets_config = toolsets_config

        # Create own PromptAssembler for sub-agent prompt building
        from ..prompts.assembler import PromptAssembler

        self._prompt_assembler = PromptAssembler(bus=bus)

    @property
    def definitions(self) -> dict[str, AgentDefinition]:
        return self._definitions

    def get_definition(self, name: str) -> AgentDefinition | None:
        return self._definitions.get(name)

    # ------------------------------------------------------------------
    # The single execution method
    # ------------------------------------------------------------------

    async def run_agent(
        self,
        agent_def: AgentDefinition,
        messages: list[dict[str, Any]],
        parent_agent_id: str | None = None,
        background: bool = False,
        token_budget: int | None = None,
    ) -> AsyncIterator[AgentOutput]:
        """Run an agent to completion, yielding all outputs.

        This is the ONLY way to run an agent. Brain, AgentTool, and
        UseSkillTool all call this method.

        Args:
            agent_def: The agent definition (system prompt, tool config).
            messages: Initial messages (task description or full conversation).
            parent_agent_id: Parent agent ID for depth tracking.
            background: Run without blocking the parent.
            token_budget: Override agent_def.token_budget.
        """
        # --- Depth check ---
        depth = self._get_depth(parent_agent_id)
        if depth >= self._max_depth:
            logger.warning(
                "Agent depth limit reached (%d/%d) for '%s'",
                depth, self._max_depth, agent_def.name,
            )
            yield AgentOutput(
                type=AgentOutputType.TOOL_RESULT,
                content=f"Cannot spawn agent '{agent_def.name}': "
                        f"max depth {self._max_depth} reached.",
                metadata={"status": "error"},
            )
            return

        # --- Concurrent agent check ---
        active_count = sum(
            1 for t in self._active_agents.values() if t.active
        )
        if active_count >= self._max_concurrent:
            logger.warning(
                "Concurrent agent limit reached (%d/%d)",
                active_count, self._max_concurrent,
            )
            yield AgentOutput(
                type=AgentOutputType.TOOL_RESULT,
                content=f"Cannot spawn agent: max concurrent "
                        f"agents ({self._max_concurrent}) reached.",
                metadata={"status": "error"},
            )
            return

        # --- Create agent ---
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        tracker = _AgentTracker(
            agent_id=agent_id,
            agent_name=agent_def.name,
            parent_id=parent_agent_id,
            depth=depth,
        )
        self._active_agents[agent_id] = tracker

        # Resolve tools: all tools minus disallowed, filtered by toolset
        exclude = set(agent_def.disallowed_tools)
        if parent_agent_id is not None:
            # Sub-agents get global disallowed tools
            exclude |= GLOBAL_DISALLOWED_FOR_SUBAGENTS

        # Toolset profile: if specified, compute a tool_filter (allowlist)
        tool_filter: list[str] | None = None
        if agent_def.toolset:
            tool_filter = self._resolve_toolset(agent_def.toolset)

        exclude_tools = exclude or None

        effective_budget = token_budget or agent_def.token_budget

        system_prompt = self._build_sub_agent_prompt(agent_def, messages)

        agent = LLMAgent(
            name=f"agent_{agent_def.name}",
            llm=self._llm,
            tool_manager=self._tool_manager,
            system_prompt=system_prompt,
            tool_filter=tool_filter,
            exclude_tools=exclude_tools,
            approval_policy=self._approval_policy,
            resolver=self._resolver,
            session_id=agent_id,
            pending_store=self._pending_store,
            bus=self._bus,
        )

        state = AgentState(
            messages=list(messages),
            metadata={
                "agent_id": agent_id,
                "agent_name": agent_def.name,
                "parent_agent_id": parent_agent_id,
            },
        )

        logger.info(
            "AgentRunner: starting '%s' (id=%s, depth=%d, token_budget=%d, bg=%s)",
            agent_def.name, agent_id, depth, effective_budget, background,
        )
        self._post_bus_event("agent_started", agent_id, agent_def.name)

        start = time.monotonic()
        tokens_used = 0

        try:
            async for output in agent.run(state):
                # Accumulate token usage (internal, not forwarded)
                if output.type == AgentOutputType.USAGE:
                    tokens_used += output.metadata.get("total_tokens", 0)
                    continue

                # Check token budget
                if effective_budget > 0 and tokens_used >= effective_budget:
                    logger.warning(
                        "Agent '%s' hit token budget (%d/%d tokens)",
                        agent_def.name, tokens_used, effective_budget,
                    )
                    yield AgentOutput(
                        type=AgentOutputType.TOKEN,
                        content=f"\n[Agent '{agent_def.name}' reached "
                                f"token budget ({tokens_used}/{effective_budget} tokens)]",
                    )
                    break

                # Stream all outputs to caller
                yield output

        except Exception as e:
            logger.error(
                "Agent '%s' (id=%s) error: %s",
                agent_def.name, agent_id, e, exc_info=True,
            )
            yield AgentOutput(
                type=AgentOutputType.TOOL_RESULT,
                content=f"Agent error: {e!s}",
                metadata={"status": "error"},
            )
        finally:
            elapsed = time.monotonic() - start
            tracker.active = False
            logger.info(
                "AgentRunner: '%s' (id=%s) finished in %.1fs, %d tokens used",
                agent_def.name, agent_id, elapsed, tokens_used,
            )
            self._post_bus_event("agent_finished", agent_id, agent_def.name)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_depth(self, parent_agent_id: str | None) -> int:
        """Calculate depth from parent chain."""
        if parent_agent_id is None:
            return 0
        tracker = self._active_agents.get(parent_agent_id)
        if tracker is None:
            return 1
        return tracker.depth + 1

    def _resolve_toolset(self, toolset_name: str) -> list[str] | None:
        """Resolve a toolset profile name to a tool allowlist.

        Returns None if the profile is empty (= all tools) or not found.
        """
        if not toolset_name:
            return None
        config = getattr(self, '_toolsets_config', None)
        if config is None:
            logger.warning("Toolset '%s' requested but no toolsets config available", toolset_name)
            return None
        profile = config.profiles.get(toolset_name)
        if profile is None:
            logger.warning("Toolset profile '%s' not found in config", toolset_name)
            return None
        if not profile.tools:
            return None  # Empty tools list = all tools
        return list(profile.tools)

    def _build_sub_agent_prompt(
        self,
        agent_def: AgentDefinition,
        messages: list[dict[str, Any]],
    ) -> str:
        """Build a sub-agent's system prompt.

        Combines the agent definition's own prompt with workspace rules
        relevant to the task's paths and base security rules.
        """
        parts: list[str] = [agent_def.system_prompt]

        # Inject ask_user guidance so sub-agents know they can pause
        parts.append(
            "--- Clarification ---\n"
            "If you need clarification from the user before you can proceed "
            "(e.g., choosing between options, missing critical info), call the "
            "`ask_user` tool with your question. Your execution will pause "
            "until the user responds. Do NOT write questions in your final "
            "output — use `ask_user` instead so the system can route the "
            "question properly and resume your work with the answer."
        )

        # Append workspace rules relevant to paths mentioned in messages
        paths = self._extract_paths_from_messages(messages)
        workspace_rules = self._prompt_assembler.get_workspace_rules_for(paths)
        if workspace_rules:
            parts.append("--- Workspace Rules ---\n" + workspace_rules)

        # Always append base security rules
        base_rules = self._prompt_assembler.get_base_rules()
        if base_rules:
            parts.append("--- Security Rules ---\n" + base_rules)

        return "\n\n".join(parts)

    @staticmethod
    def _extract_paths_from_messages(messages: list[dict[str, Any]]) -> list[str]:
        """Extract file/directory paths from message content (simple heuristic)."""
        import re

        path_re = re.compile(r"(?:~|/)[^\s,;\"'`\]\)}>]+")
        paths: list[str] = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                paths.extend(path_re.findall(content))
        return paths

    def _post_bus_event(
        self, event: str, agent_id: str, agent_name: str,
    ) -> None:
        if self._bus is None:
            return
        from ..pipeline.bus import BusMessage

        self._bus.post(BusMessage(
            type="agent",
            source="agent_runner",
            payload={
                "event": event,
                "agent_id": agent_id,
                "agent_name": agent_name,
            },
            timestamp=time.time(),
        ))


class _AgentTracker:
    """Tracks an active agent for depth/concurrency enforcement."""

    __slots__ = ("agent_id", "agent_name", "parent_id", "depth", "active")

    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        parent_id: str | None,
        depth: int,
    ) -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.parent_id = parent_id
        self.depth = depth
        self.active = True
