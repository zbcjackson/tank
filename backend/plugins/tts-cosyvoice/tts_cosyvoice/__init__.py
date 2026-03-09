"""CosyVoice TTS plugin for Tank."""

from .engine import CosyVoiceTTSEngine


def create_engine(config: dict) -> CosyVoiceTTSEngine:
    """
    Create a CosyVoice TTS engine from plugin config.

    When ``docker`` is ``True``, a Docker container running the CosyVoice
    server is started automatically and ``base_url`` is set to point at it.

    Args:
        config: Plugin configuration dict with keys:
            - docker: Auto-manage Docker container (default: False)
            - docker_image: Docker image name (default: tank-cosyvoice:latest)
            - docker_container: Container name (default: tank-cosyvoice)
            - port: Server port (default: 50000)
            - model_dir: Model directory inside container
            - docker_health_timeout: Seconds to wait for server (default: 300)
            - base_url: CosyVoice server URL (default: http://localhost:50000)
            - mode: "sft" or "zero_shot" (default: "sft")
            - spk_id_en: English speaker ID for sft mode (default: "英文女")
            - spk_id_zh: Chinese speaker ID for sft mode (default: "中文女")
            - sample_rate: Output sample rate (default: 22050)
            - timeout_s: HTTP timeout in seconds (default: 120)
            - prompt_text: Prompt transcript for zero_shot mode
            - prompt_wav_path: Path to prompt WAV for zero_shot mode

    Returns:
        CosyVoiceTTSEngine instance
    """
    if config.get("docker", False):
        from .server import CosyVoiceServer

        server = CosyVoiceServer(config)
        base_url = server.ensure_running()
        config = {**config, "base_url": base_url}

    return CosyVoiceTTSEngine(config)


__all__ = ["create_engine", "CosyVoiceTTSEngine"]
