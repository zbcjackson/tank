"""Tests for Edge TTS engine (mocked edge_tts and pydub)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.voice_assistant.audio.output.types import AudioChunk
from src.voice_assistant.audio.output.tts import TTSEngine
from src.voice_assistant.audio.output.tts_engine_edge import EdgeTTSEngine
from src.voice_assistant.config.settings import VoiceAssistantConfig


def test_tts_engine_abc_requires_generate_stream():
    """Instantiating a TTSEngine subclass without implementing generate_stream fails early."""
    class IncompleteEngine(TTSEngine):
        pass
    with pytest.raises(TypeError, match="generate_stream"):
        IncompleteEngine()


@pytest.fixture
def config():
    """Minimal config with TTS voices."""
    return VoiceAssistantConfig(
        llm_api_key="test-key",
        tts_voice_zh="zh-CN-XiaoxiaoNeural",
        tts_voice_en="en-US-JennyNeural",
    )


@pytest.mark.asyncio
async def test_generate_stream_yields_pcm_chunks_from_mp3(config):
    """EdgeTTSEngine.generate_stream decodes MP3 chunks and yields AudioChunk."""
    fake_mp3 = b"fake-mp3-bytes"
    fake_pcm = b"\x00\x01" * 100
    mock_communicate = MagicMock()
    async def stream():
        yield {"type": "audio", "data": fake_mp3}
    mock_communicate.stream = stream

    mock_segment = MagicMock()
    mock_segment.raw_data = fake_pcm
    mock_segment.frame_rate = 24000
    mock_segment.channels = 1

    with patch("src.voice_assistant.audio.output.tts_engine_edge.edge_tts") as mock_et:
        mock_et.Communicate.return_value = mock_communicate
        with patch("src.voice_assistant.audio.output.tts_engine_edge.AudioSegment") as mock_as:
            mock_as.from_file.return_value = mock_segment
            engine = EdgeTTSEngine(config)
            chunks = []
            async for c in engine.generate_stream("hello", language="en"):
                chunks.append(c)
            assert len(chunks) == 1
            assert chunks[0].data == fake_pcm
            assert chunks[0].sample_rate == 24000
            assert chunks[0].channels == 1
            mock_et.Communicate.assert_called_once_with("hello", "en-US-JennyNeural")


@pytest.mark.asyncio
async def test_generate_stream_stops_when_interrupted(config):
    """generate_stream stops yielding when is_interrupted returns True."""
    fake_mp3 = b"fake-mp3"
    mock_segment = MagicMock()
    mock_segment.raw_data = b"\x00\x01" * 10
    mock_segment.frame_rate = 24000
    mock_segment.channels = 1

    call_count = [0]
    def is_interrupted():
        call_count[0] += 1
        return call_count[0] > 1

    async def stream():
        yield {"type": "audio", "data": fake_mp3}
        yield {"type": "audio", "data": fake_mp3}

    mock_communicate = MagicMock()
    mock_communicate.stream = stream

    with patch("src.voice_assistant.audio.output.tts_engine_edge.edge_tts") as mock_et:
        mock_et.Communicate.return_value = mock_communicate
        with patch("src.voice_assistant.audio.output.tts_engine_edge.AudioSegment") as mock_as:
            mock_as.from_file.return_value = mock_segment
            engine = EdgeTTSEngine(config)
            chunks = []
            async for c in engine.generate_stream("hi", is_interrupted=is_interrupted):
                chunks.append(c)
            assert len(chunks) == 1
