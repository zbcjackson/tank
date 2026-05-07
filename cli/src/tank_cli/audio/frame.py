"""Wire format for streamed audio frames from the backend.

Must match ``tank_contracts.tts.encode_audio_frame`` on the backend side.

Layout (little-endian): magic(2) | sample_rate(4) | channels(2) | pcm_bytes...

The codec lives here (duplicated from ``tank_contracts``) so the CLI does not
need to take a workspace dependency on the backend package.
"""

from __future__ import annotations

import struct

AUDIO_FRAME_MAGIC = 0x544B  # "TK"
AUDIO_FRAME_HEADER_STRUCT = struct.Struct("<HIH")
AUDIO_FRAME_HEADER_SIZE = AUDIO_FRAME_HEADER_STRUCT.size  # 8 bytes


def encode_audio_frame(pcm: bytes, sample_rate: int, channels: int) -> bytes:
    """Prepend the 8-byte header to a PCM payload."""
    return AUDIO_FRAME_HEADER_STRUCT.pack(AUDIO_FRAME_MAGIC, sample_rate, channels) + pcm


def decode_audio_frame(frame: bytes) -> tuple[bytes, int, int]:
    """Parse a framed audio buffer. Returns (pcm, sample_rate, channels)."""
    if len(frame) < AUDIO_FRAME_HEADER_SIZE:
        raise ValueError(f"frame too short: {len(frame)} < {AUDIO_FRAME_HEADER_SIZE}")
    magic, sample_rate, channels = AUDIO_FRAME_HEADER_STRUCT.unpack_from(frame, 0)
    if magic != AUDIO_FRAME_MAGIC:
        raise ValueError(f"bad audio frame magic: 0x{magic:04x}")
    return frame[AUDIO_FRAME_HEADER_SIZE:], sample_rate, channels
