"""Test fixtures for plugin tests."""

import pytest


@pytest.fixture
def edge_tts_config():
    """Standard Edge TTS plugin config."""
    return {
        "voice_en": "en-US-JennyNeural",
        "voice_zh": "zh-CN-XiaoxiaoNeural",
    }
