"""Speaker: TTS worker and playback worker (callback mode)."""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd

from ...core.events import AudioOutputRequest
from ...core.shutdown import StopSignal
from ...core.worker import QueueWorker
from .playback import FADE_DURATION_MS
from .types import AudioChunk

if TYPE_CHECKING:
    from .tts import TTSEngine

logger = logging.getLogger("Speaker")

# Callback block size: ~10 ms at 24 kHz
PLAYBACK_BLOCKSIZE = 256


class TTSWorker(QueueWorker[AudioOutputRequest]):
    """
    Consumes AudioOutputRequest from queue, generates AudioChunk via TTS,
    puts chunks into audio_chunk_queue and None as end marker.
    """

    def __init__(
        self,
        *,
        name: str,
        stop_signal: StopSignal,
        input_queue: "queue.Queue[AudioOutputRequest]",
        audio_chunk_queue: "queue.Queue[AudioChunk | None]",
        tts_engine: "TTSEngine",
        poll_interval_s: float = 0.1,
    ):
        super().__init__(
            name=name,
            stop_signal=stop_signal,
            input_queue=input_queue,
            poll_interval_s=poll_interval_s,
        )
        self._audio_chunk_queue = audio_chunk_queue
        self._tts_engine = tts_engine
        self._loop: asyncio.AbstractEventLoop | None = None

    def run(self) -> None:
        logger.info("TTSWorker started")
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            super().run()
        finally:
            if self._loop:
                self._loop.close()
        logger.info("TTSWorker stopped")

    def handle(self, item: AudioOutputRequest) -> None:
        logger.info("TTSWorker: got request content=%r language=%s", item.content[:50] if item.content else "", item.language)

        async def generate_chunks() -> None:
            chunk_count = 0
            try:
                chunk_stream = self._tts_engine.generate_stream(
                    item.content,
                    language=item.language,
                    voice=item.voice,
                    is_interrupted=None,
                )
                logger.info("TTSWorker: starting generate_stream")
                async for chunk in chunk_stream:
                    self._audio_chunk_queue.put(chunk)
                    chunk_count += 1
                logger.info("TTSWorker: stream done, put %d chunks, sending end marker", chunk_count)
            except Exception as e:
                logger.exception("TTSWorker: generate_stream failed: %s", e)
                raise
            finally:
                self._audio_chunk_queue.put(None)

        assert self._loop is not None
        self._loop.run_until_complete(generate_chunks())
        logger.info("TTSWorker: handle finished for content=%r", item.content[:50] if item.content else "")


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
    ):
        super().__init__(name=name, daemon=daemon)
        self._stop_signal = stop_signal
        self._audio_chunk_queue = audio_chunk_queue

    def run(self) -> None:
        logger.info("PlaybackWorker started")
        while not self._stop_signal.is_set():
            try:
                first_chunk = self._audio_chunk_queue.get(timeout=0.5)
            except queue.Empty:
                logger.debug("PlaybackWorker: queue empty, waiting...")
                continue
            if first_chunk is None:
                logger.info("PlaybackWorker: got None (end marker only), skipping")
                continue
            logger.info("PlaybackWorker: got first chunk sr=%s ch=%s len=%d bytes", first_chunk.sample_rate, first_chunk.channels, len(first_chunk.data))
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
        logger.info("PlaybackWorker: starting stream sr=%s ch=%s blocksize=%s initial_samples=%s", sample_rate, channels, PLAYBACK_BLOCKSIZE, initial_samples)

        def callback(outdata: np.ndarray, frames: int, time: object, status: sd.CallbackFlags) -> None:
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
                logger.info("PlaybackWorker: stream ended after %d callbacks, raising CallbackStop", callback_count[0])
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
            logger.debug("PlaybackWorker: stream aborted")
        except Exception as e:
            logger.warning("PlaybackWorker: stream error: %s", e, exc_info=True)
