"""Tank plugin contracts."""

from .asr import StreamingASREngine
from .speaker import SpeakerEmbeddingExtractor
from .tts import (
    AUDIO_FRAME_HEADER_SIZE,
    AUDIO_FRAME_MAGIC,
    AudioChunk,
    TTSEngine,
    decode_audio_frame,
    encode_audio_frame,
)

__all__ = [
    "AUDIO_FRAME_HEADER_SIZE",
    "AUDIO_FRAME_MAGIC",
    "AudioChunk",
    "SpeakerEmbeddingExtractor",
    "StreamingASREngine",
    "TTSEngine",
    "decode_audio_frame",
    "encode_audio_frame",
]
