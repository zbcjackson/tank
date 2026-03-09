"""CosyVoice TTS engine: streams PCM from a CosyVoice FastAPI server."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable

import httpx
from tank_contracts.tts import AudioChunk, TTSEngine

logger = logging.getLogger(__name__)

# CosyVoice server outputs Int16 PCM at this sample rate.
COSYVOICE_SAMPLE_RATE = 22050
COSYVOICE_CHANNELS = 1
# Read 4 KB at a time from the streaming response.
STREAM_CHUNK_BYTES = 4096
# Default HTTP timeout (seconds) — synthesis can be slow on CPU.
DEFAULT_TIMEOUT_S = 120.0

# Mode → server endpoint mapping.
_MODE_ENDPOINTS = {
    "sft": "/inference_sft",
    "zero_shot": "/inference_zero_shot",
    "instruct2": "/inference_instruct2",
}


class CosyVoiceTTSEngine(TTSEngine):
    """TTS engine that delegates to a remote CosyVoice FastAPI server.

    Supports three modes:
      - **sft** (default): uses a pre-trained speaker ID (CosyVoice-300M-SFT).
      - **zero_shot**: clones a voice from a prompt WAV + transcript.
      - **instruct2**: voice cloning + style instruction (CosyVoice2-0.5B).
    """

    def __init__(self, config: dict) -> None:
        self._base_url = config.get("base_url", "http://localhost:50000").rstrip("/")
        self._mode = config.get("mode", "sft")
        self._spk_id_en = config.get("spk_id_en", "英文女")
        self._spk_id_zh = config.get("spk_id_zh", "中文女")
        self._sample_rate = int(config.get("sample_rate", COSYVOICE_SAMPLE_RATE))
        self._timeout_s = float(config.get("timeout_s", DEFAULT_TIMEOUT_S))

        # zero_shot / instruct2 mode settings
        self._prompt_text = config.get("prompt_text", "")
        self._instruct_text = config.get("instruct_text", "")

        # Cache prompt WAV bytes at init (immutable config, avoids re-read per request).
        prompt_wav_path = config.get("prompt_wav_path", "")
        self._prompt_wav_bytes: bytes | None = (
            _read_file_bytes(prompt_wav_path) if prompt_wav_path else None
        )

        self._client: httpx.AsyncClient | None = None

    def _spk_id_for_language(self, language: str) -> str:
        if language.startswith("zh") or language == "chinese":
            return self._spk_id_zh
        return self._spk_id_en

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily create and reuse a single httpx client for connection pooling."""
        if self._client is None or self._client.is_closed:
            timeout = httpx.Timeout(self._timeout_s, connect=10.0)
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    def _build_prompt_files(self) -> dict | None:
        """Build the multipart files dict from cached prompt WAV bytes."""
        if self._prompt_wav_bytes is None:
            return None
        return {"prompt_wav": ("prompt.wav", self._prompt_wav_bytes, "application/octet-stream")}

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """Stream PCM audio from the CosyVoice server."""
        endpoint = _MODE_ENDPOINTS.get(self._mode, _MODE_ENDPOINTS["sft"])
        url = f"{self._base_url}{endpoint}"

        if self._mode == "sft":
            spk_id = voice or self._spk_id_for_language(language)
            data = {"tts_text": text, "spk_id": spk_id}
            files = None
        elif self._mode == "zero_shot":
            data = {"tts_text": text, "prompt_text": self._prompt_text}
            files = self._build_prompt_files()
        else:  # instruct2
            data = {"tts_text": text, "instruct_text": self._instruct_text}
            files = self._build_prompt_files()

        async for chunk in self._stream_request(
            url, data=data, files=files, is_interrupted=is_interrupted
        ):
            yield chunk

    async def _stream_request(
        self,
        url: str,
        *,
        data: dict,
        files: dict | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """POST to the CosyVoice server and yield PCM AudioChunks."""
        client = self._get_client()
        async with client.stream("POST", url, data=data, files=files) as response:
            response.raise_for_status()
            async for raw in response.aiter_bytes(STREAM_CHUNK_BYTES):
                if is_interrupted and is_interrupted():
                    logger.info("CosyVoice: interrupted, stopping stream")
                    break
                yield AudioChunk(
                    data=raw,
                    sample_rate=self._sample_rate,
                    channels=COSYVOICE_CHANNELS,
                )


def _read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()
