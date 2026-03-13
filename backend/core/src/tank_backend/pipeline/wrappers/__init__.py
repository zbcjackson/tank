"""Pipeline wrapper processors for existing Tank components."""

from .asr_processor import ASRProcessor
from .brain_processor import BrainProcessor
from .playback_processor import PlaybackProcessor
from .tts_processor import TTSProcessor
from .vad_processor import VADProcessor

__all__ = [
    "ASRProcessor",
    "BrainProcessor",
    "PlaybackProcessor",
    "TTSProcessor",
    "VADProcessor",
]
