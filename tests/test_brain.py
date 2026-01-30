"""Tests for Brain thread."""

import queue
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.voice_assistant.core.brain import Brain
from src.voice_assistant.core.events import BrainInputEvent, DisplayMessage, InputType
from src.voice_assistant.core.runtime import RuntimeContext
from src.voice_assistant.core.shutdown import GracefulShutdown
from src.voice_assistant.audio.output import SpeakerHandler
from src.voice_assistant.config.settings import VoiceAssistantConfig


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
        return MagicMock(spec=SpeakerHandler)

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
    def brain(self, shutdown_signal, runtime, mock_speaker, mock_llm, mock_tool_manager, mock_config):
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
        from src.voice_assistant.core.worker import QueueWorker
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
        assert hasattr(brain, 'handle')
        assert callable(brain.handle)

    def test_brain_loads_system_prompt(self, brain):
        """Brain should load system prompt from file."""
        assert hasattr(brain, '_system_prompt')
        assert isinstance(brain._system_prompt, str)
        assert len(brain._system_prompt) > 0
        assert "Tank" in brain._system_prompt

    def test_brain_initializes_conversation_history_with_system(self, brain):
        """Brain should initialize conversation history with system prompt as first message."""
        assert hasattr(brain, '_conversation_history')
        assert len(brain._conversation_history) == 1
        assert brain._conversation_history[0]["role"] == "system"
        assert brain._conversation_history[0]["content"] == brain._system_prompt
