"""ElevenLabs realtime streaming TTS plugin for Tank."""

from .engine import ElevenLabsTTSEngine


def create_engine(config: dict) -> ElevenLabsTTSEngine:
    """Create an ElevenLabs TTS engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - api_key: ElevenLabs API key (required)
            - voice_id: Default voice ID (required)
            - voice_id_zh: Chinese voice ID (optional, falls back to voice_id)
            - model_id: Model to use (default: eleven_flash_v2_5)
            - sample_rate: Output sample rate (default: 24000)
            - stability: Voice stability 0-1 (default: 0.5)
            - similarity_boost: Similarity boost 0-1 (default: 0.75)

    Returns:
        ElevenLabsTTSEngine instance
    """
    return ElevenLabsTTSEngine(config)


__all__ = ["create_engine", "ElevenLabsTTSEngine"]
