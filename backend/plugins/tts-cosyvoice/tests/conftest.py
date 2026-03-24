"""Test fixtures for CosyVoice plugin tests."""

import pytest


@pytest.fixture
def cosyvoice_config():
    """Standard CosyVoice plugin config for sft mode."""
    return {
        "base_url": "http://localhost:50000",
        "mode": "sft",
        "spk_id_en": "英文女",
        "spk_id_zh": "中文女",
        "sample_rate": 22050,
        "timeout_s": 30,
    }


@pytest.fixture
def zero_shot_config(tmp_path):
    """CosyVoice plugin config for zero_shot mode."""
    prompt_wav = tmp_path / "prompt.wav"
    prompt_wav.write_bytes(b"\x00" * 1600)
    return {
        "base_url": "http://localhost:50000",
        "mode": "zero_shot",
        "prompt_text": "Hello, this is a test prompt.",
        "prompt_wav_path": str(prompt_wav),
        "sample_rate": 22050,
        "timeout_s": 30,
    }


@pytest.fixture
def dashscope_config():
    """CosyVoice plugin config for DashScope provider."""
    return {
        "provider": "dashscope",
        "dashscope_api_key": "sk-test-key",
        "dashscope_model": "cosyvoice-v3-flash",
        "dashscope_voice_en": "longanyang",
        "dashscope_voice_zh": "longxiaochun_v2",
        "dashscope_region": "intl",
        "sample_rate": 22050,
    }
