"""Audio input subsystem - captures audio, segments, and recognizes speech."""

from __future__ import annotations

from .asr import ASR
from .audio_input import AudioInput, AudioInputConfig
from .mic import AudioFrame, Mic
from .types import AudioFormat, FrameConfig, PerceptionConfig, SegmenterConfig
from .vad import SileroVAD, VADResult, VADStatus
from .voiceprint import Utterance, VoiceprintRecognizer
from .voiceprint_streaming import StreamingVoiceprintRecognizer

__all__ = [
    "AudioInput",
    "AudioInputConfig",
    "ASR",
    "AudioFormat",
    "FrameConfig",
    "SegmenterConfig",
    "PerceptionConfig",
    "AudioFrame",
    "Mic",
    "Utterance",
    "VADStatus",
    "VADResult",
    "VoiceprintRecognizer",
    "StreamingVoiceprintRecognizer",
    "SileroVAD",
]
