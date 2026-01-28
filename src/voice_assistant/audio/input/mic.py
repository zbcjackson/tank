"""Microphone audio capture."""

from __future__ import annotations

import threading
import queue
import time
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd

from ...core.shutdown import StopSignal

from .types import AudioFormat, FrameConfig

logger = logging.getLogger(__name__)


@dataclass
class AudioFrame:
    """Single audio frame from microphone."""
    pcm: np.ndarray          # shape: (n_samples,) float32
    sample_rate: int
    timestamp_s: float


class Mic(threading.Thread):
    """
    Continuously captures microphone audio and pushes AudioFrame into frames_queue.

    Important: keep callback/lightweight; no VAD/ASR here.
    """

    def __init__(
        self,
        stop_signal: StopSignal,
        audio_format: AudioFormat,
        frame_cfg: FrameConfig,
        frames_queue: queue.Queue[AudioFrame],
        device: Optional[int] = None,
    ):
        super().__init__(name="MicThread", daemon=True)
        self._stop_signal = stop_signal
        self._audio_format = audio_format
        self._frame_cfg = frame_cfg
        self._frames_queue = frames_queue
        self._device = device

    def run(self) -> None:
        """Start microphone capture loop."""
        # Calculate blocksize (number of samples per frame)
        blocksize = int(self._audio_format.sample_rate * self._frame_cfg.frame_ms / 1000)
        
        # Convert dtype string to numpy dtype
        dtype_map = {
            "float32": np.float32,
            "int16": np.int16,
            "int32": np.int32,
        }
        dtype = dtype_map.get(self._audio_format.dtype, np.float32)
        
        def audio_callback(indata, frames, time_info, status):
            """Callback function for sounddevice audio stream."""
            if status:
                logger.warning(f"Audio callback status: {status}")
            
            # Convert to float32 and flatten to 1D array
            # indata shape is (frames, channels), we take first channel
            if indata.shape[1] > 0:
                pcm = indata[:, 0].astype(np.float32)
            else:
                pcm = indata.flatten().astype(np.float32)
            
            # Create AudioFrame
            frame = AudioFrame(
                pcm=pcm,
                sample_rate=self._audio_format.sample_rate,
                timestamp_s=time.time()
            )
            
            # Put frame into queue (non-blocking)
            try:
                self._frames_queue.put_nowait(frame)
            except queue.Full:
                logger.warning("Frames queue is full, dropping audio frame")
        
        try:
            with sd.InputStream(
                callback=audio_callback,
                samplerate=self._audio_format.sample_rate,
                channels=self._audio_format.channels,
                blocksize=blocksize,
                dtype=dtype,
                device=self._device,
            ):
                # Keep running until stop signal is set
                while not self._stop_signal.is_set():
                    time.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in microphone capture: {e}", exc_info=True)
        finally:
            logger.info("Microphone capture stopped")
