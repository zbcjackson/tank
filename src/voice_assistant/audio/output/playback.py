"""Play PCM stream to audio device."""

from __future__ import annotations

import logging
from typing import AsyncIterator, Callable

import numpy as np
import sounddevice as sd

from .types import AudioChunk

logger = logging.getLogger("Playback")

# Short fade at start/end to avoid pops (ms). Used for fade-in and fade-out.
FADE_DURATION_MS = 5


def _apply_fade_in(frames: np.ndarray, n: int) -> None:
    """Apply linear fade-in to first n samples in-place. n may be 0."""
    if n <= 0 or len(frames) < n:
        return
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float64)
    frames[:n] = (frames[:n].astype(np.float64) * ramp).astype(np.int16)


def _apply_fade_out(frames: np.ndarray, n: int) -> None:
    """Apply linear fade-out to last n samples in-place. n may be 0."""
    if n <= 0 or len(frames) < n:
        return
    ramp = np.linspace(1.0, 0.0, n, dtype=np.float64)
    frames[-n:] = (frames[-n:].astype(np.float64) * ramp).astype(np.int16)


async def play_stream(
    chunk_stream: AsyncIterator[AudioChunk],
    is_interrupted: Callable[[], bool],
) -> None:
    """Consume async chunk stream and write PCM to sounddevice. Stops if is_interrupted().
    Applies short fade-in on first chunk and fade-out on last chunk to avoid pops."""
    stream = None
    pending: AudioChunk | None = None
    first_write = True
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
            if pending is not None:
                frames = np.frombuffer(pending.data, dtype=np.int16).copy()
                if first_write:
                    n_fade = int(pending.sample_rate * FADE_DURATION_MS / 1000)
                    _apply_fade_in(frames, n_fade)
                    first_write = False
                stream.write(frames)
            pending = chunk
        if pending is not None and not is_interrupted() and stream is not None:
            frames = np.frombuffer(pending.data, dtype=np.int16).copy()
            n_fade = int(pending.sample_rate * FADE_DURATION_MS / 1000)
            if first_write:
                _apply_fade_in(frames, n_fade)
            _apply_fade_out(frames, n_fade)
            stream.write(frames)
    finally:
        if stream is not None:
            try:
                if stream.active:
                    stream.stop()
                stream.close()
            except Exception as e:
                logger.warning("Error closing playback stream: %s", e)
