"""Test Kokoro TTS plugin (model deps mocked; never imports the real package)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from tank_contracts.tts import AudioChunk
from tts_kokoro import create_engine

MODULE = "tts_kokoro.engine"


def _config(**overrides):
    return {"default_voice": "af_heart", "sample_rate": 24000, **overrides}


def _fake_pipeline(audio):
    """A KPipeline-like callable yielding (gs, ps, audio) tuples."""
    pipeline = MagicMock()
    pipeline.return_value = [("gs", "ps", audio)]
    return pipeline


def test_create_engine():
    assert create_engine(_config()) is not None


def test_lang_code_mapping():
    engine = create_engine(_config())
    assert engine._lang_code("en") == "a"
    assert engine._lang_code("zh-CN") == "z"
    assert engine._lang_code("auto") == "a"
    assert engine._lang_code("xx") == "a"


def test_voice_selection():
    engine = create_engine(_config(voices={"en": "af_heart", "zh": "zf_xiaobei"}))
    assert engine._voice_for_language("en") == "af_heart"
    assert engine._voice_for_language("zh") == "zf_xiaobei"


@pytest.mark.asyncio
async def test_generate_stream_yields_int16_pcm():
    engine = create_engine(_config())
    audio = np.array([0.0, 0.5, -0.5, 1.0], dtype=np.float32)
    fake = _fake_pipeline(audio)

    with patch.object(engine, "_get_pipeline", return_value=fake):
        chunks = [c async for c in engine.generate_stream("Hello", language="en")]

    assert len(chunks) >= 1
    assert all(isinstance(c, AudioChunk) for c in chunks)
    assert all(c.sample_rate == 24000 for c in chunks)
    # every chunk is int16-aligned
    assert all(len(c.data) % 2 == 0 for c in chunks)
    total = b"".join(c.data for c in chunks)
    expected = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    assert total == expected
    fake.assert_called_once()


@pytest.mark.asyncio
async def test_interruption_stops_before_synth_output():
    engine = create_engine(_config())
    audio = np.zeros(8192, dtype=np.float32)
    fake = _fake_pipeline(audio)

    with patch.object(engine, "_get_pipeline", return_value=fake):
        chunks = []
        async for chunk in engine.generate_stream(
            "text", language="en", is_interrupted=lambda: True
        ):
            chunks.append(chunk)

    assert chunks == []


@pytest.mark.asyncio
async def test_missing_dependency_raises_clear_error():
    """When kokoro isn't installed, the lazy loader raises a helpful error."""
    engine = create_engine(_config())
    with patch(f"{MODULE}._load_kpipeline_cls", side_effect=RuntimeError("not installed")):
        with pytest.raises(RuntimeError, match="not installed"):
            [c async for c in engine.generate_stream("hi", language="en")]
