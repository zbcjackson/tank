"""CosyVoice TTS plugin for Tank."""

from .engine import CosyVoiceTTSEngine


def create_engine(config: dict) -> CosyVoiceTTSEngine:
    """
    Create a CosyVoice TTS engine from plugin config.

    **Provider** (``provider`` key, default ``"local"``):

    ``"local"`` — self-hosted CosyVoice FastAPI server:
        When ``docker`` is ``True``, a Docker container is started automatically
        and ``base_url`` is set to point at it.

        Keys:
            - docker: Auto-manage Docker container (default: False)
            - docker_image: Docker image name (default: tank-cosyvoice:latest)
            - docker_container: Container name (default: tank-cosyvoice)
            - port: Server port (default: 50000)
            - model_dir: Model directory inside container
            - docker_health_timeout: Seconds to wait for server (default: 300)
            - base_url: CosyVoice server URL (default: http://localhost:50000)
            - mode: "sft", "zero_shot", or "instruct2" (default: "sft")
            - spk_id_en: English speaker ID for sft mode (default: "英文女")
            - spk_id_zh: Chinese speaker ID for sft mode (default: "中文女")
            - sample_rate: Output sample rate (default: 22050)
            - timeout_s: HTTP timeout in seconds (default: 120)
            - prompt_text: Prompt transcript for zero_shot mode
            - prompt_wav_path: Path to prompt WAV for zero_shot mode
            - instruct_text: Style instruction for instruct2 mode

    ``"dashscope"`` — Alibaba DashScope CosyVoice cloud API (WebSocket):
        Keys:
            - dashscope_api_key: DashScope API key (required)
            - dashscope_model: Model name (default: "cosyvoice-v3-flash")
            - dashscope_voice_en: English voice (default: "longanyang")
            - dashscope_voice_zh: Chinese voice (default: "longanyang")
            - dashscope_region: "intl" (Singapore) or "cn" (Beijing), default "intl"
            - sample_rate: Output sample rate (default: 22050)

    Returns:
        CosyVoiceTTSEngine instance
    """
    if config.get("provider", "local") == "local" and config.get("docker", False):
        from .server import CosyVoiceServer

        server = CosyVoiceServer(config)
        base_url = server.ensure_running()
        config = {**config, "base_url": base_url}

    engine = CosyVoiceTTSEngine(config)
    # Keep a reference so the server isn't GC'd (its atexit hook needs self).
    if config.get("provider", "local") == "local" and config.get("docker", False):
        engine._server = server  # type: ignore[assignment]
    return engine


__all__ = ["create_engine", "CosyVoiceTTSEngine"]
