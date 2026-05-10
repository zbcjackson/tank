"""TTS plugin contract."""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

# Binary wire format for streamed audio frames.
# Layout (little-endian): magic(2) | sample_rate(4) | channels(2) | pcm_bytes...
# Magic distinguishes framed PCM from legacy raw-PCM frames if a client needs
# to sniff. Keep this in contracts so backend and CLI share one source of truth.
AUDIO_FRAME_MAGIC = 0x544B  # "TK"
AUDIO_FRAME_HEADER_STRUCT = struct.Struct("<HIH")
AUDIO_FRAME_HEADER_SIZE = AUDIO_FRAME_HEADER_STRUCT.size  # 8 bytes


def encode_audio_frame(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    """Prepend the 8-byte header to a PCM payload."""
    return AUDIO_FRAME_HEADER_STRUCT.pack(AUDIO_FRAME_MAGIC, sample_rate, channels) + pcm


def decode_audio_frame(frame: bytes) -> tuple[bytes, int, int]:
    """Parse a framed audio buffer. Returns (pcm, sample_rate, channels).

    Raises ValueError if the frame is too short or the magic does not match.
    """
    if len(frame) < AUDIO_FRAME_HEADER_SIZE:
        raise ValueError(f"frame too short: {len(frame)} < {AUDIO_FRAME_HEADER_SIZE}")
    magic, sample_rate, channels = AUDIO_FRAME_HEADER_STRUCT.unpack_from(frame, 0)
    if magic != AUDIO_FRAME_MAGIC:
        raise ValueError(f"bad audio frame magic: 0x{magic:04x}")
    return frame[AUDIO_FRAME_HEADER_SIZE:], sample_rate, channels


@dataclass(frozen=True)
class AudioChunk:
    """One chunk of PCM audio for playback."""

    data: bytes
    sample_rate: int
    channels: int = 1


class TTSEngine(ABC):
    """Abstract TTS: text → stream of PCM chunks. Implement for each backend."""

    @abstractmethod
    async def generate_stream(
        self,
        text: str,
        *,
        language: str = "auto",
        voice: str | None = None,
        is_interrupted: Callable[[], bool] | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """
        Stream TTS for text. Yields PCM chunks as they are produced.
        If is_interrupted() becomes True, stop yielding and return.
        """
        ...
