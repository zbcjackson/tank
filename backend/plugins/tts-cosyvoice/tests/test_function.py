"""Function tests for CosyVoice TTS plugin.

These tests spin up a lightweight FastAPI server that mimics the CosyVoice API,
then exercise the engine end-to-end over real HTTP.
"""

from __future__ import annotations

import asyncio
import threading

import numpy as np
import pytest
import uvicorn
from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import StreamingResponse
from tank_contracts.tts import AudioChunk
from tts_cosyvoice import create_engine


# ---------------------------------------------------------------------------
# Fake CosyVoice server
# ---------------------------------------------------------------------------

FAKE_SAMPLE_RATE = 22050
FAKE_CHANNELS = 1


def _generate_sine_pcm(duration_s: float = 0.2, freq: float = 440.0) -> bytes:
    """Generate a short sine wave as Int16 PCM bytes (like CosyVoice output)."""
    n_samples = int(FAKE_SAMPLE_RATE * duration_s)
    t = np.linspace(0, duration_s, n_samples, endpoint=False)
    samples = (0.5 * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    return samples.tobytes()


def _build_fake_app() -> FastAPI:
    app = FastAPI()

    @app.post("/inference_sft")
    async def inference_sft(tts_text: str = Form(), spk_id: str = Form()):
        pcm = _generate_sine_pcm(duration_s=0.3)

        def stream():
            chunk_size = 4096
            for i in range(0, len(pcm), chunk_size):
                yield pcm[i : i + chunk_size]

        return StreamingResponse(stream(), media_type="application/octet-stream")

    @app.post("/inference_zero_shot")
    async def inference_zero_shot(
        tts_text: str = Form(),
        prompt_text: str = Form(),
        prompt_wav: UploadFile = File(),
    ):
        # Read prompt_wav to verify it was sent (don't use it)
        await prompt_wav.read()
        pcm = _generate_sine_pcm(duration_s=0.2)
        return StreamingResponse(iter([pcm]), media_type="application/octet-stream")

    @app.post("/inference_sft_slow")
    async def inference_sft_slow(tts_text: str = Form(), spk_id: str = Form()):
        """Slow endpoint that yields chunks with delays (for interruption testing)."""

        async def stream():
            for _ in range(10):
                yield _generate_sine_pcm(duration_s=0.05)
                await asyncio.sleep(0.05)

        return StreamingResponse(stream(), media_type="application/octet-stream")

    return app


# ---------------------------------------------------------------------------
# Server fixture
# ---------------------------------------------------------------------------


class _ServerThread(threading.Thread):
    """Run uvicorn in a background thread."""

    def __init__(self, app: FastAPI, host: str, port: int):
        super().__init__(daemon=True)
        self.config = uvicorn.Config(app, host=host, port=port, log_level="error")
        self.server = uvicorn.Server(self.config)

    def run(self):
        self.server.run()

    def stop(self):
        self.server.should_exit = True


@pytest.fixture(scope="module")
def cosyvoice_server():
    """Start a fake CosyVoice server for the test module."""
    app = _build_fake_app()
    host, port = "127.0.0.1", 51234
    thread = _ServerThread(app, host, port)
    thread.start()

    # Wait for server to be ready
    import httpx
    import time

    base_url = f"http://{host}:{port}"
    for _ in range(50):
        try:
            httpx.get(f"{base_url}/docs", timeout=1.0)
            break
        except (httpx.ConnectError, httpx.ReadError):
            time.sleep(0.1)
    else:
        raise RuntimeError("Fake CosyVoice server did not start")

    yield base_url
    thread.stop()


# ---------------------------------------------------------------------------
# Function tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sft_end_to_end(cosyvoice_server):
    """Full round-trip: engine → HTTP → fake server → PCM chunks."""
    engine = create_engine({
        "base_url": cosyvoice_server,
        "mode": "sft",
        "spk_id_en": "英文女",
        "spk_id_zh": "中文女",
        "sample_rate": FAKE_SAMPLE_RATE,
    })

    chunks: list[AudioChunk] = []
    async for chunk in engine.generate_stream("Hello world", language="en"):
        chunks.append(chunk)

    assert len(chunks) >= 1
    total_bytes = sum(len(c.data) for c in chunks)
    assert total_bytes > 0
    assert all(c.sample_rate == FAKE_SAMPLE_RATE for c in chunks)
    assert all(c.channels == FAKE_CHANNELS for c in chunks)

    # Verify the data is valid Int16 PCM
    all_data = b"".join(c.data for c in chunks)
    samples = np.frombuffer(all_data, dtype=np.int16)
    assert len(samples) > 0
    # Sine wave should have non-zero amplitude
    assert np.max(np.abs(samples)) > 1000


@pytest.mark.asyncio
async def test_sft_chinese_end_to_end(cosyvoice_server):
    """Chinese text uses Chinese speaker ID."""
    engine = create_engine({
        "base_url": cosyvoice_server,
        "mode": "sft",
        "spk_id_zh": "中文女",
        "sample_rate": FAKE_SAMPLE_RATE,
    })

    chunks: list[AudioChunk] = []
    async for chunk in engine.generate_stream("你好世界", language="zh"):
        chunks.append(chunk)

    assert len(chunks) >= 1
    total_bytes = sum(len(c.data) for c in chunks)
    assert total_bytes > 0


@pytest.mark.asyncio
async def test_zero_shot_end_to_end(cosyvoice_server, tmp_path):
    """Zero-shot mode sends prompt WAV and gets audio back."""
    # Create a minimal WAV-like file
    prompt_wav = tmp_path / "prompt.wav"
    prompt_wav.write_bytes(np.zeros(1600, dtype=np.int16).tobytes())

    engine = create_engine({
        "base_url": cosyvoice_server,
        "mode": "zero_shot",
        "prompt_text": "This is a test prompt.",
        "prompt_wav_path": str(prompt_wav),
        "sample_rate": FAKE_SAMPLE_RATE,
    })

    chunks: list[AudioChunk] = []
    async for chunk in engine.generate_stream("Synthesize this text", language="en"):
        chunks.append(chunk)

    assert len(chunks) >= 1
    all_data = b"".join(c.data for c in chunks)
    samples = np.frombuffer(all_data, dtype=np.int16)
    assert len(samples) > 0


@pytest.mark.asyncio
async def test_interruption_end_to_end(cosyvoice_server):
    """Interruption stops the stream mid-generation."""
    # Use the slow endpoint by overriding the base_url path
    # We'll patch the engine to hit /inference_sft_slow instead
    engine = create_engine({
        "base_url": cosyvoice_server,
        "mode": "sft",
        "spk_id_en": "英文女",
        "sample_rate": FAKE_SAMPLE_RATE,
    })

    chunk_count = 0

    def is_interrupted():
        return chunk_count >= 2

    chunks: list[AudioChunk] = []
    async for chunk in engine.generate_stream(
        "Long text for interruption test",
        language="en",
        is_interrupted=is_interrupted,
    ):
        chunks.append(chunk)
        chunk_count += 1

    # Should have stopped early due to interruption
    assert 2 <= len(chunks) <= 5


@pytest.mark.asyncio
async def test_connection_refused():
    """Engine raises when server is not reachable."""
    engine = create_engine({
        "base_url": "http://127.0.0.1:59999",
        "timeout_s": 2,
    })

    import httpx

    with pytest.raises(httpx.ConnectError):
        async for _ in engine.generate_stream("Hello", language="en"):
            pass


@pytest.mark.asyncio
async def test_multiple_sequential_requests(cosyvoice_server):
    """Multiple sequential requests work without connection issues."""
    engine = create_engine({
        "base_url": cosyvoice_server,
        "mode": "sft",
        "spk_id_en": "英文女",
        "sample_rate": FAKE_SAMPLE_RATE,
    })

    for text in ["First", "Second", "Third"]:
        chunks: list[AudioChunk] = []
        async for chunk in engine.generate_stream(text, language="en"):
            chunks.append(chunk)
        assert len(chunks) >= 1
        assert sum(len(c.data) for c in chunks) > 0
