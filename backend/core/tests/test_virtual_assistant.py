"""Integration test for VoiceAssistant in 'virtual' mode (no hardware)."""

import asyncio
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tank_backend.audio.input.queue_source import QueueAudioSource
from tank_backend.audio.input.types import AudioFrame
from tank_backend.audio.output.callback_sink import CallbackAudioSink
from tank_backend.audio.output.types import AudioChunk
from tank_backend.core.assistant import Assistant
from tank_backend.core.events import DisplayMessage

MODULE = "tank_backend.core.assistant"


@pytest.fixture
def mock_config():
    with patch(f"{MODULE}.load_config") as mock_load:
        config = MagicMock()
        config.serper_api_key = "test_serper"
        config.speech_interrupt_enabled = True
        config.max_conversation_history = 5
        config.max_history_tokens = 8000
        config.summarize_at_tokens = 6000
        config.enable_speaker_id = False
        mock_load.return_value = config
        yield config


@pytest.mark.asyncio
async def test_virtual_assistant_flow(mock_config):
    """
    Test Assistant with QueueAudioSource and CallbackAudioSink.
    Verifies that pushing audio frames results in processed messages.
    """

    # 1. Setup mocks for LLM to avoid real API calls
    async def mock_chat_stream(*args, **kwargs):
        from tank_backend.core.events import UpdateType

        yield UpdateType.TEXT, "Hello! I am your virtual assistant.", {}

    # Mock ASR to avoid model loading and provide fixed results
    text_to_return = "hello"
    call_count = [0]

    def mock_process_pcm(pcm):
        call_count[0] += 1
        # Only return is_final=True on the 10th frame
        if call_count[0] < 10:
            return text_to_return, False
        else:
            return text_to_return, True

    # Mock EdgeTTSEngine to avoid real TTS calls
    async def mock_generate_stream(*args, **kwargs):
        yield AudioChunk(data=b"dummy_pcm", sample_rate=24000, channels=1)

    # Mock engines
    mock_tts_engine = MagicMock()
    mock_tts_engine.generate_stream = mock_generate_stream

    mock_asr_engine = MagicMock()
    mock_asr_engine.process_pcm = MagicMock(side_effect=mock_process_pcm)
    mock_asr_engine.reset = MagicMock()

    # Mock LLM instance with chat_stream
    mock_llm_instance = MagicMock()
    mock_llm_instance.chat_stream = mock_chat_stream

    # Build mock registry
    mock_registry = MagicMock()

    def instantiate(full_name, config):
        if full_name and "asr" in full_name:
            return mock_asr_engine
        if full_name and "tts" in full_name:
            return mock_tts_engine
        return MagicMock()

    mock_registry.instantiate.side_effect = instantiate

    # Build mock app config
    mock_app_config = MagicMock()
    mock_app_config.get_llm_profile.return_value = MagicMock()

    def is_feature_enabled(name):
        return {"asr": True, "tts": True, "speaker": False}.get(name, False)

    mock_app_config.is_feature_enabled.side_effect = is_feature_enabled

    def get_feature_config(name):
        cfg = MagicMock()
        cfg.enabled = is_feature_enabled(name)
        cfg.extension = f"mock-{name}:{name}" if cfg.enabled else None
        cfg.config = {"voice_en": "en-US-JennyNeural", "voice_zh": "zh-CN-XiaoxiaoNeural"}
        cfg.plugin = f"mock-{name}" if cfg.enabled else ""
        return cfg

    mock_app_config.get_feature_config.side_effect = get_feature_config

    mock_pm = MagicMock()
    mock_pm.load_all.return_value = mock_registry

    with (
        patch(f"{MODULE}.PluginManager", return_value=mock_pm),
        patch(f"{MODULE}.AppConfig", return_value=mock_app_config),
        patch(f"{MODULE}.create_llm_from_profile", return_value=mock_llm_instance),
    ):
        # 2. Setup factories
        recorded_chunks = []

        def source_factory(q, stop_sig):
            return QueueAudioSource(q)

        def sink_factory(q, stop_sig):
            return CallbackAudioSink(
                stop_signal=stop_sig,
                audio_chunk_queue=q,
                on_chunk=lambda chunk: recorded_chunks.append(chunk),
            )

        # 3. Initialize Assistant
        assistant = Assistant(audio_source_factory=source_factory, audio_sink_factory=sink_factory)

        try:
            assistant.start()

            # 4. Push a few frames of 'audio' (just zeros)
            q_source = assistant.audio_input._source
            for _i in range(10):
                q_source.push(
                    AudioFrame(
                        pcm=np.zeros(320, dtype=np.float32),
                        sample_rate=16000,
                        timestamp_s=time.time(),
                    )
                )
                await asyncio.sleep(0.01)

            # 5. Wait for transcription and response
            timeout = time.time() + 10
            all_msgs = []
            found_msg = False
            found_resp = False

            while time.time() < timeout:
                new_msgs = list(assistant.get_messages())
                all_msgs.extend(new_msgs)

                if not found_msg and any(
                    text_to_return in m.text.lower()
                    for m in all_msgs
                    if isinstance(m, DisplayMessage) and m.is_user
                ):
                    found_msg = True

                if not found_resp and any(
                    "brain" in m.speaker.lower()
                    for m in all_msgs
                    if isinstance(m, DisplayMessage)
                ):
                    found_resp = True

                if found_msg and found_resp:
                    break

                await asyncio.sleep(0.1)

            assert found_msg, (
                f"Should have received '{text_to_return}' transcription. All msgs: {all_msgs}"
            )
            assert found_resp, f"Should have received assistant response. All msgs: {all_msgs}"

            # 6. Check if CallbackAudioSink received chunks
            timeout = time.time() + 5
            while time.time() < timeout and not recorded_chunks:
                await asyncio.sleep(0.1)

            assert len(recorded_chunks) > 0, "Should have captured audio chunks from TTS"

        finally:
            assistant.stop()
