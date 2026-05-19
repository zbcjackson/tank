"""Audio transcoding for WeChat voice messages.

WeChat's iLink Bot API requires voice messages in Tencent SILK format
(SILK V3 with a ``\\x02`` prefix). Edge-TTS and most other engines
produce OGG/Opus or MP3. This module transcodes arbitrary audio bytes
into Tencent SILK via ffmpeg → PCM → pilk.

Returns ``(silk_bytes, duration_ms)`` so the caller can fill in the
``playtime`` field of the voice_item.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

import pilk

logger = logging.getLogger("WeChatAudio")

_SILK_SAMPLE_RATE = 24000  # WeChat voice messages: 24 kHz


class TranscodeError(Exception):
    """Raised when audio transcoding to SILK fails."""


async def transcode_to_silk(audio: bytes) -> tuple[bytes, int]:
    """Transcode arbitrary audio bytes to Tencent SILK.

    Returns (silk_bytes, duration_ms).
    """
    if not shutil.which("ffmpeg"):
        raise TranscodeError("ffmpeg not found on PATH")

    with tempfile.TemporaryDirectory(prefix="wechat-silk-") as tmpdir:
        tmp = Path(tmpdir)
        src_path = tmp / "in.audio"
        pcm_path = tmp / "out.pcm"
        silk_path = tmp / "out.silk"
        src_path.write_bytes(audio)

        # 1) Decode to PCM s16le mono at 24 kHz via ffmpeg.
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-i", str(src_path),
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", str(_SILK_SAMPLE_RATE),
            str(pcm_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not pcm_path.exists():
            raise TranscodeError(
                f"ffmpeg decode failed (rc={proc.returncode}): {stderr.decode('utf-8', 'replace')[:200]}"
            )

        # 2) Encode PCM to Tencent SILK via pilk (runs sync, push to thread).
        await asyncio.to_thread(
            pilk.encode,
            str(pcm_path),
            str(silk_path),
            pcm_rate=_SILK_SAMPLE_RATE,
            tencent=True,
        )
        duration_ms = await asyncio.to_thread(pilk.get_duration, str(silk_path))

        return silk_path.read_bytes(), int(duration_ms)
