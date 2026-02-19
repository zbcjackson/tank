"""Edge TTS backend: only file that imports edge_tts."""

from __future__ import annotations

import asyncio
import logging
import shutil
from io import BytesIO
from typing import AsyncIterator, Callable, Optional

import edge_tts
from pydub import AudioSegment

from ...config.settings import VoiceAssistantConfig
from .types import AudioChunk
from .tts import TTSEngine

logger = logging.getLogger(__name__)

# Edge TTS uses 24kHz 48kbit/s mono MP3. Fallback: accumulate this many bytes
# before pydub decode to reduce chunk-boundary clicks.
MP3_ACCUMULATE_BYTES = 12288  # 12 KB (~2s of audio)
EDGE_TTS_SAMPLE_RATE = 24000
EDGE_TTS_CHANNELS = 1
FFMPEG_READ_CHUNK = 4096


class EdgeTTSEngine(TTSEngine):
    """TTS engine using Microsoft Edge TTS. Decodes MP3 stream to PCM."""

    def __init__(self, config: VoiceAssistantConfig):
        self._config = config

    def _voice_for_language(self, language: str) -> str:
        if language.startswith("zh") or language == "chinese":
            return self._config.tts_voice_zh
        return self._config.tts_voice_en

    async def _generate_stream_ffmpeg(
        self,
        communicate: edge_tts.Communicate,
        is_interrupted: Optional[Callable[[], bool]],
    ) -> AsyncIterator[AudioChunk]:
        """Decode MP3 via ffmpeg stdin→stdout for continuous PCM and minimal latency."""
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "mp3",
            "-i",
            "pipe:0",
            "-f",
            "s16le",
            "-ar",
            str(EDGE_TTS_SAMPLE_RATE),
            "-ac",
            str(EDGE_TTS_CHANNELS),
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        assert proc.stdin is not None and proc.stdout is not None

        async def write_mp3() -> None:
            try:
                async for chunk in communicate.stream():
                    if is_interrupted and is_interrupted():
                        break
                    if chunk.get("type") != "audio":
                        continue
                    data = chunk.get("data")
                    if data:
                        proc.stdin.write(data)
                        await proc.stdin.drain()
            finally:
                proc.stdin.close()

        write_task = asyncio.create_task(write_mp3())
        try:
            while True:
                if is_interrupted and is_interrupted():
                    break
                data = await proc.stdout.read(FFMPEG_READ_CHUNK)
                if not data:
                    break
                yield AudioChunk(
                    data=data,
                    sample_rate=EDGE_TTS_SAMPLE_RATE,
                    channels=EDGE_TTS_CHANNELS,
                )
        finally:
            write_task.cancel()
            try:
                await write_task
            except asyncio.CancelledError:
                pass
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except (asyncio.TimeoutError, ProcessLookupError):
                    proc.kill()

    async def _generate_stream_pydub(
        self,
        communicate: edge_tts.Communicate,
        is_interrupted: Optional[Callable[[], bool]],
    ) -> AsyncIterator[AudioChunk]:
        """Fallback: accumulate MP3 then decode with pydub (fewer boundaries than per-chunk)."""
        buffer = bytearray()
        sample_rate = EDGE_TTS_SAMPLE_RATE
        channels = EDGE_TTS_CHANNELS

        async for chunk in communicate.stream():
            if is_interrupted and is_interrupted():
                break
            if chunk.get("type") != "audio":
                continue
            data = chunk.get("data")
            if not data:
                continue
            buffer.extend(data)

            if len(buffer) >= MP3_ACCUMULATE_BYTES:
                try:
                    seg = AudioSegment.from_file(BytesIO(bytes(buffer)), format="mp3")
                except Exception as e:
                    logger.warning("Failed to decode MP3 chunk: %s", e)
                else:
                    sample_rate = seg.frame_rate
                    channels = seg.channels
                    yield AudioChunk(
                        data=seg.raw_data,
                        sample_rate=sample_rate,
                        channels=channels,
                    )
                    buffer.clear()

        if buffer and not (is_interrupted and is_interrupted()):
            try:
                seg = AudioSegment.from_file(BytesIO(bytes(buffer)), format="mp3")
                yield AudioChunk(
                    data=seg.raw_data,
                    sample_rate=seg.frame_rate,
                    channels=seg.channels,
                )
            except Exception as e:
                logger.warning("Failed to decode final MP3 chunk: %s", e)

    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: Optional[str] = None,
        is_interrupted: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[AudioChunk]:
        voice = voice or self._voice_for_language(language)
        communicate = edge_tts.Communicate(text, voice)

        if shutil.which("ffmpeg"):
            async for chunk in self._generate_stream_ffmpeg(communicate, is_interrupted):
                yield chunk
        else:
            logger.debug("ffmpeg not found, using pydub accumulation")
            async for chunk in self._generate_stream_pydub(communicate, is_interrupted):
                yield chunk
