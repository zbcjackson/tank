"""Test ElevenLabs ASR plugin."""

import numpy as np
import pytest
from unittest.mock import patch
from asr_elevenlabs import create_engine


def test_create_engine():
    """Test plugin factory function."""
    config = {
        "api_key": "test_key",
        "language_code": "en",
        "sample_rate": 16000,
    }

    with patch("asr_elevenlabs.engine.ElevenLabsASREngine._start_background_loop"):
        engine = create_engine(config)
        assert engine is not None


@pytest.mark.asyncio
async def test_process_pcm_returns_partial():
    """Test that process_pcm returns partial transcripts."""
    config = {
        "api_key": "test_key",
        "sample_rate": 16000,
    }

    with patch("asr_elevenlabs.engine.ElevenLabsASREngine._start_background_loop"):
        engine = create_engine(config)

        # Simulate partial transcript state
        engine._partial_text = "hello world"
        engine._has_endpoint = False

        # Generate test audio
        audio = np.zeros(1600, dtype=np.float32)

        text, is_endpoint = engine.process_pcm(audio)
        assert text == "hello world"
        assert is_endpoint is False


@pytest.mark.asyncio
async def test_process_pcm_returns_committed():
    """Test that process_pcm returns committed transcripts with endpoint."""
    config = {
        "api_key": "test_key",
        "sample_rate": 16000,
    }

    with patch("asr_elevenlabs.engine.ElevenLabsASREngine._start_background_loop"):
        engine = create_engine(config)

        # Simulate committed transcript state
        engine._committed_text = "final text"
        engine._has_endpoint = True

        # Generate test audio
        audio = np.zeros(1600, dtype=np.float32)

        text, is_endpoint = engine.process_pcm(audio)
        assert text == "final text"
        assert is_endpoint is True

        # State should be cleared after reading
        assert engine._committed_text == ""
        assert engine._has_endpoint is False


def test_reset():
    """Test that reset clears internal state."""
    config = {
        "api_key": "test_key",
        "sample_rate": 16000,
    }

    with patch("asr_elevenlabs.engine.ElevenLabsASREngine._start_background_loop"):
        engine = create_engine(config)

        # Set some state
        engine._partial_text = "partial"
        engine._committed_text = "committed"
        engine._has_endpoint = True

        # Reset
        engine.reset()

        # State should be cleared
        assert engine._partial_text == ""
        assert engine._committed_text == ""
        assert engine._has_endpoint is False
