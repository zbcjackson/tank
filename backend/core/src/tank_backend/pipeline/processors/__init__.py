"""Pipeline processors — native Processor subclasses for the audio pipeline."""

from .asr import ASRProcessor
from .brain import Brain
from .echo_guard import EchoGuardConfig, SelfEchoDetector
from .fan_in_merger import FanInMerger, SpeakerIDResult
from .playback import PlaybackProcessor
from .speaker_id import SpeakerIDProcessor
from .tts import TTSProcessor
from .vad import VADProcessor

__all__ = [
    "ASRProcessor",
    "Brain",
    "EchoGuardConfig",
    "FanInMerger",
    "PlaybackProcessor",
    "SelfEchoDetector",
    "SpeakerIDProcessor",
    "SpeakerIDResult",
    "TTSProcessor",
    "VADProcessor",
]
