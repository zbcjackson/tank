"""Audio output subsystem - TTS and playback.

Keep this module lightweight: import/export only.
"""

from ...core.events import AudioOutputRequest
from .tts import TTSEngine
from .types import AudioChunk

__all__ = [
    "AudioChunk",
    "AudioOutputRequest",
    "TTSEngine",
]
