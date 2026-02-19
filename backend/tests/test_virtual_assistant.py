"""Integration test for VoiceAssistant in 'virtual' mode (no hardware)."""

import asyncio
import pytest
import queue
import time
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

from tank_backend.core.assistant import Assistant
from tank_backend.audio.input.queue_source import QueueAudioSource
from tank_backend.audio.output.callback_sink import CallbackAudioSink
from tank_backend.audio.input.types import AudioFrame
from tank_backend.audio.output.types import AudioChunk
from tank_backend.core.events import DisplayMessage, SignalMessage, BrainInputEvent


@pytest.fixture
def mock_config():
    with patch("src.voice_assistant.core.assistant.load_config") as mock_load:
        config = MagicMock()
        config.llm_api_key = "test_key"
        config.llm_model = "test_model"
        config.llm_base_url = "https://api.openai.com/v1"
        config.serper_api_key = "test_serper"
        config.speech_interrupt_enabled = True
        config.max_conversation_history = 5
        config.tts_voice_zh = "zh-CN-XiaoxiaoNeural"
        config.tts_voice_en = "en-US-JennyNeural"
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

    # Mock SherpaASR to avoid model loading and provide fixed results
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

    with patch("src.voice_assistant.llm.llm.LLM.chat_stream", side_effect=mock_chat_stream), \
         patch("src.voice_assistant.audio.input.asr_sherpa.SherpaASR.__init__", return_value=None), \
         patch("src.voice_assistant.audio.input.asr_sherpa.SherpaASR.process_pcm", side_effect=mock_process_pcm), \
         patch("src.voice_assistant.audio.output.tts_engine_edge.EdgeTTSEngine.generate_stream", side_effect=mock_generate_stream):
        
        # 2. Setup factories
        recorded_chunks = []
        
        def source_factory(q, stop_sig):
            return QueueAudioSource(q)
            
        def sink_factory(q, stop_sig):
            return CallbackAudioSink(
                stop_signal=stop_sig,
                audio_chunk_queue=q,
                on_chunk=lambda chunk: recorded_chunks.append(chunk)
            )

        # 3. Initialize Assistant
        assistant = Assistant(
            audio_source_factory=source_factory,
            audio_sink_factory=sink_factory
        )
        
        try:
            assistant.start()
            
            # 4. Push a few frames of 'audio' (just zeros)
            q_source = assistant.audio_input._source
            for i in range(10):
                q_source.push(AudioFrame(
                    pcm=np.zeros(320, dtype=np.float32),
                    sample_rate=16000,
                    timestamp_s=time.time()
                ))
                await asyncio.sleep(0.01)
            
            # 5. Wait for transcription and response
            timeout = time.time() + 10
            all_msgs = []
            found_msg = False
            found_resp = False
            
            while time.time() < timeout:
                new_msgs = list(assistant.get_messages())
                all_msgs.extend(new_msgs)
                
                if not found_msg:
                    if any(text_to_return in m.text.lower() for m in all_msgs if isinstance(m, DisplayMessage) and m.is_user):
                        found_msg = True

                if not found_resp:
                    if any("brain" in m.speaker.lower() for m in all_msgs if isinstance(m, DisplayMessage)):
                        found_resp = True
                
                if found_msg and found_resp:
                    break
                    
                await asyncio.sleep(0.1)
            
            assert found_msg, f"Should have received '{text_to_return}' transcription. All msgs: {all_msgs}"
            assert found_resp, f"Should have received assistant response. All msgs: {all_msgs}"
            
            # 6. Check if CallbackAudioSink received chunks
            timeout = time.time() + 5
            while time.time() < timeout and not recorded_chunks:
                await asyncio.sleep(0.1)
            
            assert len(recorded_chunks) > 0, "Should have captured audio chunks from TTS"

        finally:
            assistant.stop()
