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
        self._prompt_wav_path = config.get("prompt_wav_path", "")
        self._instruct_text = config.get("instruct_text", "")

    def _spk_id_for_language(self, language: str) -> str:
        if language.startswith("zh") or language == "chinese":
            return self._spk_id_zh
        return self._spk_id_en

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """Stream PCM audio from the CosyVoice server."""
        if self._mode == "zero_shot":
            async for chunk in self._generate_zero_shot(text, is_interrupted):
                yield chunk
        elif self._mode == "instruct2":
            async for chunk in self._generate_instruct2(text, is_interrupted):
                yield chunk
        else:
            spk_id = voice or self._spk_id_for_language(language)
            async for chunk in self._generate_sft(text, spk_id, is_interrupted):
                yield chunk

    async def _generate_sft(
        self,
        text: str,
        spk_id: str,
        is_interrupted: Callable[[], bool] | None,
    ) -> AsyncIterator[AudioChunk]:
        """SFT mode: pre-trained speaker ID."""
        url = f"{self._base_url}/inference_sft"
        data = {"tts_text": text, "spk_id": spk_id}

        async for chunk in self._stream_request(url, data=data, is_interrupted=is_interrupted):
            yield chunk

    async def _generate_zero_shot(
        self,
        text: str,
        is_interrupted: Callable[[], bool] | None,
    ) -> AsyncIterator[AudioChunk]:
        """Zero-shot mode: voice cloning from prompt WAV."""
        url = f"{self._base_url}/inference_zero_shot"
        data = {"tts_text": text, "prompt_text": self._prompt_text}

        files = None
        if self._prompt_wav_path:
            wav_bytes = _read_file_bytes(self._prompt_wav_path)
            files = {"prompt_wav": ("prompt.wav", wav_bytes, "application/octet-stream")}

        async for chunk in self._stream_request(
            url, data=data, files=files, is_interrupted=is_interrupted
        ):
            yield chunk

    async def _generate_instruct2(
        self,
        text: str,
        is_interrupted: Callable[[], bool] | None,
    ) -> AsyncIterator[AudioChunk]:
        """Instruct2 mode: voice cloning + style instruction (CosyVoice2)."""
        url = f"{self._base_url}/inference_instruct2"
        data = {"tts_text": text, "instruct_text": self._instruct_text}

        files = None
        if self._prompt_wav_path:
            wav_bytes = _read_file_bytes(self._prompt_wav_path)
            files = {"prompt_wav": ("prompt.wav", wav_bytes, "application/octet-stream")}

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
        timeout = httpx.Timeout(self._timeout_s, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
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
