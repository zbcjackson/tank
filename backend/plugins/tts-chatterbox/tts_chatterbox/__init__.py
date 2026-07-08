"""Local offline Chatterbox in-process TTS plugin for Tank."""

from .engine import ChatterboxTTSEngine


def create_engine(config: dict) -> ChatterboxTTSEngine:
    """Create a Chatterbox TTS engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - device: torch device (default: cpu)
            - exaggeration: emotion intensity 0-1+ (default: 0.5)
            - cfg_weight: pacing/guidance weight (default: 0.5)
            - voice_prompt_path: reference wav for voice cloning (optional)
            - sample_rate: output sample rate (default: model.sr)

    Returns:
        ChatterboxTTSEngine instance
    """
    return ChatterboxTTSEngine(config)


__all__ = ["create_engine", "ChatterboxTTSEngine"]
