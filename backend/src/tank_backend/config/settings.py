import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class VoiceAssistantConfig(BaseModel):
    llm_api_key: str = Field(
        ..., min_length=1, description="LLM API key for accessing the language model"
    )
    llm_model: str = Field(default="anthropic/claude-3-5-nano", description="LLM model to use")
    llm_base_url: str = Field(
        default="https://openrouter.ai/api/v1", description="LLM API base URL"
    )
    serper_api_key: str | None = Field(
        default=None, description="Serper API key for web search functionality"
    )
    whisper_model_size: str = Field(
        default="base", description="Whisper model size (tiny, base, small, medium, large)"
    )
    sherpa_model_dir: str = Field(
        default="models/sherpa-onnx-zipformer-en-zh",
        description="Path to Sherpa-ONNX model directory",
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
    speech_interrupt_enabled: bool = Field(
        default=True,
        description="When True, user speech interrupts TTS playback and current LLM processing",
    )
    enable_speaker_id: bool = Field(
        default=False, description="Enable speaker identification (voiceprint recognition)"
    )
    speaker_model_path: str = Field(
        default="models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
        description="Path to speaker embedding model (ONNX format)",
    )
    speaker_db_path: str = Field(
        default="data/speakers.db", description="Path to speaker database (SQLite)"
    )
    speaker_threshold: float = Field(
        default=0.6,
        description="Speaker identification threshold (0.0-1.0, higher = stricter)",
    )
    speaker_default_user: str = Field(
        default="Unknown", description="Default user when speaker not identified"
    )

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")


def load_config(config_path: Path | None = None) -> VoiceAssistantConfig:
    if config_path is None:
        config_path = Path(".env")

    if config_path.exists():
        load_dotenv(config_path)
        logger.info(f"Loaded environment variables from {config_path}")
    else:
        logger.warning(f"Config file {config_path} not found, using environment variables only")

    try:
        config = VoiceAssistantConfig(
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", "anthropic/claude-3-5-nano"),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
            serper_api_key=os.getenv("SERPER_API_KEY", ""),
            whisper_model_size=os.getenv("WHISPER_MODEL_SIZE", "base"),
            sherpa_model_dir=os.getenv("SHERPA_MODEL_DIR", "models/sherpa-onnx-zipformer-en-zh"),
            default_language=os.getenv("DEFAULT_LANGUAGE", "zh"),
            audio_duration=float(os.getenv("AUDIO_DURATION", "5.0")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            max_conversation_history=int(os.getenv("MAX_CONVERSATION_HISTORY", "10")),
            speech_interrupt_enabled=os.getenv("SPEECH_INTERRUPT_ENABLED", "true").lower()
            in ("true", "1", "yes"),
            enable_speaker_id=os.getenv("ENABLE_SPEAKER_ID", "false").lower()
            in ("true", "1", "yes"),
            speaker_model_path=os.getenv(
                "SPEAKER_MODEL_PATH",
                "models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx",
            ),
            speaker_db_path=os.getenv("SPEAKER_DB_PATH", "data/speakers.db"),
            speaker_threshold=float(os.getenv("SPEAKER_THRESHOLD", "0.6")),
            speaker_default_user=os.getenv("SPEAKER_DEFAULT_USER", "Unknown"),
        )

        if not config.llm_api_key:
            raise ValueError("LLM_API_KEY is required but not set")

        # Serper API key is optional - web search will not be available without it
        if not config.serper_api_key:
            logger.warning(
                "SERPER_API_KEY is not set. Web search functionality will not be available."
            )

        return config

    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise


def create_example_env_file(path: Path = Path(".env.example")):
    example_content = """# LLM API Key - Get from your LLM provider (e.g., OpenRouter, OpenAI, etc.)
LLM_API_KEY=your_api_key_here

# LLM Configuration
LLM_MODEL=anthropic/claude-3-5-nano
LLM_BASE_URL=https://openrouter.ai/api/v1

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

# Speaker identification (voiceprint recognition)
ENABLE_SPEAKER_ID=false
SPEAKER_MODEL_PATH=models/speaker/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx
SPEAKER_DB_PATH=data/speakers.db
SPEAKER_THRESHOLD=0.6
SPEAKER_DEFAULT_USER=Unknown
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
