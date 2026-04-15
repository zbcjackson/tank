"""Shared test helpers for Brain tests."""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock

from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import Brain, BrainConfig


def make_mock_context(system_prompt: str = "You are a helpful assistant.") -> MagicMock:
    """Create a mock ContextManager for Brain tests."""
    ctx = MagicMock()
    ctx.session_id = "test-session-id"
    ctx.messages = [{"role": "system", "content": system_prompt}]
    ctx.resume_or_new.return_value = "test-session-id"
    ctx.prepare_turn.return_value = [{"role": "system", "content": system_prompt}]
    ctx.count_tokens.return_value = 0
    # Async methods must be AsyncMock so they can be awaited
    ctx.recall_memory = AsyncMock()
    ctx.maybe_compact = AsyncMock()
    return ctx


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
    approval_manager: object | None = None,
) -> Brain:
    """Create a Brain with sensible mock defaults for testing."""
    if llm is None:
        llm = MagicMock()
    if tool_manager is None:
        tool_manager = MagicMock()
    if config is None:
        config = BrainConfig()
    if bus is None:
        bus = Bus()
    if interrupt_event is None:
        interrupt_event = threading.Event()
    if context is None:
        context = make_mock_context()

    return Brain(
        llm=llm,
        tool_manager=tool_manager,
        config=config,
        bus=bus,
        interrupt_event=interrupt_event,
        context=context,
        tts_enabled=tts_enabled,
        echo_guard_config=echo_guard_config,
        agent_graph=agent_graph,
        approval_manager=approval_manager,
    )
