import pytest
from unittest.mock import Mock, patch
from src.voice_assistant.config.settings import VoiceAssistantConfig, load_config
from pathlib import Path
import tempfile
import os

class TestConfig:
    def test_default_config(self):
        config = VoiceAssistantConfig(llm_api_key="test_key")
        assert config.whisper_model_size == "base"
        assert config.default_language == "auto"
        assert config.audio_duration == 5.0

    def test_config_with_custom_values(self):
        config = VoiceAssistantConfig(
            llm_api_key="test_key",
            whisper_model_size="small",
            default_language="en"
        )
        assert config.whisper_model_size == "small"
        assert config.default_language == "en"

    @patch.dict(os.environ, {
        "LLM_API_KEY": "test_key",
        "WHISPER_MODEL_SIZE": "large",
        "DEFAULT_LANGUAGE": "zh"
    })
    def test_load_config_from_env(self):
        config = load_config()
        assert config.llm_api_key == "test_key"
        assert config.whisper_model_size == "large"
        assert config.default_language == "zh"

    def test_missing_api_key(self):
        with pytest.raises(ValueError):
            VoiceAssistantConfig(llm_api_key="")

    def test_config_from_temp_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("LLM_API_KEY=temp_key\n")
            f.write("WHISPER_MODEL_SIZE=medium\n")
            temp_path = f.name

        try:
            config = load_config(Path(temp_path))
            assert config.llm_api_key == "temp_key"
            assert config.whisper_model_size == "medium"
        finally:
            os.unlink(temp_path)