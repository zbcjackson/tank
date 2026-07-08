"""Test AssemblyAI ASR plugin."""

from unittest.mock import patch

import numpy as np

MODULE = "asr_assemblyai.engine"


def _make_engine(**overrides):
    """Create an engine without starting the background WebSocket loop."""
    config = {"api_key": "test_key", "sample_rate": 16000, **overrides}
    with patch(f"{MODULE}.AssemblyAIASREngine._start_background_loop"):
        from asr_assemblyai import create_engine

        return create_engine(config)


def test_create_engine_factory():
    """Factory maps config values to the engine constructor."""
    with patch(f"{MODULE}.AssemblyAIASREngine.__init__", return_value=None) as mock_init:
        from asr_assemblyai import create_engine

        create_engine({
            "api_key": "my_key",
            "speech_model": "universal-3-5-pro",
            "sample_rate": 8000,
        })
        mock_init.assert_called_once_with(
            api_key="my_key", speech_model="universal-3-5-pro", sample_rate=8000
        )


def test_sample_rate_property():
    engine = _make_engine(sample_rate=8000)
    assert engine.sample_rate == 8000


def test_supports_streaming_default():
    """AssemblyAI is a streaming engine."""
    engine = _make_engine()
    stream = engine.create_stream()
    assert stream.supports_streaming is True


def test_partial_turn_updates_partial():
    """A non-final Turn message updates the partial transcript."""
    engine = _make_engine()
    engine._start_session()

    engine._handle_message({
        "type": "Turn",
        "end_of_turn": False,
        "transcript": "hello",
    })

    audio = np.zeros(1600, dtype=np.float32)
    assert engine._process_pcm(audio) == "hello"


def test_end_of_turn_commits_text():
    """An end_of_turn Turn message promotes text to committed."""
    engine = _make_engine()
    engine._start_session()

    engine._handle_message({
        "type": "Turn",
        "end_of_turn": True,
        "transcript": "hello world",
    })

    final = engine._stop_session()
    assert final == "hello world"


def test_process_pcm_without_session_returns_empty():
    engine = _make_engine()
    audio = np.zeros(1600, dtype=np.float32)
    assert engine._process_pcm(audio) == ""


def test_detected_language_is_none():
    engine = _make_engine()
    stream = engine.create_stream()
    assert stream.detected_language is None
