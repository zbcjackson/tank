"""Tests for Brain conversation persistence via Checkpointer."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from tank_backend.persistence.checkpointer import Checkpointer
from tank_backend.pipeline.bus import Bus
from tank_backend.pipeline.processors.brain import Brain

MODULE = "tank_backend.pipeline.processors.brain"


@pytest.fixture
def checkpointer(tmp_path):
    cp = Checkpointer(tmp_path / "test.db")
    yield cp
    cp.close()


def _make_brain(checkpointer=None, session_id=None):
    config = MagicMock()
    config.max_history_tokens = 8000
    config.summarize_at_tokens = 6000
    config.speech_interrupt_enabled = False

    llm = MagicMock()
    tool_manager = MagicMock()
    bus = Bus()

    with patch(f"{MODULE}.Brain._load_system_prompt", return_value="You are helpful."):
        brain = Brain(
            llm=llm,
            tool_manager=tool_manager,
            config=config,
            bus=bus,
            interrupt_event=threading.Event(),
            checkpointer=checkpointer,
            session_id=session_id,
        )
    return brain


def test_brain_checkpoints_after_turn(checkpointer):
    """Brain._checkpoint() persists conversation history."""
    brain = _make_brain(checkpointer=checkpointer, session_id="s1")
    brain._add_to_conversation_history("user", "hello")
    brain._add_to_conversation_history("assistant", "hi")
    brain._checkpoint()

    loaded = checkpointer.load("s1")
    assert loaded is not None
    assert len(loaded) == 3  # system + user + assistant
    assert loaded[0]["role"] == "system"
    assert loaded[1]["content"] == "hello"
    assert loaded[2]["content"] == "hi"


def test_brain_loads_from_checkpoint_on_set_session_id(checkpointer):
    """set_session_id() restores history from checkpoint."""
    # Pre-populate checkpoint
    saved_history = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "previous question"},
        {"role": "assistant", "content": "previous answer"},
    ]
    checkpointer.save("s2", saved_history)

    brain = _make_brain(checkpointer=checkpointer)
    assert len(brain._conversation_history) == 1  # only system prompt

    brain.set_session_id("s2")
    assert len(brain._conversation_history) == 3
    assert brain._conversation_history[1]["content"] == "previous question"


def test_brain_without_checkpointer_works_normally():
    """Brain without checkpointer should work without errors."""
    brain = _make_brain(checkpointer=None, session_id=None)
    brain._add_to_conversation_history("user", "hello")
    brain._checkpoint()  # should be a no-op
    brain.set_session_id("s1")  # should be a no-op
    assert len(brain._conversation_history) == 2  # system + user


def test_brain_checkpoint_failure_is_graceful(checkpointer):
    """Checkpoint save failure should be logged, not raised."""
    brain = _make_brain(checkpointer=checkpointer, session_id="s1")
    brain._add_to_conversation_history("user", "hello")

    # Force save to fail
    checkpointer.close()

    # Should not raise
    brain._checkpoint()


def test_brain_reset_checkpoints_empty_history(checkpointer):
    """reset_conversation() should checkpoint the reset state."""
    brain = _make_brain(checkpointer=checkpointer, session_id="s1")
    brain._add_to_conversation_history("user", "hello")
    brain._checkpoint()

    brain.reset_conversation()

    loaded = checkpointer.load("s1")
    assert loaded is not None
    assert len(loaded) == 1  # only system prompt
    assert loaded[0]["role"] == "system"
