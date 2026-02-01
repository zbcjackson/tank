"""Tests for Edge TTS engine: separate coverage for ffmpeg and pydub decode paths."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.voice_assistant.audio.output.tts import TTSEngine
from src.voice_assistant.audio.output.tts_engine_edge import (
    EdgeTTSEngine,
    EDGE_TTS_SAMPLE_RATE,
    EDGE_TTS_CHANNELS,
)
from src.voice_assistant.config.settings import VoiceAssistantConfig

MODULE = "src.voice_assistant.audio.output.tts_engine_edge"


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


def make_communicate_mock(mp3_chunks):
    """Mock edge_tts.Communicate whose stream yields type=audio chunks."""
    async def stream():
        for data in mp3_chunks:
            yield {"type": "audio", "data": data}
    mock = MagicMock()
    mock.stream = stream
    return mock


def make_pydub_segment(raw_data, sample_rate=24000, channels=1):
    """Mock pydub AudioSegment for from_file return value."""
    seg = MagicMock()
    seg.raw_data = raw_data
    seg.frame_rate = sample_rate
    seg.channels = channels
    return seg


def make_ffmpeg_mock_proc(stdout_chunks):
    """Mock subprocess: stdin write/drain/close; stdout.read returns chunks then b''."""
    proc = MagicMock()
    proc.returncode = None
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock(return_value=None)
    proc.stdin.close = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.read = AsyncMock(side_effect=list(stdout_chunks) + [b""])
    proc.terminate = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    proc.kill = MagicMock()
    return proc


async def collect_chunks(engine, text, **kwargs):
    """Run engine.generate_stream(text, **kwargs) and return list of AudioChunk."""
    chunks = []
    async for c in engine.generate_stream(text, **kwargs):
        chunks.append(c)
    return chunks


def make_interrupt_after(threshold):
    """Return is_interrupted callable that returns True after (threshold + 1) calls."""
    call_count = [0]
    def is_interrupted():
        call_count[0] += 1
        return call_count[0] > threshold
    return is_interrupted


# ---- Pydub path (shutil.which("ffmpeg") returns None) ----


@pytest.mark.asyncio
async def test_generate_stream_pydub_yields_pcm_chunks(config):
    """When ffmpeg is absent, generate_stream uses pydub and yields decoded AudioChunk."""
    fake_mp3, fake_pcm = b"fake-mp3-bytes", b"\x00\x01" * 100
    communicate = make_communicate_mock([fake_mp3])
    segment = make_pydub_segment(fake_pcm)

    with patch(f"{MODULE}.shutil.which", return_value=None), \
         patch(f"{MODULE}.edge_tts") as mock_et, \
         patch(f"{MODULE}.AudioSegment") as mock_as:
        mock_et.Communicate.return_value = communicate
        mock_as.from_file.return_value = segment
        engine = EdgeTTSEngine(config)
        chunks = await collect_chunks(engine, "hello", language="en")

    assert len(chunks) == 1
    assert chunks[0].data == fake_pcm
    assert chunks[0].sample_rate == 24000
    assert chunks[0].channels == 1
    mock_et.Communicate.assert_called_once_with("hello", "en-US-JennyNeural")


@pytest.mark.asyncio
async def test_generate_stream_pydub_stops_when_interrupted(config):
    """Pydub path stops yielding when is_interrupted returns True."""
    fake_mp3 = b"fake-mp3"
    segment = make_pydub_segment(b"\x00\x01" * 10)
    communicate = make_communicate_mock([fake_mp3, fake_mp3])
    is_interrupted = make_interrupt_after(1)

    with patch(f"{MODULE}.shutil.which", return_value=None), \
         patch(f"{MODULE}.edge_tts") as mock_et, \
         patch(f"{MODULE}.AudioSegment") as mock_as, \
         patch(f"{MODULE}.MP3_ACCUMULATE_BYTES", 8):
        mock_et.Communicate.return_value = communicate
        mock_as.from_file.return_value = segment
        engine = EdgeTTSEngine(config)
        chunks = await collect_chunks(engine, "hi", is_interrupted=is_interrupted)

    assert len(chunks) == 1


# ---- Ffmpeg path (shutil.which("ffmpeg") returns path) ----


@pytest.mark.asyncio
async def test_generate_stream_ffmpeg_yields_pcm_chunks(config):
    """When ffmpeg is present, generate_stream uses ffmpeg subprocess and yields PCM from stdout."""
    fake_pcm = b"\x00\x01" * 200
    communicate = make_communicate_mock([b"mp3-data"])
    mock_proc = make_ffmpeg_mock_proc([fake_pcm])

    with patch(f"{MODULE}.shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch(f"{MODULE}.edge_tts") as mock_et, \
         patch(f"{MODULE}.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
        mock_et.Communicate.return_value = communicate
        engine = EdgeTTSEngine(config)
        chunks = await collect_chunks(engine, "hello", language="en")

    assert len(chunks) == 1
    assert chunks[0].data == fake_pcm
    assert chunks[0].sample_rate == EDGE_TTS_SAMPLE_RATE
    assert chunks[0].channels == EDGE_TTS_CHANNELS
    mock_et.Communicate.assert_called_once_with("hello", "en-US-JennyNeural")


@pytest.mark.asyncio
async def test_generate_stream_ffmpeg_stops_when_interrupted(config):
    """Ffmpeg path stops yielding when is_interrupted returns True."""
    fake_pcm = b"\x00\x01" * 100
    communicate = make_communicate_mock([b"mp3"])
    is_interrupted = make_interrupt_after(1)
    mock_proc = make_ffmpeg_mock_proc([fake_pcm])

    with patch(f"{MODULE}.shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch(f"{MODULE}.edge_tts") as mock_et, \
         patch(f"{MODULE}.asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
        mock_et.Communicate.return_value = communicate
        engine = EdgeTTSEngine(config)
        chunks = await collect_chunks(engine, "hi", is_interrupted=is_interrupted)

    assert len(chunks) == 1
