"""Tests for Brain thread."""

from unittest.mock import MagicMock

import pytest

from tank_backend.audio.output import AudioOutput
from tank_backend.config.settings import VoiceAssistantConfig
from tank_backend.core.brain import Brain
from tank_backend.core.events import BrainInputEvent, InputType
from tank_backend.core.runtime import RuntimeContext
from tank_backend.core.shutdown import GracefulShutdown


class TestBrain:
    """Unit tests for Brain."""

    @pytest.fixture
    def runtime(self):
        return RuntimeContext.create()

    @pytest.fixture
    def shutdown_signal(self):
        return GracefulShutdown()

    @pytest.fixture
    def mock_speaker(self):
        return MagicMock(spec=AudioOutput)

    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def mock_tool_manager(self):
        return MagicMock()

    @pytest.fixture
    def mock_config(self):
        return VoiceAssistantConfig(
            llm_api_key="test_key",
            llm_model="test_model",
            llm_base_url="https://test.com/v1",
            max_conversation_history=10,
        )

    @pytest.fixture
    def brain(
        self, shutdown_signal, runtime, mock_speaker, mock_llm, mock_tool_manager, mock_config
    ):
        return Brain(
            shutdown_signal=shutdown_signal,
            runtime=runtime,
            speaker_ref=mock_speaker,
            llm=mock_llm,
            tool_manager=mock_tool_manager,
            config=mock_config,
        )

    def test_brain_inherits_from_queue_worker(self, brain):
        """Brain should inherit from QueueWorker."""
        from tank_backend.core.worker import QueueWorker

        assert isinstance(brain, QueueWorker)

    def test_brain_consumes_from_brain_input_queue(self, brain, runtime, shutdown_signal):
        """Brain should consume BrainInputEvent from brain_input_queue."""
        event = BrainInputEvent(
            type=InputType.TEXT,
            text="hello",
            user="TestUser",
            language=None,
            confidence=None,
        )
        runtime.brain_input_queue.put(event)

        # Start brain in a thread and let it process
        brain.start()

        # Wait a bit for processing
        import time

        time.sleep(0.2)

        # Stop brain
        shutdown_signal.stop()
        brain.join(timeout=1.0)

        # Verify handle was called (indirectly by checking queues)
        # The exact behavior depends on implementation, but we can check
        # that the queue was consumed
        assert runtime.brain_input_queue.empty()

    def test_brain_handle_method_exists(self, brain):
        """Brain should have handle method."""
        assert hasattr(brain, "handle")
        assert callable(brain.handle)

    def test_brain_loads_system_prompt(self, brain):
        """Brain should load system prompt from file."""
        assert hasattr(brain, "_system_prompt")
        assert isinstance(brain._system_prompt, str)
        assert len(brain._system_prompt) > 0
        assert "Tank" in brain._system_prompt

    def test_brain_initializes_conversation_history_with_system(self, brain):
        """Brain should initialize conversation history with system prompt as first message."""
        assert hasattr(brain, "_conversation_history")
        assert len(brain._conversation_history) == 1
        assert brain._conversation_history[0]["role"] == "system"
        assert brain._conversation_history[0]["content"] == brain._system_prompt

    def test_brain_includes_speaker_name_in_conversation_history(
        self, brain, runtime, shutdown_signal, mock_llm
    ):
        """Brain should include speaker name in conversation history."""
        # Mock LLM to return immediately
        async def mock_chat_stream(*args, **kwargs):
            yield ("text", "Hello!", {})

        mock_llm.chat_stream = mock_chat_stream

        event = BrainInputEvent(
            type=InputType.TEXT,
            text="What's the weather?",
            user="Jackson",
            language="en",
            confidence=None,
        )

        # Process the event
        brain.handle(event)

        # Check conversation history includes speaker name
        assert len(brain._conversation_history) >= 2  # system + user message
        user_message = brain._conversation_history[1]
        assert user_message["role"] == "user"
        assert "Jackson:" in user_message["content"]
        assert "What's the weather?" in user_message["content"]

    def test_brain_handles_unknown_speaker(self, brain, runtime, shutdown_signal, mock_llm):
        """Brain should handle Unknown speaker gracefully."""
        # Mock LLM to return immediately
        async def mock_chat_stream(*args, **kwargs):
            yield ("text", "Hello!", {})

        mock_llm.chat_stream = mock_chat_stream

        event = BrainInputEvent(
            type=InputType.TEXT,
            text="Hello",
            user="Unknown",
            language="en",
            confidence=None,
        )

        # Process the event
        brain.handle(event)

        # Check conversation history includes Unknown speaker
        assert len(brain._conversation_history) >= 2
        user_message = brain._conversation_history[1]
        assert user_message["role"] == "user"
        assert "Unknown:" in user_message["content"]

    def test_system_prompt_includes_speaker_awareness(self, brain):
        """System prompt should mention speaker awareness."""
        assert "SPEAKER AWARENESS" in brain._system_prompt
        assert "speaker" in brain._system_prompt.lower()
