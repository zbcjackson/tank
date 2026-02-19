"""Client-side audio capture: Mic -> WebSocket."""

from __future__ import annotations

import asyncio
import logging
import queue
from typing import Awaitable, Callable, Optional

import numpy as np

from ..audio.input.mic import Mic
from ..audio.input.types import AudioFormat, AudioFrame, FrameConfig
from ..core.shutdown import GracefulShutdown

logger = logging.getLogger("AudioCapture")


class ClientAudioCapture:
    """
    Captures audio from local Mic and sends PCM frames to the WebSocket client.

    Reuses the existing Mic class for sounddevice capture.
    """

    def __init__(
        self,
        shutdown: GracefulShutdown,
        audio_format: AudioFormat = AudioFormat(),
        frame_cfg: FrameConfig = FrameConfig(),
        device: Optional[int] = None,
    ):
        self._shutdown = shutdown
        self._frames_queue: queue.Queue[AudioFrame] = queue.Queue(maxsize=400)
        self._mic = Mic(
            stop_signal=shutdown,
            audio_format=audio_format,
            frame_cfg=frame_cfg,
            frames_queue=self._frames_queue,
            device=device,
        )

    def start(self) -> None:
        """Start the Mic capture thread."""
        self._mic.start()

    async def drain_to_ws(
        self, send_audio: Callable[[bytes], Awaitable[None]]
    ) -> None:
        """
        Async loop: drain frames_queue and send as Int16 PCM bytes via WebSocket.

        Args:
            send_audio: async callable that sends bytes over WebSocket.
        """
        while not self._shutdown.is_set():
            try:
                frame = self._frames_queue.get_nowait()
                int16_data = (frame.pcm * 32768.0).astype(np.int16)
                await send_audio(int16_data.tobytes())
            except queue.Empty:
                await asyncio.sleep(0.01)

    def stop(self) -> None:
        """Stop capture and wait for Mic thread."""
        self._mic.join(timeout=2)
