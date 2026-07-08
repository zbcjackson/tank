"""AssemblyAI Universal-Streaming realtime ASR plugin for Tank."""

from .engine import AssemblyAIASREngine


def create_engine(config: dict) -> AssemblyAIASREngine:
    """Create an AssemblyAI ASR engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - api_key: AssemblyAI API key (required)
            - speech_model: streaming model (default: universal-3-5-pro)
            - sample_rate: Audio sample rate (default: 16000)

    Returns:
        AssemblyAIASREngine instance
    """
    return AssemblyAIASREngine(
        api_key=config["api_key"],
        speech_model=config.get("speech_model", "universal-3-5-pro"),
        sample_rate=config.get("sample_rate", 16000),
    )


__all__ = ["AssemblyAIASREngine", "create_engine"]
