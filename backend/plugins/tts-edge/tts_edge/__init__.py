"""Edge TTS plugin for Tank."""

from .engine import EdgeTTSEngine


def create_engine(config: dict):
    """
    Create an Edge TTS engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - voice_en: English voice name (e.g., "en-US-JennyNeural")
            - voice_zh: Chinese voice name (e.g., "zh-CN-XiaoxiaoNeural")

    Returns:
        EdgeTTSEngine instance
    """
    return EdgeTTSEngine(config)


__all__ = ["create_engine", "EdgeTTSEngine"]
