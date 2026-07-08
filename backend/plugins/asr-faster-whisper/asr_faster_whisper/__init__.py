"""Local offline Faster-Whisper batch ASR plugin for Tank."""

from .engine import FasterWhisperASREngine, FasterWhisperASRStream


def create_engine(config: dict) -> FasterWhisperASREngine:
    """Create a Faster-Whisper ASR engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - model_size: Whisper model size (default: base)
            - device: cpu or cuda (default: cpu)
            - compute_type: int8 / float16 / etc. (default: int8)
            - language: ISO code, or "" for auto-detect (default: "")
            - beam_size: decoding beam size (default: 5)
            - sample_rate: Audio sample rate (default: 16000)

    Returns:
        FasterWhisperASREngine instance
    """
    return FasterWhisperASREngine(
        model_size=config.get("model_size", "base"),
        device=config.get("device", "cpu"),
        compute_type=config.get("compute_type", "int8"),
        language=config.get("language", ""),
        beam_size=config.get("beam_size", 5),
        sample_rate=config.get("sample_rate", 16000),
    )


__all__ = ["FasterWhisperASREngine", "FasterWhisperASRStream", "create_engine"]
