"""Audio input subsystem - captures audio, segments, and recognizes speech."""

from __future__ import annotations

from .asr import ASR
from .audio_input import AudioInput, AudioInputConfig
from .mic import AudioFrame, Mic
from .perception import Perception, PerceptionConfig
from .segmenter import Utterance, UtteranceSegmenter
from .types import AudioFormat, FrameConfig, SegmenterConfig
from .vad import SileroVAD, VADResult, VADStatus
from .voiceprint import VoiceprintRecognizer

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
    "Perception",
    "Utterance",
    "UtteranceSegmenter",
    "VADStatus",
    "VADResult",
    "VoiceprintRecognizer",
    "SileroVAD",
]
