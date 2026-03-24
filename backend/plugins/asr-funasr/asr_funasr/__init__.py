"""FunASR streaming ASR plugin for Tank."""

from .engine import FunASREngine


def create_engine(config: dict) -> FunASREngine:
    """Create a FunASR ASR engine from plugin config.

    Args:
        config: Plugin configuration dict with keys:

          **Common:**
            - sample_rate: Audio sample rate (default: 16000)
            - itn: Enable inverse text normalization (default: True)

          **Self-hosted FunASR** (no api_key):
            - host: FunASR server host (default: "127.0.0.1")
            - port: FunASR server port (default: "10095")
            - mode: "online", "offline", or "2pass" (default: "2pass")
            - is_ssl: Use wss:// (default: False)
            - chunk_size: [look-back, chunk, look-ahead] (default: [5, 10, 5])
            - hotwords: Dict of hotword → weight (default: {})

          **DashScope cloud** (api_key required):
            - api_key: DashScope API key (required, use ${DASHSCOPE_API_KEY})
            - model: Model name (default: "paraformer-realtime-v2")
            - dashscope_url: Override endpoint URL (default: China endpoint)

    Returns:
        FunASREngine instance
    """
    return FunASREngine(
        host=config.get("host", "127.0.0.1"),
        port=config.get("port", "10095"),
        mode=config.get("mode", "2pass"),
        is_ssl=config.get("is_ssl", False),
        sample_rate=config.get("sample_rate", 16000),
        chunk_size=config.get("chunk_size", [5, 10, 5]),
        hotwords=config.get("hotwords", {}),
        itn=config.get("itn", True),
        api_key=config.get("api_key", ""),
        model=config.get("model", ""),
        dashscope_url=config.get("dashscope_url", ""),
    )


__all__ = ["create_engine", "FunASREngine"]
