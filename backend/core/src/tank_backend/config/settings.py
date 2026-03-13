import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# Mapping from env var name → (model field name, type coercion).
# Only fields that need env-var loading are listed here.
# Fields not listed use their Field(default=...) value.
_ENV_FIELD_MAP: dict[str, tuple[str, type]] = {
    "SERPER_API_KEY": ("serper_api_key", str),
    "DEFAULT_LANGUAGE": ("default_language", str),
    "AUDIO_DURATION": ("audio_duration", float),
    "LOG_LEVEL": ("log_level", str),
    "MAX_CONVERSATION_HISTORY": ("max_conversation_history", int),
    "MAX_HISTORY_TOKENS": ("max_history_tokens", int),
    "SUMMARIZE_AT_TOKENS": ("summarize_at_tokens", int),
    "SPEECH_INTERRUPT_ENABLED": ("speech_interrupt_enabled", str),
    "ENABLE_SPEAKER_ID": ("enable_speaker_id", str),
}

_TRUTHY = {"true", "1", "yes"}


def _parse_bool(value: str) -> bool:
    return value.lower() in _TRUTHY


class VoiceAssistantConfig(BaseModel):
    serper_api_key: str | None = Field(
        default=None, description="Serper API key for web search functionality"
    )
    default_language: str = Field(
        default="zh", description="Default language for processing (auto, en, zh)"
    )
    audio_duration: float = Field(
        default=5.0, description="Default audio recording duration in seconds"
    )
    log_level: str = Field(default="INFO", description="Logging level")
    max_conversation_history: int = Field(
        default=10, description="Maximum number of conversation turns to keep"
    )
    max_history_tokens: int = Field(
        default=8000, description="Maximum token budget for conversation history"
    )
    summarize_at_tokens: int = Field(
        default=6000,
        description="Trigger summarization when history exceeds this token count",
    )
    speech_interrupt_enabled: bool = Field(
        default=True,
        description="When True, user speech interrupts TTS playback and current LLM processing",
    )
    enable_speaker_id: bool = Field(
        default=False, description="Enable speaker identification (voiceprint recognition)"
    )

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")


def _read_env_overrides() -> dict:
    """Read set env vars and coerce them to the expected types."""
    overrides: dict = {}
    for env_key, (field_name, coerce) in _ENV_FIELD_MAP.items():
        raw = os.getenv(env_key)
        if raw is None:
            continue
        if coerce is float:
            overrides[field_name] = float(raw)
        elif coerce is int:
            overrides[field_name] = int(raw)
        else:
            overrides[field_name] = raw
    # Coerce bool fields that arrived as strings
    for bool_field in ("speech_interrupt_enabled", "enable_speaker_id"):
        if bool_field in overrides and isinstance(overrides[bool_field], str):
            overrides[bool_field] = _parse_bool(overrides[bool_field])
    # Treat empty SERPER_API_KEY as None
    if overrides.get("serper_api_key") == "":
        overrides["serper_api_key"] = None
    return overrides


def load_config(config_path: Path | None = None) -> VoiceAssistantConfig:
    if config_path is None:
        config_path = Path(".env")

    if config_path.exists():
        load_dotenv(config_path)
        logger.info(f"Loaded environment variables from {config_path}")
    else:
        logger.warning(f"Config file {config_path} not found, using environment variables only")

    try:
        config = VoiceAssistantConfig(**_read_env_overrides())

        if not config.serper_api_key:
            logger.warning(
                "SERPER_API_KEY is not set. Web search functionality will not be available."
            )

        return config

    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise


def create_example_env_file(path: Path = Path(".env.example")):
    example_content = """# LLM API Key - Referenced by core/config.yaml via ${LLM_API_KEY}
LLM_API_KEY=your_api_key_here

# Serper API Key - Get from https://serper.dev/
SERPER_API_KEY=your_serper_api_key_here

# Whisper model size: tiny, base, small, medium, large
WHISPER_MODEL_SIZE=base

# Default language: auto, en, zh
DEFAULT_LANGUAGE=zh

# Audio recording duration in seconds
AUDIO_DURATION=5.0

# Logging level
LOG_LEVEL=INFO

# Maximum conversation history to keep
MAX_CONVERSATION_HISTORY=10

# Speech interrupt: when True, user speech interrupts TTS and LLM (true/false)
SPEECH_INTERRUPT_ENABLED=true

# Speaker identification — enable/disable toggle (config in core/config.yaml)
ENABLE_SPEAKER_ID=false
"""

    with open(path, "w") as f:
        f.write(example_content)

    logger.info(f"Created example environment file at {path}")


def setup_logging(log_level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
