"""Tank plugin contracts."""

from .asr import ASREngine, ASRStream, StreamingASREngine
from .connector import (
    Attachment,
    Connector,
    ConnectorCapabilities,
    Identity,
    MessageEvent,
    MessageHandler,
    SendResult,
)
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
    "ASREngine",
    "ASRStream",
    "Attachment",
    "AudioChunk",
    "Connector",
    "ConnectorCapabilities",
    "Identity",
    "MessageEvent",
    "MessageHandler",
    "SendResult",
    "SpeakerEmbeddingExtractor",
    "StreamingASREngine",
    "TTSEngine",
    "decode_audio_frame",
    "encode_audio_frame",
]
