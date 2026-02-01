"""Play PCM stream to audio device."""

from __future__ import annotations

import logging
from typing import AsyncIterator, Callable

import numpy as np
import sounddevice as sd

from .types import AudioChunk

logger = logging.getLogger(__name__)


async def play_stream(
    chunk_stream: AsyncIterator[AudioChunk],
    is_interrupted: Callable[[], bool],
) -> None:
    """Consume async chunk stream and write PCM to sounddevice. Stops if is_interrupted()."""
    stream = None
    try:
        async for chunk in chunk_stream:
            if is_interrupted():
                break
            if stream is None:
                stream = sd.OutputStream(
                    samplerate=chunk.sample_rate,
                    channels=chunk.channels,
                    dtype="int16",
                )
                stream.start()
            frames = np.frombuffer(chunk.data, dtype=np.int16)
            stream.write(frames)
    finally:
        if stream is not None:
            try:
                if stream.active:
                    stream.stop()
                stream.close()
            except Exception as e:
                logger.warning("Error closing playback stream: %s", e)
