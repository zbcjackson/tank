"""Playback worker: AudioChunk queue -> sounddevice output (callback mode)."""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

import numpy as np
import sounddevice as sd

from ...core import StopSignal
from .types import AudioChunk

logger = logging.getLogger("Speaker")

# Callback block size: ~10 ms at 24 kHz
PLAYBACK_BLOCKSIZE = 256

# Short fade at start/end to avoid pops (ms). Used for fade-in and fade-out.
FADE_DURATION_MS = 5


class PlaybackWorker(threading.Thread):
    """
    Consumes AudioChunk from queue and plays via sounddevice callback mode.
    Fills outdata from an internal buffer; refills buffer from queue (non-blocking).
    """

    def __init__(
        self,
        *,
        name: str,
        stop_signal: StopSignal,
        audio_chunk_queue: "queue.Queue[AudioChunk | None]",
        daemon: bool = True,
        interrupt_event: Optional[threading.Event] = None,
    ):
        super().__init__(name=name, daemon=daemon)
        self._stop_signal = stop_signal
        self._audio_chunk_queue = audio_chunk_queue
        self._interrupt_event = interrupt_event

    def run(self) -> None:
        logger.info("PlaybackWorker started")
        while not self._stop_signal.is_set():
            try:
                first_chunk = self._audio_chunk_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if first_chunk is None:
                continue
            logger.info(
                "PlaybackWorker: got first chunk sr=%s ch=%s len=%d bytes",
                first_chunk.sample_rate,
                first_chunk.channels,
                len(first_chunk.data),
            )
            self._play_one_stream(first_chunk)
        logger.info("PlaybackWorker stopped")

    def _play_one_stream(self, first_chunk: AudioChunk) -> None:
        sample_rate = first_chunk.sample_rate
        channels = first_chunk.channels
        n_fade = int(sample_rate * FADE_DURATION_MS / 1000)
        stream_ended = [False]
        first_callback_done = [False]
        callback_count = [0]
        queue_ref = self._audio_chunk_queue
        buf_container: list[np.ndarray] = [
            np.frombuffer(first_chunk.data, dtype=np.int16).copy()
        ]
        initial_samples = len(buf_container[0])
        logger.info(
            "PlaybackWorker: starting stream sr=%s ch=%s blocksize=%s initial_samples=%s",
            sample_rate,
            channels,
            PLAYBACK_BLOCKSIZE,
            initial_samples,
        )

        def callback(
            outdata: np.ndarray, frames: int, time_info: object, status: sd.CallbackFlags
        ) -> None:
            if self._interrupt_event is not None and self._interrupt_event.is_set():
                logger.warning("PlaybackWorker: interrupt_event is set in callback, raising CallbackAbort")
                raise sd.CallbackAbort
            if status:
                logger.warning("PlaybackWorker: callback status=%s", status)
            callback_count[0] += 1
            if callback_count[0] == 1:
                logger.info("PlaybackWorker: first callback, frames=%s", frames)

            need = frames * channels
            buf = buf_container[0]
            while len(buf) < need and not stream_ended[0]:
                try:
                    item = queue_ref.get_nowait()
                    if item is None:
                        stream_ended[0] = True
                        break
                    buf = np.concatenate([buf, np.frombuffer(item.data, dtype=np.int16)])
                except queue.Empty:
                    break
            buf_container[0] = buf

            have = min(len(buf), need)
            out = np.zeros((frames, channels), dtype=np.int16)
            out_flat = out.ravel()
            out_flat[:have] = buf[:have]
            buf_container[0] = buf[have:]

            if not first_callback_done[0]:
                first_callback_done[0] = True
                n_apply = min(n_fade, have)
                if n_apply > 0:
                    ramp = np.linspace(0.0, 1.0, n_apply, dtype=np.float64)
                    out_flat[:n_apply] = (
                        out_flat[:n_apply].astype(np.float64) * ramp
                    ).astype(np.int16)

            if stream_ended[0] and len(buf_container[0]) == 0:
                n_apply = min(n_fade, have)
                if n_apply > 0:
                    ramp = np.linspace(1.0, 0.0, n_apply, dtype=np.float64)
                    out_flat[have - n_apply : have] = (
                        out_flat[have - n_apply : have].astype(np.float64) * ramp
                    ).astype(np.int16)
                outdata[:] = out
                logger.info(
                    "PlaybackWorker: stream ended after %d callbacks, raising CallbackStop",
                    callback_count[0],
                )
                raise sd.CallbackStop

            outdata[:] = out

        try:
            logger.info("PlaybackWorker: opening OutputStream")
            with sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="int16",
                blocksize=PLAYBACK_BLOCKSIZE,
                callback=callback,
            ) as stream:
                # Block until callback raises CallbackStop (stream stops); otherwise
                # the with-block would exit immediately and close the stream before playback.
                while stream.active:
                    time.sleep(0.01)
            logger.info("PlaybackWorker: stream closed normally")
        except sd.CallbackAbort:
            logger.info("PlaybackWorker: stream aborted (CallbackAbort)")
        except Exception as e:
            logger.warning("PlaybackWorker: stream error: %s", e, exc_info=True)

