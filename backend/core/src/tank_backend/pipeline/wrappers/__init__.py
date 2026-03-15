"""Pipeline wrapper processors for existing Tank components."""

from .asr_processor import ASRProcessor
from .brain_processor import BrainProcessor
from .echo_guard import EchoGuardConfig, SelfEchoDetector
from .playback_processor import PlaybackProcessor
from .tts_processor import TTSProcessor
from .vad_processor import VADProcessor

__all__ = [
    "ASRProcessor",
    "BrainProcessor",
    "EchoGuardConfig",
    "PlaybackProcessor",
    "SelfEchoDetector",
    "TTSProcessor",
    "VADProcessor",
]
