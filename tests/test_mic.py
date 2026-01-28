"""Tests for microphone audio capture."""

import pytest
import queue
import threading
import time
import numpy as np
from unittest.mock import Mock, patch, MagicMock

from src.voice_assistant.audio.input.mic import Mic, AudioFrame
from src.voice_assistant.audio.input.types import AudioFormat, FrameConfig
from src.voice_assistant.core.shutdown import GracefulShutdown
import sounddevice as sd


class TestMic:
    """Test cases for Mic class."""

    @pytest.fixture
    def audio_format(self):
        """Default audio format."""
        return AudioFormat(sample_rate=16000, channels=1, dtype="float32")

    @pytest.fixture
    def frame_config(self):
        """Default frame configuration."""
        return FrameConfig(frame_ms=20, max_frames_queue=100)

    @pytest.fixture
    def frames_queue(self):
        """Queue for audio frames."""
        return queue.Queue(maxsize=100)

    @pytest.fixture
    def stop_signal(self):
        """Stop signal."""
        return GracefulShutdown()

    def test_mic_captures_audio_frames(self, audio_format, frame_config, frames_queue, stop_signal):
        """Test that Mic captures audio frames and puts them into queue."""
        mic = Mic(
            stop_signal=stop_signal,
            audio_format=audio_format,
            frame_cfg=frame_config,
            frames_queue=frames_queue,
        )

        # Store callback for later use
        captured_callback = None
        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream_context.__enter__ = Mock(return_value=mock_stream)
        mock_stream_context.__exit__ = Mock(return_value=False)
        
        def capture_callback(*args, **kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get('callback') or (args[0] if args else None)
            return mock_stream_context
        
        with patch('src.voice_assistant.audio.input.mic.sd.InputStream', side_effect=capture_callback):
            # Start mic thread
            mic.start()
            
            # Wait a bit for thread to start and initialize stream
            time.sleep(0.3)
            
            # Verify InputStream was called and callback was captured
            assert captured_callback is not None, "sd.InputStream should have been called with callback parameter"
            
            # Simulate callback being called with audio data
            mock_audio_data = np.random.randn(320, 1).astype(np.float32)  # 20ms at 16kHz
            captured_callback(mock_audio_data, 320, {}, {})
            time.sleep(0.1)
            
            # Check that frame was added to queue
            assert not frames_queue.empty()
            frame = frames_queue.get_nowait()
            assert isinstance(frame, AudioFrame)
            assert frame.sample_rate == audio_format.sample_rate
            assert frame.pcm.dtype == np.float32
            assert len(frame.pcm) == 320
            
            # Stop mic
            stop_signal.stop()
            mic.join(timeout=1.0)

    def test_mic_stops_on_stop_signal(self, audio_format, frame_config, frames_queue, stop_signal):
        """Test that Mic stops when stop_signal is set."""
        mic = Mic(
            stop_signal=stop_signal,
            audio_format=audio_format,
            frame_cfg=frame_config,
            frames_queue=frames_queue,
        )

        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream_context.__enter__ = Mock(return_value=mock_stream)
        mock_stream_context.__exit__ = Mock(return_value=False)
        
        with patch('src.voice_assistant.audio.input.mic.sd.InputStream', return_value=mock_stream_context):
            mic.start()
            
            # Wait a bit for thread to start
            time.sleep(0.2)
            
            # Set stop signal
            stop_signal.stop()
            
            # Mic should stop within reasonable time
            mic.join(timeout=2.0)
            assert not mic.is_alive()

    def test_mic_handles_full_queue(self, audio_format, frame_config, frames_queue, stop_signal):
        """Test that Mic handles full queue gracefully without blocking."""
        # Fill queue to capacity
        for _ in range(frames_queue.maxsize):
            frame = AudioFrame(
                pcm=np.random.randn(320).astype(np.float32),
                sample_rate=audio_format.sample_rate,
                timestamp_s=time.time()
            )
            frames_queue.put_nowait(frame)
        
        assert frames_queue.full()
        
        mic = Mic(
            stop_signal=stop_signal,
            audio_format=audio_format,
            frame_cfg=frame_config,
            frames_queue=frames_queue,
        )

        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream_context.__enter__ = Mock(return_value=mock_stream)
        mock_stream_context.__exit__ = Mock(return_value=False)
        
        with patch('src.voice_assistant.audio.input.mic.sd.InputStream', return_value=mock_stream_context):
            mic.start()
            time.sleep(0.2)
            
            # Simulate callback with full queue
            call_kwargs = mock_stream_context.call_args[1] if mock_stream_context.call_args else {}
            callback = call_kwargs.get('callback')
            if callback:
                mock_audio_data = np.random.randn(320, 1).astype(np.float32)
                callback(mock_audio_data, 320, {}, {})
            
            # Mic should not block even with full queue
            stop_signal.stop()
            mic.join(timeout=1.0)
            
            # Should complete without hanging
            assert not mic.is_alive()

    def test_mic_uses_correct_audio_format(self, frame_config, frames_queue, stop_signal):
        """Test that Mic uses AudioFormat parameters correctly."""
        custom_format = AudioFormat(sample_rate=44100, channels=1, dtype="float32")
        
        mic = Mic(
            stop_signal=stop_signal,
            audio_format=custom_format,
            frame_cfg=frame_config,
            frames_queue=frames_queue,
        )

        mock_stream_context = MagicMock()
        mock_stream = MagicMock()
        mock_stream_context.__enter__ = Mock(return_value=mock_stream)
        mock_stream_context.__exit__ = Mock(return_value=False)
        
        with patch('src.voice_assistant.audio.input.mic.sd.InputStream', return_value=mock_stream_context) as mock_input_stream:
            mic.start()
            time.sleep(0.2)
            stop_signal.stop()
            mic.join(timeout=1.0)
            
            # Verify custom format was used
            assert mock_input_stream.called
            call_kwargs = mock_input_stream.call_args[1]
            assert call_kwargs['samplerate'] == 44100
            assert call_kwargs['channels'] == 1
            assert call_kwargs['dtype'] == np.float32
