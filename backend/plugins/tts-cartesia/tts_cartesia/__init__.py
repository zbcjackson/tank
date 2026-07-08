"""Cartesia Sonic realtime streaming TTS plugin for Tank."""

from .engine import CartesiaTTSEngine


def create_engine(config: dict) -> CartesiaTTSEngine:
    """Create a Cartesia TTS engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - api_key: Cartesia API key (required)
            - model_id: Sonic model (default: sonic-3)
            - voices: language → voice-UUID map (optional)
            - default_voice: fallback voice UUID (required unless voices given)
            - sample_rate: output sample rate (default: 24000)
            - emotion: optional Cartesia emotion controls
            - cartesia_version: API version (default: 2026-03-01)

    Returns:
        CartesiaTTSEngine instance
    """
    return CartesiaTTSEngine(config)


__all__ = ["create_engine", "CartesiaTTSEngine"]
