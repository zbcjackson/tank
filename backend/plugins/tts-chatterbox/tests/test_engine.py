"""Test Chatterbox TTS plugin (model deps mocked; never imports the real package)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from tank_contracts.tts import AudioChunk
from tts_chatterbox import create_engine

MODULE = "tts_chatterbox.engine"


def _config(**overrides):
    return {"device": "cpu", "sample_rate": 24000, **overrides}


def test_create_engine():
    assert create_engine(_config()) is not None


def test_emotion_config_defaults():
    engine = create_engine(_config(exaggeration=0.7, cfg_weight=0.3))
    assert engine._exaggeration == 0.7
    assert engine._cfg_weight == 0.3


@pytest.mark.asyncio
async def test_generate_stream_yields_int16_pcm():
    engine = create_engine(_config())
    audio = np.array([0.0, 0.5, -0.5, 1.0], dtype=np.float32)

    mock_model = MagicMock()
    mock_model.sr = 24000
    mock_model.generate.return_value = audio

    with patch.object(engine, "_get_model", return_value=mock_model):
        chunks = [c async for c in engine.generate_stream("Hello", language="en")]

    assert len(chunks) >= 1
    assert all(isinstance(c, AudioChunk) for c in chunks)
    assert all(c.sample_rate == 24000 for c in chunks)
    assert all(len(c.data) % 2 == 0 for c in chunks)
    total = b"".join(c.data for c in chunks)
    expected = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    assert total == expected
    # emotion controls are passed to generate
    _, kwargs = mock_model.generate.call_args
    assert kwargs["exaggeration"] == 0.5
    assert kwargs["cfg_weight"] == 0.5


@pytest.mark.asyncio
async def test_torch_tensor_conversion():
    """A tensor-like object with detach/cpu/numpy is converted correctly."""
    engine = create_engine(_config())
    audio = np.array([0.25, -0.25], dtype=np.float32)

    tensor = MagicMock()
    tensor.detach.return_value = tensor
    tensor.cpu.return_value = tensor
    tensor.numpy.return_value = audio

    mock_model = MagicMock()
    mock_model.sr = 24000
    mock_model.generate.return_value = tensor

    with patch.object(engine, "_get_model", return_value=mock_model):
        chunks = [c async for c in engine.generate_stream("hi", language="en")]

    total = b"".join(c.data for c in chunks)
    assert total == (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


@pytest.mark.asyncio
async def test_interruption():
    engine = create_engine(_config())
    mock_model = MagicMock()
    mock_model.sr = 24000
    mock_model.generate.return_value = np.zeros(8192, dtype=np.float32)

    with patch.object(engine, "_get_model", return_value=mock_model):
        chunks = []
        async for chunk in engine.generate_stream(
            "text", language="en", is_interrupted=lambda: True
        ):
            chunks.append(chunk)

    assert chunks == []


@pytest.mark.asyncio
async def test_missing_dependency_raises_clear_error():
    engine = create_engine(_config())
    with patch(
        f"{MODULE}._load_chatterbox_cls", side_effect=RuntimeError("not installed")
    ):
        with pytest.raises(RuntimeError, match="not installed"):
            [c async for c in engine.generate_stream("hi", language="en")]
