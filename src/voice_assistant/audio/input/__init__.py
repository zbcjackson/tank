"""Audio input subsystem - captures audio, segments, and recognizes speech."""

from __future__ import annotations

from .audio_input import AudioInput, AudioInputConfig
from .types import AudioFormat, FrameConfig, SegmenterConfig
from .mic import Mic, AudioFrame
from .segmenter import UtteranceSegmenter, Utterance
from .asr import ASR
from .perception import Perception, PerceptionConfig
from .voiceprint import VoiceprintRecognizer
from .vad import VADStatus, VADResult, SileroVAD




__all__ = [
    "AudioInput",
    "AudioInputConfig",
    "ASR",
    "AudioFormat",
    "FrameConfig",
    "SegmenterConfig",
    "PerceptionConfig",
    "AudioFrame",
    "Utterance",
    "VADStatus",
    "VADResult",
    "VoiceprintRecognizer",
    "SileroVAD",
]
