"""Pipeline processors — native Processor subclasses for the audio pipeline."""

from ...config.models import EchoGuardConfig
from .asr import ASRProcessor
from .asr_speaker_merger import ASRSpeakerMerger, SpeakerIDResult
from .brain import Brain, BrainConfig
from .echo_guard import SelfEchoDetector
from .playback import PlaybackProcessor
from .speaker_id import SpeakerIDProcessor
from .tts import TTSProcessor
from .vad import VADProcessor

__all__ = [
    "ASRProcessor",
    "Brain",
    "BrainConfig",
    "EchoGuardConfig",
    "ASRSpeakerMerger",
    "PlaybackProcessor",
    "SelfEchoDetector",
    "SpeakerIDProcessor",
    "SpeakerIDResult",
    "TTSProcessor",
    "VADProcessor",
]
