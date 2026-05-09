"""Sherpa-ONNX streaming ASR plugin for Tank."""

from .engine import SherpaASREngine, SherpaASRStream


def create_engine(config: dict) -> SherpaASREngine:
    """Create a Sherpa-ONNX ASR engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - model_dir: Path to Sherpa-ONNX model directory
            - num_threads: Number of threads (default: 4)
            - sample_rate: Audio sample rate (default: 16000)

    Returns:
        SherpaASREngine instance
    """
    return SherpaASREngine(
        model_dir=config.get("model_dir", "../models/sherpa-onnx-zipformer-en-zh"),
        num_threads=config.get("num_threads", 4),
        sample_rate=config.get("sample_rate", 16000),
    )


__all__ = ["SherpaASREngine", "SherpaASRStream", "create_engine"]
