"""AgentRunner — single execution method for all agents.

Brain uses it for the main agent. The ``agent`` tool uses it for sub-agents.
Skills use it for fork mode. All agents get approval, UI streaming, and
lifecycle management consistently through this one entry point.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from .base import AgentOutput, AgentOutputType, AgentState
from .definition import AgentDefinition
from .llm_agent import LLMAgent
from .resources import DESKTOP_RESOURCE, DesktopResource
from .subagent import (
    SubAgentAuthorization,
    SubAgentBudget,
    SubAgentCleanupError,
    SubAgentContext,
    SubAgentObserver,
    SubAgentRequest,
)
from .subagent_adapter import SubAgentAdapter

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
        app_config: Any = None,
        registry: Any = None,
        desktop_resource: DesktopResource | None = None,
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
        self._app_config = app_config
        # B2: ExtensionRegistry for plugin agent engines ("brain in the
        # plugin"). None = this context can only run built-in agents.
        self._registry = registry
        self._desktop_resource = desktop_resource or DESKTOP_RESOURCE

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

    def extension_permissions(self, agent_def: AgentDefinition) -> frozenset[str]:
        if self._registry is None:
            raise RuntimeError("Subagent requires an ExtensionRegistry")
        manifest = self._registry.get_manifest(agent_def.extension)
        if manifest is None or manifest.type != "subagent":
            raise ValueError(
                f"Subagent extension '{agent_def.extension}' is missing or has wrong type"
            )
        return frozenset(manifest.permissions)

    def _uses_desktop(self, agent_def: AgentDefinition) -> bool:
        if agent_def.grounding is not None:
            return True
        if agent_def.extension:
            return "desktop" in self.extension_permissions(agent_def)
        if agent_def.engine:
            manifest = self._registry.get_manifest(agent_def.engine) if self._registry else None
            return manifest is not None and "desktop_executor" in manifest.needs
        tools = agent_def.tool_filter
        if tools is None and agent_def.toolset:
            tools = self._resolve_toolset(agent_def.toolset)
        return tools is not None and any(
            self._approval_policy.category_for(t) == "computer" for t in tools
        )

    async def run_agent(
        self, agent_def: AgentDefinition, messages: list[dict[str, Any]],
        parent_agent_id: str | None = None, background: bool = False,
        token_budget: int | None = None, allowed_categories: set[str] | None = None,
        *, task_id: str | None = None,
        authorization: SubAgentAuthorization | None = None,
        deadline: float | None = None, observer: SubAgentObserver | None = None,
        max_steps: int | None = None,
    ) -> AsyncIterator[AgentOutput]:
        context = None
        if agent_def.grounding is not None:
            deadline = deadline if deadline is not None else time.monotonic() + 600
            context = SubAgentContext(
                authorization or SubAgentAuthorization(frozenset({"desktop"})),
                SubAgentBudget(limit=(
                    agent_def.token_budget if token_budget is None else token_budget
                )),
                asyncio.Event(), deadline, observer, max_steps,
            )
            context.check("desktop")
        if agent_def.extension:
            deadline = deadline if deadline is not None else time.monotonic() + 600
            permissions = self.extension_permissions(agent_def)
            authorization = authorization or SubAgentAuthorization()
            for permission in permissions:
                authorization.check(permission)
            context = SubAgentContext(
                authorization, SubAgentBudget(limit=(
                    agent_def.token_budget if token_budget is None else token_budget
                )), asyncio.Event(), deadline, observer, max_steps,
            )
            context.check()
        outputs = self._run_agent(
            agent_def, messages, parent_agent_id, background, token_budget,
            allowed_categories, context=context, task_id=task_id,
        )
        try:
            if self._uses_desktop(agent_def):
                async with self._desktop_resource.acquire(deadline=deadline):
                    try:
                        async with asyncio.timeout_at(deadline if agent_def.grounding else None):
                            async for output in outputs:
                                yield output
                    finally:
                        await outputs.aclose()
            else:
                try:
                    async for output in outputs:
                        yield output
                finally:
                    await outputs.aclose()
        except SubAgentCleanupError as exc:
            if self._uses_desktop(agent_def):
                self._desktop_resource.quarantine(str(exc))
            raise
        finally:
            if context is not None:
                context.cancel.set()

    async def _run_agent(
        self,
        agent_def: AgentDefinition,
        messages: list[dict[str, Any]],
        parent_agent_id: str | None = None,
        background: bool = False,
        token_budget: int | None = None,
        allowed_categories: set[str] | None = None,
        *, context: SubAgentContext | None = None, task_id: str | None = None,
    ) -> AsyncGenerator[AgentOutput, None]:
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

        # Resolve tools: all tools minus disallowed, filtered by toolset
        exclude = set(agent_def.disallowed_tools)
        if parent_agent_id is not None:
            # Sub-agents get global disallowed tools
            exclude |= GLOBAL_DISALLOWED_FOR_SUBAGENTS

        # Inline allowlist takes priority, then named toolset profile
        tool_filter: list[str] | None = None
        if agent_def.tool_filter is not None:
            tool_filter = list(agent_def.tool_filter)
        elif agent_def.toolset:
            tool_filter = self._resolve_toolset(agent_def.toolset)

        exclude_tools = exclude or None

        effective_budget = token_budget or agent_def.token_budget

        available_tools: set[str] = set()
        if not agent_def.engine and not agent_def.extension:
            available_tools = {
                tool["function"]["name"]
                for tool in self._tool_manager.get_openai_tools(exclude=exclude_tools)
                if tool_filter is None or tool["function"]["name"] in tool_filter
            }
        system_prompt = self._build_sub_agent_prompt(agent_def, messages, available_tools)
        owned_grounders: list[LLM] = []

        if agent_def.extension:
            if context is None:
                raise RuntimeError("Subagent runtime context missing")
            context.check()
            for permission in self.extension_permissions(agent_def):
                context.authorization.check(permission)
            config = (self._app_config.subagents.get(agent_def.extension, {})
                      if self._app_config is not None else {})
            from .subagent import SubAgent

            plugin = self._registry.instantiate(agent_def.extension, dict(config))
            if not isinstance(plugin, SubAgent):
                raise TypeError("Subagent factory must return SubAgent")
            task = next((m.get("content", "") for m in reversed(messages)
                         if m.get("role") == "user" and isinstance(m.get("content"), str)), "")
            agent = SubAgentAdapter(agent_def.name, plugin, SubAgentRequest(
                task=task, context=agent_def.system_prompt, task_id=task_id or agent_id,
            ), context)
        elif agent_def.engine:
            # B2 factory branch: plugin agent engine (e.g. agent-n2).
            # toolset/model are meaningless for engine agents — ignored.
            agent = self._create_engine_agent(agent_def, system_prompt)
        else:
            # Resolve LLM: use agent-specific model profile if declared
            if agent_def.model and self._app_config is not None:
                from ..llm.profile import create_llm_from_profile

                agent_llm = create_llm_from_profile(
                    self._app_config.get_llm_profile(agent_def.model)
                )
            else:
                agent_llm = self._llm

            tool_manager = self._tool_manager
            if agent_def.grounding is not None:
                from dataclasses import replace

                from ..llm.profile import create_llm_from_profile
                from ..tools.computer_grounding import GroundingAdapter
                from ..tools.computer_locate import SPLIT_PROMPT, LocateSession, LocateTool

                assert context is not None
                config = agent_def.grounding
                from ..tools.computer_frame import FrameTool

                session_tools = {n: t for n, t in self._tool_manager.tools.items()
                                 if n in available_tools}
                if not isinstance(session_tools.get("screenshot"), FrameTool):
                    raise ValueError("Split grounding requires an allowed macOS screenshot tool")
                for profile in (config.profile, config.fallback_profile):
                    if profile is not None and (
                        self._app_config is None or profile not in self._app_config.llm_profiles
                    ):
                        raise ValueError(f"Unknown grounding profile: {profile}")
                llms = {"primary": agent_llm}
                for key, profile in (("primary", config.profile),
                                     ("fallback", config.fallback_profile)):
                    if profile is not None:
                        assert self._app_config is not None
                        llms[key] = create_llm_from_profile(self._app_config.llm_profiles[profile])
                        owned_grounders.append(llms[key])
                session = LocateSession(session_tools, llms, GroundingAdapter(
                    config.protocol, config.nullable_style, config.strict,
                    config.detail, config.status_field,
                ), context, agent_id)
                tool_manager = copy.copy(self._tool_manager)
                tool_manager.tools = dict(session_tools)
                tool_manager.tool_metadata = dict(self._tool_manager.tool_metadata)
                # Raw held-button tools bypass reference validation. Keep them out of split mode.
                for name in ("computer_batch", "mouse_down", "mouse_up"):
                    tool_manager.tools.pop(name, None)
                for name, tool in list(tool_manager.tools.items()):
                    if tool.get_metadata().category == "computer":
                        tool_manager.register_tool(LocateTool(session, name))
                tool_manager.register_tool(LocateTool(session, "locate"))
                tool_manager.register_tool(LocateTool(session, "computer_batch"))
                tool_manager.set_session_id(agent_id)
                if tool_filter is not None:
                    tool_filter.append("locate")
                available_tools = {
                    t["function"]["name"]
                    for t in tool_manager.get_openai_tools(exclude=exclude_tools)
                    if tool_filter is None or t["function"]["name"] in tool_filter
                }
                # Override the coordinate contract without losing task-specific instructions.
                system_prompt = self._build_sub_agent_prompt(
                    replace(
                        agent_def, system_prompt=agent_def.system_prompt + "\n\n" + SPLIT_PROMPT,
                    ),
                    messages, available_tools,
                )

            approval_policy: Any = self._approval_policy
            if agent_def.grounding is not None:
                approval_policy = copy.copy(self._approval_policy)
                approval_policy._tool_metadata = tool_manager.tool_metadata
            if allowed_categories and approval_policy is not None:
                from .approval import ScopedPolicy

                approval_policy = ScopedPolicy(approval_policy, allowed_categories)
            agent = LLMAgent(
                name=f"agent_{agent_def.name}",
                llm=agent_llm,
                tool_manager=tool_manager,
                approval_policy=approval_policy,
                system_prompt=system_prompt,
                tool_filter=tool_filter,
                exclude_tools=exclude_tools,
                resolver=self._resolver,
                session_id=agent_id,
                pending_store=self._pending_store,
                bus=self._bus,
                task_context=context,
            )

        # A failed factory must not occupy a concurrent-agent slot.
        self._active_agents[agent_id] = tracker
        state = AgentState(
            messages=cast(Any, list(messages)),
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
        outputs = agent.run(state)
        try:
            async for output in outputs:
                # Accumulate token usage (internal, not forwarded)
                if output.type == AgentOutputType.USAGE:
                    tokens_used = (context.budget.total_tokens if context is not None
                                   else tokens_used + output.metadata.get("total_tokens", 0))
                    continue

                # Check token budget
                if context is None and effective_budget > 0 and tokens_used >= effective_budget:
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
            if agent_def.extension:
                raise
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
            tracker.active = False
            close = getattr(outputs, "aclose", None)
            if close is not None:
                await close()
            for grounder in owned_grounders:
                await grounder.client.close()
            if context is not None:
                tokens_used = context.budget.total_tokens
            elapsed = time.monotonic() - start
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

    def _create_engine_agent(
        self, agent_def: AgentDefinition, system_prompt: str,
    ) -> Any:
        """Instantiate a plugin agent engine via the ExtensionRegistry.

        The factory config carries only what the engine declared it
        needs (B2 trust boundary): a DesktopExecutor when the manifest
        ``needs`` includes it, the LLM profile named after the plugin
        (e.g. "agent-n2:agent" → profile "agent-n2", None when absent),
        and the assembled system prompt.
        """
        engine = agent_def.engine
        if not engine:
            raise RuntimeError(
                f"Agent '{agent_def.name}' has no engine declared"
            )
        if self._registry is None:
            raise RuntimeError(
                f"Agent '{agent_def.name}' requires engine "
                f"'{engine}' but no ExtensionRegistry is "
                f"available in this context"
            )

        from ..computer.executor import create_desktop_executor

        manifest = self._registry.get_manifest(engine)
        needs = getattr(manifest, "needs", ()) or ()

        engine_config: dict[str, Any] = {}
        if self._app_config is not None:
            engine_config = self._app_config.get_section("agent_engines").get(engine, {})
            if not isinstance(engine_config, dict):
                raise ValueError(f"agent_engines.{engine} must be a mapping")
        llm_profile = None
        if self._app_config is not None:
            profile_name = engine_config.get("llm_profile", engine.split(":", 1)[0])
            # Engine protocols can be provider-specific. Never substitute the
            # default chat model when the requested profile is absent.
            llm_profile = self._app_config.llm_profiles.get(profile_name)
            if llm_profile is None:
                logger.warning(
                    "Engine '%s': LLM profile '%s' not found; no fallback", engine, profile_name,
                )

        config: dict[str, Any] = {
            **engine_config,
            "system_prompt": system_prompt,
            "desktop_executor": (
                create_desktop_executor()
                if "desktop_executor" in needs
                else None
            ),
            "llm_profile": llm_profile,
        }
        return self._registry.instantiate(engine, config)

    def _build_sub_agent_prompt(
        self,
        agent_def: AgentDefinition,
        messages: list[dict[str, Any]],
        available_tools: set[str],
    ) -> str:
        """Build a sub-agent's system prompt.

        Combines the agent definition's own prompt with workspace rules
        relevant to the task's paths and base security rules.
        """
        parts: list[str] = [agent_def.system_prompt]

        if "ask_user" in available_tools:
            parts.append(
                "--- Clarification ---\n"
                "If you need clarification from the user before you can proceed "
                "(e.g., choosing between options, missing critical info), call the "
                "`ask_user` tool with your question. Your execution will pause "
                "until the user responds. Do NOT write questions in your final "
                "output — use `ask_user` instead so the system can route the "
                "question properly and resume your work with the answer."
            )
        else:
            parts.append(
                "--- Clarification ---\n"
                "If critical information is missing and you cannot proceed, "
                "stop and report what information is needed in your final output."
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
