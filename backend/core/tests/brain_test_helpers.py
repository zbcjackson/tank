"""Shared test helpers for Brain tests."""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock, patch

from tank_backend.context.conversation import ConversationData
from tank_backend.context.resolver import CompactionMode, ResolvedConversation
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import Brain, BrainConfig


def make_mock_context(system_prompt: str = "You are a helpful assistant.") -> MagicMock:
    """Create a mock ContextManager for Brain tests."""
    ctx = MagicMock()
    ctx.session_id = "test-session-id"
    ctx.conversation_id = "test-session-id"
    ctx.messages = [{"role": "system", "content": system_prompt}]
    ctx.prepare_turn = AsyncMock(return_value=[{"role": "system", "content": system_prompt}])
    ctx.count_tokens.return_value = 0
    ctx.recall_memory = AsyncMock()
    ctx.compact = AsyncMock()
    ctx.assemble_system_prompt.return_value = system_prompt
    ctx.preference_store = None
    ctx.pending_approvals = None
    return ctx


def make_mock_resolver() -> MagicMock:
    """Create a mock ConversationResolver for Brain tests."""
    conv = ConversationData.new("You are a helpful assistant.")
    resolved = ResolvedConversation(
        conversation=conv, compaction_mode=CompactionMode.DESTRUCTIVE,
    )
    resolver = MagicMock()
    resolver.resume_or_new.return_value = resolved
    resolver.resume.return_value = resolved
    resolver.new.return_value = resolved
    return resolver


def make_brain(
    *,
    llm: object | None = None,
    tool_manager: object | None = None,
    config: BrainConfig | None = None,
    bus: Bus | None = None,
    interrupt_event: threading.Event | None = None,
    context: object | None = None,
    tts_enabled: bool = True,
    echo_guard_config: object | None = None,
    agent_graph: object | None = None,
) -> Brain:
    """Create a Brain with sensible mock defaults for testing."""
    if llm is None:
        llm = MagicMock()
    if tool_manager is None:
        tool_manager = MagicMock()
        tool_manager.approval_policy = MagicMock()
    if config is None:
        config = BrainConfig()
    if bus is None:
        bus = Bus()
    if interrupt_event is None:
        interrupt_event = threading.Event()
    if context is None:
        context = make_mock_context()

    # If no agent_graph provided, create a minimal one to avoid _build_agent_graph
    # being called with a mock app_config (which would fail)
    if agent_graph is None:
        from tank_backend.agents.graph import AgentGraph
        from tank_backend.agents.llm_agent import LLMAgent

        mock_agent = LLMAgent(
            name="chat",
            llm=llm,
            tool_manager=tool_manager,
        )
        agent_graph = AgentGraph(agents={"chat": mock_agent}, default_agent="chat")

    mock_app_config = MagicMock()
    mock_app_config.get_section.return_value = {}

    # Brain creates ConversationResolver and ContextManager internally.
    # Patch both at the import level so Brain.__init__ picks up our mocks.
    mock_cm_class = MagicMock(return_value=context)
    mock_resolver_class = MagicMock(return_value=make_mock_resolver())
    with (
        patch.dict(
            "tank_backend.context.__dict__",
            {"ContextManager": mock_cm_class},
        ),
        patch(
            "tank_backend.context.resolver.ConversationResolver",
            mock_resolver_class,
        ),
    ):
        return Brain(
            llm=llm,
            tool_manager=tool_manager,
            config=config,
            bus=bus,
            interrupt_event=interrupt_event,
            app_config=mock_app_config,
            tts_enabled=tts_enabled,
            echo_guard_config=echo_guard_config,
            agent_graph=agent_graph,
        )
