"""Audio input subsystem - captures audio, segments, and recognizes speech."""

from __future__ import annotations

from .asr import ASR
from .mic import AudioFrame, Mic
from .types import AudioFormat, FrameConfig, PerceptionConfig, SegmenterConfig
from .vad import SileroVAD, VADEngine, VADResult, VADStatus, VADStream
from .voiceprint import Utterance, VoiceprintRecognizer
from .voiceprint_streaming import StreamingVoiceprintRecognizer

__all__ = [
    "ASR",
    "AudioFormat",
    "AudioFrame",
    "FrameConfig",
    "Mic",
    "PerceptionConfig",
    "SegmenterConfig",
    "SileroVAD",
    "StreamingVoiceprintRecognizer",
    "Utterance",
    "VADEngine",
    "VADResult",
    "VADStatus",
    "VADStream",
    "VoiceprintRecognizer",
]
