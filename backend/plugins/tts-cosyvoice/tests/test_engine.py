"""Unit tests for CosyVoice TTS plugin."""

from urllib.parse import unquote

import httpx
import pytest
from tank_contracts.tts import AudioChunk, TTSEngine
from tts_cosyvoice import CosyVoiceTTSEngine, create_engine
from tts_cosyvoice.engine import COSYVOICE_SAMPLE_RATE


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_create_engine(cosyvoice_config):
    """create_engine returns a TTSEngine instance."""
    engine = create_engine(cosyvoice_config)
    assert isinstance(engine, TTSEngine)
    assert isinstance(engine, CosyVoiceTTSEngine)


def test_create_engine_defaults():
    """create_engine works with empty config using defaults."""
    engine = create_engine({})
    assert isinstance(engine, TTSEngine)
    assert engine._base_url == "http://localhost:50000"
    assert engine._mode == "sft"
    assert engine._sample_rate == COSYVOICE_SAMPLE_RATE


def test_create_engine_docker_mode():
    """create_engine with docker=True starts server and sets base_url."""
    from unittest.mock import MagicMock, patch

    mock_server = MagicMock()
    mock_server.ensure_running.return_value = "http://localhost:55555"

    with patch("tts_cosyvoice.server.CosyVoiceServer", return_value=mock_server):
        engine = create_engine({"docker": True, "port": 55555})

    assert isinstance(engine, CosyVoiceTTSEngine)
    assert engine._base_url == "http://localhost:55555"
    mock_server.ensure_running.assert_called_once()


def test_create_engine_strips_trailing_slash():
    """Trailing slash on base_url is stripped."""
    engine = create_engine({"base_url": "http://host:9000/"})
    assert engine._base_url == "http://host:9000"


# ---------------------------------------------------------------------------
# Language → speaker ID mapping
# ---------------------------------------------------------------------------


def test_spk_id_for_chinese(cosyvoice_config):
    engine = create_engine(cosyvoice_config)
    assert engine._spk_id_for_language("zh") == "中文女"
    assert engine._spk_id_for_language("zh-CN") == "中文女"
    assert engine._spk_id_for_language("chinese") == "中文女"


