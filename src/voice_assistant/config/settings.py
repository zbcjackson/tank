import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

class VoiceAssistantConfig(BaseModel):
    llm_api_key: str = Field(..., min_length=1, description="LLM API key for accessing the language model")
    llm_model: str = Field(default="anthropic/claude-3-5-nano", description="LLM model to use")
    llm_base_url: str = Field(default="https://openrouter.ai/api/v1", description="LLM API base URL")
    serper_api_key: Optional[str] = Field(default=None, description="Serper API key for web search functionality")
    whisper_model_size: str = Field(default="base", description="Whisper model size (tiny, base, small, medium, large)")
    default_language: str = Field(default="zh", description="Default language for processing (auto, en, zh)")
    audio_duration: float = Field(default=5.0, description="Default audio recording duration in seconds")
    tts_voice_en: str = Field(default="en-US-JennyNeural", description="Default English TTS voice")
    tts_voice_zh: str = Field(default="zh-CN-XiaoxiaoNeural", description="Default Chinese TTS voice")
    log_level: str = Field(default="INFO", description="Logging level")
    max_conversation_history: int = Field(default=10, description="Maximum number of conversation turns to keep")
    speech_interrupt_enabled: bool = Field(default=True, description="When True, user speech interrupts TTS playback and current LLM processing")

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

def load_config(config_path: Optional[Path] = None) -> VoiceAssistantConfig:
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
            default_language=os.getenv("DEFAULT_LANGUAGE", "zh"),
            audio_duration=float(os.getenv("AUDIO_DURATION", "5.0")),
            tts_voice_en=os.getenv("TTS_VOICE_EN", "en-US-JennyNeural"),
            tts_voice_zh=os.getenv("TTS_VOICE_ZH", "zh-CN-XiaoxiaoNeural"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            max_conversation_history=int(os.getenv("MAX_CONVERSATION_HISTORY", "10")),
            speech_interrupt_enabled=os.getenv("SPEECH_INTERRUPT_ENABLED", "true").lower() in ("true", "1", "yes"),
        )

        if not config.llm_api_key:
            raise ValueError("LLM_API_KEY is required but not set")

        # Serper API key is optional - web search will not be available without it
        if not config.serper_api_key:
            logger.warning("SERPER_API_KEY is not set. Web search functionality will not be available.")

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

# TTS voices
TTS_VOICE_EN=en-US-JennyNeural
TTS_VOICE_ZH=zh-CN-XiaoxiaoNeural

# Logging level
LOG_LEVEL=INFO

# Maximum conversation history to keep
MAX_CONVERSATION_HISTORY=10

# Speech interrupt: when True, user speech interrupts TTS and LLM (true/false)
SPEECH_INTERRUPT_ENABLED=true
"""

    with open(path, "w") as f:
        f.write(example_content)

    logger.info(f"Created example environment file at {path}")

def setup_logging(log_level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )