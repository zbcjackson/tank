"""Deepgram Nova-3 realtime streaming ASR plugin for Tank."""

from .engine import DeepgramASREngine


def create_engine(config: dict) -> DeepgramASREngine:
    """Create a Deepgram ASR engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - api_key: Deepgram API key (required)
            - model: Deepgram model (default: nova-3)
            - language: ISO language code or "multi" (default: en)
            - sample_rate: Audio sample rate (default: 16000)

    Returns:
        DeepgramASREngine instance
    """
    return DeepgramASREngine(
        api_key=config["api_key"],
        model=config.get("model", "nova-3"),
        language=config.get("language", "en"),
        sample_rate=config.get("sample_rate", 16000),
    )


__all__ = ["DeepgramASREngine", "create_engine"]
