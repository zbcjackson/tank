"""Silero VAD-based voice activity detection."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import numpy as np
from silero_vad import load_silero_vad, VADIterator

from .types import SegmenterConfig

logger = logging.getLogger(__name__)


class VADStatus(Enum):
    """Voice activity detection status."""
    NO_SPEECH = auto()      # No speech detected, no utterance
    IN_SPEECH = auto()      # Speech detected, accumulating frames
    END_SPEECH = auto()     # Speech ended, utterance finalized


@dataclass(frozen=True)
class VADResult:
    """Result from VAD processing."""
    status: VADStatus
    utterance_pcm: Optional[np.ndarray] = None
    sample_rate: Optional[int] = None
    started_at_s: Optional[float] = None
    ended_at_s: Optional[float] = None


class SileroVAD:
    """
    Silero VAD-based voice activity detector.
    
    Uses Silero VAD model (ONNX) to detect speech and segment utterances.
    Manages internal state for continuous processing.
    """

    def __init__(
        self,
        cfg: SegmenterConfig,
        sample_rate: int = 16000,
    ):
        """
        Initialize SileroVAD.
        
        Args:
            cfg: Segmenter configuration
            sample_rate: Audio sample rate (default: 16000 Hz)
        """
        self._cfg = cfg
        self._sample_rate = sample_rate
        
        # State tracking
        self._in_speech = False
        self._speech_pcm_parts: list[np.ndarray] = []
        self._speech_started_at_s: Optional[float] = None
        self._last_voice_at_s: Optional[float] = None  # For silence timeout tracking
        
        # Chunk buffering (for 512-sample chunks required by silero-vad)
        self._chunk_buffer = np.array([], dtype=np.float32)
        self._chunk_size = 512  # Required chunk size for 16kHz
        self._last_chunk_has_voice = False  # Track last processed chunk's voice state
        
        # Pre-roll buffer (ring buffer for audio before speech start)
        # Calculate number of frames: pre_roll_ms / frame_ms (assuming 20ms frames)
        frame_ms = 20  # Standard frame size
        pre_roll_frames = int(cfg.pre_roll_ms / frame_ms)
        self._pre_roll_buffer: deque[np.ndarray] = deque(maxlen=pre_roll_frames)
        
        # Model initialization - load immediately, fail fast if not available
        model = load_silero_vad(onnx=True, opset_version=16)
        # Pass speech_threshold to VADIterator, which will handle threshold comparison internally
        self._vad_iterator = VADIterator(
            model,
            threshold=cfg.speech_threshold,
            sampling_rate=self._sample_rate
        )

    def _process_chunk(self, chunk: np.ndarray) -> bool:
        """
        Process a 512-sample chunk and return speech detection result.
        
        Args:
            chunk: Audio chunk (512 samples for 16kHz)
            
        Returns:
            True if speech detected, False otherwise
        """
        if len(chunk) < self._chunk_size:
            # Partial chunk, use energy threshold
            energy = np.sqrt(np.mean(chunk ** 2))
            return energy > 0.01
        
        # Full chunk, use model inference
        # VADIterator already handles threshold comparison internally
        # Returns {'start'}/{'end'} when speech detected, None otherwise
        result = self._vad_iterator(chunk, return_seconds=False)
        return result is not None  # True if speech detected, False otherwise

    def _process_pending_chunks(self) -> Optional[bool]:
        """
        Process any complete chunks in the buffer.
        
        Returns:
            True if speech detected in processed chunks, False if no speech,
            None if no complete chunks to process
        """
        has_voice = None
        
        # Process all complete chunks
        while len(self._chunk_buffer) >= self._chunk_size:
            chunk = self._chunk_buffer[:self._chunk_size]
            self._chunk_buffer = self._chunk_buffer[self._chunk_size:]
            
            # Process chunk
            chunk_has_voice = self._process_chunk(chunk)
            self._last_chunk_has_voice = chunk_has_voice
            
            if has_voice is None:
                has_voice = chunk_has_voice
            else:
                has_voice = has_voice or chunk_has_voice
        
        return has_voice

    def _has_voice_activity(self, pcm: np.ndarray) -> bool:
        """
        Detect voice activity by buffering frames into chunks.
        
        Accumulates frames until chunk size (512 samples) is reached,
        then processes the chunk.
        """
        # Add frame to chunk buffer
        self._chunk_buffer = np.concatenate([self._chunk_buffer, pcm])
        
        # Process any complete chunks
        chunk_result = self._process_pending_chunks()
        
        if chunk_result is not None:
            # Processed at least one complete chunk
            return chunk_result
        
        # No complete chunks yet, use energy threshold for partial buffer
        if len(self._chunk_buffer) > 0:
            energy = np.sqrt(np.mean(self._chunk_buffer ** 2))
            return energy > 0.01
        
        # Fallback to last known state
        return self._last_chunk_has_voice

    def process_frame(
        self,
        pcm: np.ndarray,
        timestamp_s: float,
    ) -> VADResult:
        """
        Process a single audio frame.
        
        Args:
            pcm: Audio frame PCM data (float32, mono)
            timestamp_s: Frame timestamp (seconds, frame end time)
            
        Returns:
            VADResult with status and optional utterance data
        """
        # Always update pre-roll buffer
        self._pre_roll_buffer.append(pcm.copy())
        
        # Check silence timeout BEFORE processing voice activity
        # This ensures we detect silence even if chunk buffering delays voice detection
        if self._in_speech and self._last_voice_at_s is not None:
            silence_duration_ms = (timestamp_s - self._last_voice_at_s) * 1000.0
            if silence_duration_ms >= self._cfg.min_silence_ms:
                # Check min_speech_ms - discard if too short
                if self._speech_started_at_s is not None:
                    speech_duration_ms = (self._last_voice_at_s - self._speech_started_at_s) * 1000.0
                    if speech_duration_ms < self._cfg.min_speech_ms:
                        # Discard short utterance
                        self._in_speech = False
                        self._speech_pcm_parts = []
                        self._speech_started_at_s = None
                        self._last_voice_at_s = None
                        return VADResult(status=VADStatus.NO_SPEECH)
                
                # Finalize utterance
                utterance_pcm = np.concatenate(self._speech_pcm_parts) if self._speech_pcm_parts else np.array([], dtype=np.float32)
                started_at = self._speech_started_at_s or timestamp_s
                ended_at = self._last_voice_at_s or timestamp_s
                
                # Reset state
                self._in_speech = False
                self._speech_pcm_parts = []
                self._speech_started_at_s = None
                self._last_voice_at_s = None

                logger.info("VAD speech process ended at %.3f, speech started_at_s=%.3f, ended_at_s=%.3f", time.time(), started_at, ended_at)
                return VADResult(
                    status=VADStatus.END_SPEECH,
                    utterance_pcm=utterance_pcm,
                    sample_rate=self._sample_rate,
                    started_at_s=started_at,
                    ended_at_s=ended_at,
                )

        has_voice = self._has_voice_activity(pcm)
        
        if not self._in_speech:
            if not has_voice:
                return VADResult(status=VADStatus.NO_SPEECH)
            
            # Voice start detected - include pre-roll in utterance
            self._in_speech = True
            self._speech_started_at_s = timestamp_s
            self._last_voice_at_s = timestamp_s  # Track last voice time for silence timeout
            logger.info("VAD speech process started at %.3f, speech started at %.3f", time.time(), timestamp_s)
            
            # Include pre-roll frames + current frame
            pre_roll_parts = list(self._pre_roll_buffer)
            self._speech_pcm_parts = pre_roll_parts + [pcm]
            return VADResult(status=VADStatus.IN_SPEECH)
        
        # In speech state
        self._speech_pcm_parts.append(pcm)
        
        # Check max_utterance_ms - force finalize if exceeded
        if self._speech_started_at_s is not None:
            utterance_duration_ms = (timestamp_s - self._speech_started_at_s) * 1000.0
            if utterance_duration_ms >= self._cfg.max_utterance_ms:
                # Force finalize
                utterance_pcm = np.concatenate(self._speech_pcm_parts) if self._speech_pcm_parts else np.array([], dtype=np.float32)
                started_at = self._speech_started_at_s
                
                # Reset state
                self._in_speech = False
                self._speech_pcm_parts = []
                self._speech_started_at_s = None
                self._last_voice_at_s = None

                logger.info("VAD speech process ended at %.3f, speech started_at_s=%.3f, ended_at_s=%.3f", time.time(), started_at, timestamp_s)
                return VADResult(
                    status=VADStatus.END_SPEECH,
                    utterance_pcm=utterance_pcm,
                    sample_rate=self._sample_rate,
                    started_at_s=started_at,
                    ended_at_s=timestamp_s,
                )

        # Update last voice time if voice detected
        if has_voice:
            self._last_voice_at_s = timestamp_s
        
        return VADResult(status=VADStatus.IN_SPEECH)
    
    def flush(self, now_s: float) -> VADResult:
        """
        Force finalize any in-progress speech.
        
        Args:
            now_s: Current timestamp (seconds)
            
        Returns:
            VADResult with END_SPEECH if speech was in progress, NO_SPEECH otherwise
        """
        if not self._in_speech:
            return VADResult(status=VADStatus.NO_SPEECH)
        
        # Process any remaining chunk buffer
        if len(self._chunk_buffer) > 0:
            has_voice = self._process_chunk(self._chunk_buffer)
            self._chunk_buffer = np.array([], dtype=np.float32)
        
        # Finalize utterance
        if len(self._speech_pcm_parts) > 0:
            utterance_pcm = np.concatenate(self._speech_pcm_parts)
            started_at = self._speech_started_at_s or now_s
            
            # Reset state
            self._in_speech = False
            self._speech_pcm_parts = []
            self._speech_started_at_s = None

            logger.info("VAD speech flush process ended at %.3f, speech started_at_s=%.3f, ended_at_s=%.3f", time.time(), started_at, now_s)
            return VADResult(
                status=VADStatus.END_SPEECH,
                utterance_pcm=utterance_pcm,
                sample_rate=self._sample_rate,
                started_at_s=started_at,
                ended_at_s=now_s,
            )

        # Reset state
        self._in_speech = False
        self._speech_pcm_parts = []
        self._speech_started_at_s = None

        return VADResult(status=VADStatus.NO_SPEECH)