def test_spk_id_for_english(cosyvoice_config):
    engine = create_engine(cosyvoice_config)
    assert engine._spk_id_for_language("en") == "英文女"
    assert engine._spk_id_for_language("en-US") == "英文女"
    assert engine._spk_id_for_language("auto") == "英文女"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_pcm(n_bytes: int = 4096) -> bytes:
    """Return deterministic fake PCM bytes."""
    return bytes(range(256)) * (n_bytes // 256) + bytes(range(n_bytes % 256))


async def _collect_chunks(engine, text, **kwargs) -> list[AudioChunk]:
    chunks = []
    async for chunk in engine.generate_stream(text, **kwargs):
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# Streaming — SFT mode (using pytest-httpx)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_stream_sft(cosyvoice_config, httpx_mock):
    """SFT mode streams PCM chunks from the server."""
    pcm_data = _fake_pcm(2048)
    httpx_mock.add_response(
        url="http://localhost:50000/inference_sft",
        method="POST",
        content=pcm_data,
    )
    engine = create_engine(cosyvoice_config)

    chunks = await _collect_chunks(engine, "Hello", language="en")

    assert len(chunks) >= 1
    assert all(isinstance(c, AudioChunk) for c in chunks)
    total_data = b"".join(c.data for c in chunks)
    assert total_data == pcm_data
    assert chunks[0].sample_rate == 22050
    assert chunks[0].channels == 1

    # Verify correct endpoint was called
    request = httpx_mock.get_request()
    assert request.url == "http://localhost:50000/inference_sft"
    assert request.method == "POST"


@pytest.mark.asyncio
async def test_generate_stream_sft_chinese(cosyvoice_config, httpx_mock):
    """Chinese language selects the Chinese speaker ID."""
    httpx_mock.add_response(
        url="http://localhost:50000/inference_sft",
        method="POST",
        content=_fake_pcm(512),
    )
    engine = create_engine(cosyvoice_config)

    chunks = await _collect_chunks(engine, "你好", language="zh-CN")
    assert len(chunks) >= 1

    request = httpx_mock.get_request()
    # Form data is URL-encoded; decode before checking
    body = unquote(request.content.decode("utf-8", errors="replace"))
    assert "中文女" in body


@pytest.mark.asyncio
async def test_generate_stream_custom_voice(cosyvoice_config, httpx_mock):
    """Explicit voice parameter overrides language-based selection."""
    httpx_mock.add_response(
        url="http://localhost:50000/inference_sft",
        method="POST",
        content=_fake_pcm(512),
    )
    engine = create_engine(cosyvoice_config)

    chunks = await _collect_chunks(engine, "Hi", language="en", voice="日文男")
    assert len(chunks) >= 1

    request = httpx_mock.get_request()
    body = unquote(request.content.decode("utf-8", errors="replace"))
    assert "日文男" in body


# ---------------------------------------------------------------------------
# Streaming — zero_shot mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_stream_zero_shot(zero_shot_config, httpx_mock):
    """Zero-shot mode sends prompt_text and prompt_wav."""
    httpx_mock.add_response(
        url="http://localhost:50000/inference_zero_shot",
        method="POST",
        content=_fake_pcm(1024),
    )
    engine = create_engine(zero_shot_config)

    chunks = await _collect_chunks(engine, "Synthesize this", language="en")
    assert len(chunks) >= 1

    request = httpx_mock.get_request()
    assert request.url == "http://localhost:50000/inference_zero_shot"
    body = request.content.decode("utf-8", errors="replace")
    assert "Synthesize this" in body
    assert "Hello, this is a test prompt." in body
    # prompt_wav should be in the multipart body
    assert "prompt.wav" in body


# ---------------------------------------------------------------------------
# Streaming — instruct2 mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_stream_instruct2(tmp_path, httpx_mock):
    """Instruct2 mode sends instruct_text and prompt_wav."""
    prompt_wav = tmp_path / "prompt.wav"
    prompt_wav.write_bytes(b"\x00" * 1600)
    httpx_mock.add_response(
        url="http://localhost:50000/inference_instruct2",
        method="POST",
        content=_fake_pcm(1024),
    )
    engine = create_engine({
        "base_url": "http://localhost:50000",
        "mode": "instruct2",
        "instruct_text": "Speak slowly and gently",
        "prompt_wav_path": str(prompt_wav),
        "sample_rate": 22050,
    })

    chunks = await _collect_chunks(engine, "Hello world", language="en")
    assert len(chunks) >= 1

    request = httpx_mock.get_request()
    assert request.url == "http://localhost:50000/inference_instruct2"
    body = request.content.decode("utf-8", errors="replace")
    assert "Hello world" in body
    assert "Speak slowly and gently" in body
    assert "prompt.wav" in body


# ---------------------------------------------------------------------------
# Interruption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_interruption_stops_stream(cosyvoice_config, httpx_mock):
    """is_interrupted callback stops yielding chunks."""
    # Send a large response so there are multiple chunks
    httpx_mock.add_response(
        url="http://localhost:50000/inference_sft",
        method="POST",
        content=_fake_pcm(32768),
    )
    engine = create_engine(cosyvoice_config)

    call_count = 0

    def is_interrupted():
        return call_count >= 2

    chunks = []
    async for chunk in engine.generate_stream(
        "Long text", language="en", is_interrupted=is_interrupted
    ):
        chunks.append(chunk)
        call_count += 1

    # Should stop after ~2 chunks due to interrupt
    assert 1 <= len(chunks) <= 3


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_error(cosyvoice_config, httpx_mock):
    """Connection error propagates."""
    httpx_mock.add_exception(
        httpx.ConnectError("Connection refused"),
        url="http://localhost:50000/inference_sft",
    )
    engine = create_engine(cosyvoice_config)

    with pytest.raises(httpx.ConnectError):
        await _collect_chunks(engine, "Hello", language="en")


@pytest.mark.asyncio
async def test_http_error(cosyvoice_config, httpx_mock):
    """HTTP 500 raises httpx.HTTPStatusError."""
    httpx_mock.add_response(
        url="http://localhost:50000/inference_sft",
        method="POST",
        status_code=500,
    )
    engine = create_engine(cosyvoice_config)

    with pytest.raises(httpx.HTTPStatusError):
        await _collect_chunks(engine, "Hello", language="en")


# ---------------------------------------------------------------------------
# Empty response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_response(cosyvoice_config, httpx_mock):
    """Server returns no audio data — yields zero chunks."""
    httpx_mock.add_response(
        url="http://localhost:50000/inference_sft",
        method="POST",
        content=b"",
    )
    engine = create_engine(cosyvoice_config)

    chunks = await _collect_chunks(engine, "Hello", language="en")
    assert len(chunks) == 0


# ---------------------------------------------------------------------------
# Custom sample rate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_sample_rate(httpx_mock):
    """Config sample_rate is reflected in AudioChunk."""
    httpx_mock.add_response(
        url="http://localhost:50000/inference_sft",
        method="POST",
        content=_fake_pcm(512),
    )
    engine = create_engine({"sample_rate": 24000})

    chunks = await _collect_chunks(engine, "Hi", language="en")
    assert chunks[0].sample_rate == 24000
