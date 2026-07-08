"""Hume Octave emotionally-expressive streaming TTS plugin for Tank."""

from .engine import HumeTTSEngine


def create_engine(config: dict) -> HumeTTSEngine:
    """Create a Hume Octave TTS engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - api_key: Hume API key (required)
            - voice_id / voice_name: predefined Hume voice (optional)
            - description: emotion/persona prompt shaping delivery (optional)
            - voices: language → voice-name map (optional)
            - default_voice: fallback voice name (optional)
            - sample_rate: output sample rate (default: 24000)

    Returns:
        HumeTTSEngine instance
    """
    return HumeTTSEngine(config)


__all__ = ["create_engine", "HumeTTSEngine"]
