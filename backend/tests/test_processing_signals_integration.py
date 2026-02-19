"""Integration test for processing_started/ended signals through WebSocket."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from tank_backend.core.assistant import Assistant
from tank_backend.core.events import UpdateType, SignalMessage
from tank_backend.audio.input.types import AudioSource
from tank_backend.audio.output.types import AudioSink


class MockAudioSource(AudioSource):
    """Mock audio source for testing."""
    def start(self):
        pass

    def join(self):
        pass


class MockAudioSink(AudioSink):
    """Mock audio sink for testing."""
    def start(self):
        pass

    def join(self):
        pass


@pytest.fixture
def mock_audio_source_factory():
    def factory(q, stop_sig):
        return MockAudioSource()
    return factory


@pytest.fixture
def mock_audio_sink_factory():
    def factory(q, stop_sig):
        return MockAudioSink()
    return factory


@pytest.fixture
def assistant(mock_audio_source_factory, mock_audio_sink_factory, tmp_path):
    """Create assistant with mocked audio."""
    # Create a minimal config file
    config_file = tmp_path / ".env"
    config_file.write_text("LLM_API_KEY=test_key\n")

    assistant = Assistant(
        config_path=config_file,
        audio_source_factory=mock_audio_source_factory,
        audio_sink_factory=mock_audio_sink_factory
    )

    # Mock LLM
    async def mock_stream(*args, **kwargs):
        yield UpdateType.TEXT, "Hello", {}

    assistant._llm.chat_stream = AsyncMock(return_value=mock_stream())

    yield assistant


def test_assistant_sends_processing_signals(assistant):
    """Test that assistant sends processing_started and processing_ended signals."""
    # Start the assistant threads
    assistant.start()

    try:
        # Send text input
        assistant.process_input("Hello")

        # Give Brain time to process
        import time
        time.sleep(1.0)

        # Collect messages
        messages = list(assistant.get_messages())

        # Find signals
        signal_msgs = [m for m in messages if isinstance(m, SignalMessage)]
        started = [m for m in signal_msgs if m.signal_type == "processing_started"]
        ended = [m for m in signal_msgs if m.signal_type == "processing_ended"]

        assert len(started) == 1, "Should have processing_started signal"
        assert len(ended) == 1, "Should have processing_ended signal"

        # Verify order
        started_idx = messages.index(started[0])
        ended_idx = messages.index(ended[0])
        assert started_idx < ended_idx, "processing_started should come before processing_ended"
    finally:
        # Stop the assistant
        assistant.stop()
