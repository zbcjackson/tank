import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from tank_backend.core.brain import Brain
from tank_backend.core.events import BrainInputEvent, InputType, UpdateType, DisplayMessage, SignalMessage, AudioOutputRequest
from tank_backend.core.runtime import RuntimeContext
from tank_backend.core.shutdown import GracefulShutdown
from tank_backend.config.settings import VoiceAssistantConfig

@pytest.fixture
def runtime():
    return RuntimeContext.create()

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    # chat_stream needs to return an async generator
    async def async_gen(*args, **kwargs):
        yield UpdateType.THOUGHT, "Thinking...", {}
        yield UpdateType.TOOL_CALL, "", {"index": 0, "name": "get_weather", "status": "calling"}
        yield UpdateType.TOOL_RESULT, "Sunny", {"index": 0, "name": "get_weather", "status": "success"}
        yield UpdateType.TEXT, "The weather is sunny.", {}
    
    llm.chat_stream.return_value = async_gen()
    return llm

@pytest.fixture
def brain(runtime, mock_llm):
    shutdown_signal = GracefulShutdown()
    mock_speaker = MagicMock()
    mock_tool_manager = MagicMock()
    mock_tool_manager.get_openai_tools.return_value = []
    config = VoiceAssistantConfig(llm_api_key="test")
    
    b = Brain(shutdown_signal, runtime, mock_speaker, mock_llm, mock_tool_manager, config)
    # Create a new event loop for testing
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    b._event_loop = loop
    yield b
    loop.close()

def test_brain_streaming_full_flow(brain, runtime, mock_llm):
    event = BrainInputEvent(
        type=InputType.TEXT,
        text="What is the weather?",
        user="User",
        language="en",
        confidence=None,
        metadata={"msg_id": "test_msg_id"}
    )
    
    # Run handle
    brain.handle(event)
    
    # Check display queue for messages
    messages = []
    while not runtime.ui_queue.empty():
        messages.append(runtime.ui_queue.get_nowait())

    # 2. Assistant messages (filter out SignalMessage)
    assistant_msgs = [m for m in messages if isinstance(m, DisplayMessage) and not m.is_user]
    assert any(m.update_type == UpdateType.THOUGHT for m in assistant_msgs)
    assert any(m.update_type == UpdateType.TOOL_CALL for m in assistant_msgs)
    assert any(m.update_type == UpdateType.TOOL_RESULT for m in assistant_msgs)
    assert any(m.update_type == UpdateType.TEXT and m.text == "The weather is sunny." for m in assistant_msgs)
    
    # 3. Final message
    assert assistant_msgs[-1].is_final is True
    
    # 4. Audio output (TTS)
    assert not runtime.audio_output_queue.empty()
    audio_req = runtime.audio_output_queue.get_nowait()
    assert audio_req.content == "The weather is sunny."
