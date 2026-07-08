"""Local offline Kokoro-82M in-process TTS plugin for Tank."""

from .engine import KokoroTTSEngine


def create_engine(config: dict) -> KokoroTTSEngine:
    """Create a Kokoro TTS engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - voices: language → Kokoro voice preset map (optional)
            - default_voice: fallback voice (default: af_heart)
            - speed: speaking rate multiplier (default: 1.0)
            - sample_rate: output sample rate (default: 24000)

    Returns:
        KokoroTTSEngine instance
    """
    return KokoroTTSEngine(config)


__all__ = ["create_engine", "KokoroTTSEngine"]
