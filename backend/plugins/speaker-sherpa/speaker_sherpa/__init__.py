"""Sherpa-ONNX speaker embedding plugin for Tank."""

from .engine import SherpaEmbeddingExtractor


def create_engine(config: dict) -> SherpaEmbeddingExtractor:
    """Create a Sherpa-ONNX speaker embedding extractor from plugin config.

    Args:
        config: Plugin configuration dict with keys:
            - model_path: Path to ONNX model file
            - num_threads: Number of threads (default: 1)
            - provider: Execution provider (default: "cpu")

    Returns:
        SherpaEmbeddingExtractor instance
    """
    return SherpaEmbeddingExtractor(
        model_path=config["model_path"],
        num_threads=config.get("num_threads", 1),
        provider=config.get("provider", "cpu"),
    )


__all__ = ["create_engine", "SherpaEmbeddingExtractor"]
