"""Test Edge TTS plugin with a fake provider and real MP3 decoding."""

import subprocess

import pytest
from tank_contracts.tts import AudioChunk, TTSEngine
from tts_edge import create_engine
from tts_edge.engine import _align_int16


@pytest.fixture(scope="module")
def mp3_audio():
    return subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-b:a",
            "48k",
            "-f",
            "mp3",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout


@pytest.fixture
def provider(monkeypatch, mp3_audio):
    calls = []

    class Communicate:
        def __init__(self, text, voice):
            calls.append((text, voice))

        async def stream(self):
            yield {"type": "WordBoundary"}
            for offset in range(0, len(mp3_audio), 1024):
                yield {"type": "audio", "data": mp3_audio[offset : offset + 1024]}

    monkeypatch.setattr("tts_edge.engine.edge_tts.Communicate", Communicate)
    return calls


class TestAlignInt16:
    def test_even_chunk_passes_through_unchanged(self):
        aligned, leftover = _align_int16(b"\x01\x02\x03\x04", b"")
        assert aligned == b"\x01\x02\x03\x04"
        assert leftover == b""

    def test_odd_chunk_defers_last_byte(self):
        aligned, leftover = _align_int16(b"\x01\x02\x03", b"")
        assert aligned == b"\x01\x02"
        assert leftover == b"\x03"

    def test_leftover_joins_next_chunk(self):
        aligned, leftover = _align_int16(b"\x04\x05", b"\x03")
        assert aligned == b"\x03\x04"
        assert leftover == b"\x05"

    def test_empty_chunk_with_odd_leftover_is_empty(self):
        aligned, leftover = _align_int16(b"", b"\x03")
        assert aligned == b""
        assert leftover == b"\x03"


def test_create_engine():
    """Test plugin factory function."""
    config = {
        "voice_en": "en-US-JennyNeural",
        "voice_zh": "zh-CN-XiaoxiaoNeural",
    }
    engine = create_engine(config)
    assert isinstance(engine, TTSEngine)


@pytest.mark.asyncio
async def test_generate_stream_basic(provider):
    """Test TTS generation produces audio chunks."""
    config = {
        "voice_en": "en-US-JennyNeural",
        "voice_zh": "zh-CN-XiaoxiaoNeural",
    }
    engine = create_engine(config)

    chunks = []
    stream = engine.generate_stream("Hello", language="en")
    try:
        async for chunk in stream:
            chunks.append(chunk)
            assert isinstance(chunk, AudioChunk)
            assert chunk.sample_rate == 24000
            assert chunk.channels == 1
            assert len(chunk.data) > 0 and len(chunk.data) % 2 == 0
            if len(chunks) >= 3:
                break
    finally:
        await stream.aclose()

    assert len(chunks) > 0
    assert provider == [("Hello", "en-US-JennyNeural")]


@pytest.mark.asyncio
async def test_interruption(provider):
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
    stream = engine.generate_stream(
        "This is a long sentence that should generate many audio chunks for testing interruption",
        language="en",
        is_interrupted=is_interrupted,
    )
    try:
        async for chunk in stream:
            chunks.append(chunk)
            if len(chunks) == 2:
                interrupted = True
    finally:
        await stream.aclose()

    # Should stop soon after interrupt (allow a few more chunks due to buffering)
    assert 2 <= len(chunks) <= 5


@pytest.mark.asyncio
async def test_chinese_voice_selection(provider):
    """Test that Chinese text uses Chinese voice."""
    config = {
        "voice_en": "en-US-JennyNeural",
        "voice_zh": "zh-CN-XiaoxiaoNeural",
    }
    engine = create_engine(config)

    chunks = []
    stream = engine.generate_stream("你好", language="zh")
    try:
        async for chunk in stream:
            chunks.append(chunk)
            if len(chunks) >= 2:
                break
    finally:
        await stream.aclose()

    assert len(chunks) > 0
    assert provider == [("你好", "zh-CN-XiaoxiaoNeural")]
