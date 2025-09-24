import pytest
import os


@pytest.fixture
def setup_test_env():
    """Setup test environment variables"""
    original_env = os.environ.copy()

    # Set test environment variables
    os.environ["LLM_API_KEY"] = "test_key_12345"
    os.environ["WHISPER_MODEL_SIZE"] = "base"
    os.environ["DEFAULT_LANGUAGE"] = "zh"

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_audio_data():
    """Mock audio data for testing"""
    import numpy as np
    return np.random.rand(16000).astype(np.float32)  # 1 second of mock audio at 16kHz