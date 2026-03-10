"""ElevenLabs realtime streaming ASR plugin for Tank."""

from .engine import ElevenLabsASREngine


def create_engine(config: dict) -> ElevenLabsASREngine:
    """Create an ElevenLabs ASR engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - api_key: ElevenLabs API key (required)
            - language_code: ISO language code (default: auto-detect)
            - sample_rate: Audio sample rate (default: 16000)

    Returns:
        ElevenLabsASREngine instance
    """
    return ElevenLabsASREngine(
        api_key=config["api_key"],
        language_code=config.get("language_code", ""),
        sample_rate=config.get("sample_rate", 16000),
    )


__all__ = ["create_engine", "ElevenLabsASREngine"]
