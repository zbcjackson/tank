"""Tests for StreamingPerception thread."""

import queue
import uuid
import numpy as np
import pytest
from unittest.mock import MagicMock

from tank_backend.audio.input.perception_streaming import StreamingPerception
from tank_backend.core.events import BrainInputEvent, DisplayMessage, InputType
from tank_backend.core.runtime import RuntimeContext
from tank_backend.core.shutdown import GracefulShutdown

@pytest.fixture
def runtime():
    return RuntimeContext.create()

@pytest.fixture
def mock_asr():
    asr = MagicMock()
    # Return (text, is_final)
    asr.process_pcm.return_value = ("", False)
    return asr

@pytest.fixture
def perception(runtime, mock_asr):
    stop = GracefulShutdown()
    frames_queue = queue.Queue()
    return StreamingPerception(
        shutdown_signal=stop,
        runtime=runtime,
        frames_queue=frames_queue,
        asr=mock_asr,
        user="User"
    )

def test_streaming_perception_msg_id_lifecycle(perception, runtime, mock_asr):
    """Verify that msg_id is generated and reused until final."""
    
    # Mock some AudioFrame
    frame = MagicMock()
    frame.pcm = np.zeros(160, dtype=np.float32)

    # 1. First partial result
    mock_asr.process_pcm.return_value = ("hello", False)
    perception.handle(frame)
    
    assert not runtime.ui_queue.empty()
    msg1 = runtime.ui_queue.get_nowait()
    assert msg1.text == "hello"
    assert msg1.is_final is False
    assert msg1.msg_id is not None
    assert msg1.msg_id.startswith("user_")

    # 2. Second partial result - same ID
    mock_asr.process_pcm.return_value = ("hello world", False)
    perception.handle(frame)

    msg2 = runtime.ui_queue.get_nowait()
    assert msg2.text == "hello world"
    assert msg2.msg_id == msg1.msg_id

    # 3. Final result - same ID
    mock_asr.process_pcm.return_value = ("hello world", True)
    perception.handle(frame)

    msg3 = runtime.ui_queue.get_nowait()
    assert msg3.text == "hello world"
    assert msg3.is_final is True
    assert msg3.msg_id == msg1.msg_id

    # 4. Next utterance - NEW ID
    mock_asr.process_pcm.return_value = ("new sentence", False)
    perception.handle(frame)

    msg4 = runtime.ui_queue.get_nowait()
    assert msg4.text == "new sentence"
    assert msg4.msg_id != msg1.msg_id
    assert msg4.msg_id is not None

def test_streaming_perception_skips_unchanged_text(perception, runtime, mock_asr):
    """Verify that it doesn't spam the queue if text doesn't change."""
    frame = MagicMock()
    frame.pcm = np.zeros(160, dtype=np.float32)

    mock_asr.process_pcm.return_value = ("hello", False)
    perception.handle(frame)
    assert runtime.ui_queue.qsize() == 1
    runtime.ui_queue.get()

    # Same text, not final -> skip
    perception.handle(frame)
    assert runtime.ui_queue.empty()

    # Same text, BUT final -> don't skip
    mock_asr.process_pcm.return_value = ("hello", True)
    perception.handle(frame)
    assert runtime.ui_queue.qsize() == 1
    msg = runtime.ui_queue.get()
    assert msg.is_final is True
