"""Tests for Perception thread (ASR + display)."""

import queue
import numpy as np
import pytest
from unittest.mock import MagicMock

from src.voice_assistant.audio.input.perception import Perception, PerceptionConfig
from src.voice_assistant.audio.input.segmenter import Utterance
from src.voice_assistant.audio.input.voiceprint import VoiceprintRecognizer
from src.voice_assistant.core.events import BrainInputEvent, DisplayMessage, InputType
from src.voice_assistant.core.runtime import RuntimeContext
from src.voice_assistant.core.shutdown import GracefulShutdown


def make_utterance(pcm_len=1600, sample_rate=16000):
    """Create a minimal Utterance (0.1s at 16kHz)."""
    pcm = np.zeros(pcm_len, dtype=np.float32)
    return Utterance(
        pcm=pcm,
        sample_rate=sample_rate,
        started_at_s=0.0,
        ended_at_s=0.1,
    )


class TestPerception:
    """Unit tests for Perception with mocked ASR."""

    @pytest.fixture
    def runtime(self):
        return RuntimeContext.create()

    @pytest.fixture
    def mock_asr(self):
        asr = MagicMock()
        asr.transcribe.return_value = ("hello world", "en", 0.95)
        return asr

    @pytest.fixture
    def perception(self, runtime, mock_asr):
        stop = GracefulShutdown()
        utterance_queue = queue.Queue()
        config = PerceptionConfig(default_user="Unknown")
        voiceprint = VoiceprintRecognizer(default_user="Unknown")
        return Perception(
            shutdown_signal=stop,
            runtime=runtime,
            utterance_queue=utterance_queue,
            asr=mock_asr,
            voiceprint=voiceprint,
            config=config,
        )

    def test_handle_puts_brain_input_event_and_display_message(
        self, perception, runtime, mock_asr
    ):
        """Perception.handle puts BrainInputEvent and DisplayMessage with ASR result."""
        utterance = make_utterance()
        perception.handle(utterance)

        mock_asr.transcribe.assert_called_once_with(utterance.pcm, utterance.sample_rate)

        assert not runtime.brain_input_queue.empty()
        event = runtime.brain_input_queue.get_nowait()
        assert isinstance(event, BrainInputEvent)
        assert event.type == InputType.AUDIO
        assert event.text == "hello world"
        assert event.user == "Unknown"
        assert event.language == "en"
        assert event.confidence == 0.95

        assert not runtime.display_queue.empty()
        msg = runtime.display_queue.get_nowait()
        assert isinstance(msg, DisplayMessage)
        assert msg.speaker == "Unknown"
        assert msg.text == "hello world"

    def test_handle_skips_display_when_text_empty(self, perception, runtime, mock_asr):
        """When ASR returns empty text, no DisplayMessage is put."""
        mock_asr.transcribe.return_value = ("", None, None)
        utterance = make_utterance()
        perception.handle(utterance)

        assert not runtime.brain_input_queue.empty()
        runtime.brain_input_queue.get_nowait()

        assert runtime.display_queue.empty()
