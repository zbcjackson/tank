"""Test Edge TTS plugin."""

import pytest
from tank_contracts.tts import AudioChunk, TTSEngine
from tts_edge import create_engine


def test_create_engine():
    """Test plugin factory function."""
    config = {
        "voice_en": "en-US-JennyNeural",
        "voice_zh": "zh-CN-XiaoxiaoNeural",
    }
    engine = create_engine(config)
    assert isinstance(engine, TTSEngine)


@pytest.mark.asyncio
async def test_generate_stream_basic():
    """Test TTS generation produces audio chunks."""
    config = {
        "voice_en": "en-US-JennyNeural",
        "voice_zh": "zh-CN-XiaoxiaoNeural",
    }
    engine = create_engine(config)

    chunks = []
    async for chunk in engine.generate_stream("Hello", language="en"):
        chunks.append(chunk)
        assert isinstance(chunk, AudioChunk)
        assert chunk.sample_rate == 24000
        assert chunk.channels == 1
        assert len(chunk.data) > 0
        if len(chunks) >= 3:  # Just test first few chunks
            break

    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_interruption():
    """Test that is_interrupted callback stops generation."""
    config = {
        "voice_en": "en-US-JennyNeural",
        "voice_zh": "zh-CN-XiaoxiaoNeural",
    }
    engine = create_engine(config)

    interrupted = False

    def is_interrupted():
        return interrupted

    chunks = []
    async for chunk in engine.generate_stream(
        "This is a long sentence that should generate many audio chunks for testing interruption",
        language="en",
        is_interrupted=is_interrupted,
    ):
        chunks.append(chunk)
        if len(chunks) == 2:
            interrupted = True  # Interrupt after 2 chunks

    # Should stop soon after interrupt (allow a few more chunks due to buffering)
    assert 2 <= len(chunks) <= 5


@pytest.mark.asyncio
async def test_chinese_voice_selection():
    """Test that Chinese text uses Chinese voice."""
    config = {
        "voice_en": "en-US-JennyNeural",
        "voice_zh": "zh-CN-XiaoxiaoNeural",
    }
    engine = create_engine(config)

    chunks = []
    async for chunk in engine.generate_stream("你好", language="zh"):
        chunks.append(chunk)
        if len(chunks) >= 2:
            break

    assert len(chunks) > 0
