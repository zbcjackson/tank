"""Integration test for processing_started/ended signals through WebSocket."""

from unittest.mock import MagicMock, patch

import pytest

from tank_backend.audio.input.types import AudioSource
from tank_backend.audio.output.types import AudioSink
from tank_backend.core.assistant import Assistant
from tank_backend.core.events import SignalMessage, UpdateType

MODULE = "tank_backend.core.assistant"


class MockAudioSource(AudioSource):
    """Mock audio source for testing."""

    def start(self):
        pass

    def join(self, timeout=None):
        pass


class MockAudioSink(AudioSink):
    """Mock audio sink for testing."""

    def start(self):
        pass

    def join(self, timeout=None):
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


def _make_mock_registry(mock_asr_engine=None, mock_tts_engine=None):
    """Build a mock registry that returns pre-built engines."""
    registry = MagicMock()

    def instantiate(full_name, config):
        if full_name and "asr" in full_name:
            return mock_asr_engine or MagicMock()
        if full_name and "tts" in full_name:
            return mock_tts_engine or MagicMock()
        return MagicMock()

    registry.instantiate.side_effect = instantiate
    return registry


def _make_mock_app_config(asr=True, tts=True, speaker=False):
    """Build a mock AppConfig with slot enable/disable."""
    mock = MagicMock()
    mock.get_llm_profile.return_value = MagicMock()

    def is_slot_enabled(slot):
        return {"asr": asr, "tts": tts, "speaker": speaker}.get(slot, False)

    mock.is_slot_enabled.side_effect = is_slot_enabled

    def get_slot_config(slot):
        cfg = MagicMock()
        cfg.enabled = is_slot_enabled(slot)
        cfg.extension = f"mock-{slot}:{slot}" if cfg.enabled else None
        cfg.config = {}
        cfg.plugin = f"mock-{slot}" if cfg.enabled else ""
        return cfg

    mock.get_slot_config.side_effect = get_slot_config
    return mock


@pytest.fixture
def assistant(mock_audio_source_factory, mock_audio_sink_factory, tmp_path):
    """Create assistant with mocked audio."""
    config_file = tmp_path / ".env"
    config_file.write_text("")

    mock_asr_engine = MagicMock()
    mock_asr_engine.process_pcm = MagicMock(return_value=("", False))
    mock_asr_engine.reset = MagicMock()

    mock_registry = _make_mock_registry(mock_asr_engine=mock_asr_engine)
    mock_app_config = _make_mock_app_config()

    # Mock LLM with streaming support
    async def mock_stream(*args, **kwargs):
        yield UpdateType.TEXT, "Hello", {}

    mock_llm = MagicMock()
    mock_llm.chat_stream = mock_stream

    mock_pm = MagicMock()
    mock_pm.load_all.return_value = mock_registry

    with (
        patch(f"{MODULE}.PluginManager", return_value=mock_pm),
        patch(f"{MODULE}.AppConfig", return_value=mock_app_config),
        patch(f"{MODULE}.create_llm_from_profile", return_value=mock_llm),
    ):
        assistant = Assistant(
            config_path=config_file,
            audio_source_factory=mock_audio_source_factory,
            audio_sink_factory=mock_audio_sink_factory,
        )

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
