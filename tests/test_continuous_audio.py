import pytest
import asyncio
import time
import numpy as np
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from src.voice_assistant.audio.continuous_transcription import ContinuousTranscriber
from src.voice_assistant.audio.tts import EdgeTTSSpeaker


class TestContinuousTranscriber:
    @pytest.fixture
    def transcriber(self):
        # Mock whisper.load_model to avoid loading actual model in tests
        with patch('src.voice_assistant.audio.continuous_transcription.whisper.load_model') as mock_load:
            mock_model = Mock()
            mock_load.return_value = mock_model
            transcriber = ContinuousTranscriber(model_size="base")
            return transcriber

    @pytest.fixture
    def mock_audio_stream(self):
        """Mock audio stream with silence and speech patterns"""
        sample_rate = 16000

        # Create silence
        silence = np.zeros(1600, dtype=np.float32)  # 0.1 seconds of silence

        # Create speech-like audio with fundamental frequency and formants
        duration = 0.3  # 0.3 seconds
        t = np.linspace(0, duration, int(sample_rate * duration))
        fundamental = 0.3 * np.sin(2 * np.pi * 150 * t)
        formant1 = 0.2 * np.sin(2 * np.pi * 800 * t)
        formant2 = 0.1 * np.sin(2 * np.pi * 1200 * t)
        speech = (fundamental + formant1 + formant2).astype(np.float32)

        return np.concatenate([silence, speech, silence])

    @pytest.mark.asyncio
    async def test_voice_activity_detection_silence(self, transcriber):
        """Test that silence is correctly detected as no voice activity"""
        silence_audio = np.zeros(1600, dtype=np.float32)
        has_voice = transcriber.has_voice_activity(silence_audio)
        assert not has_voice

    @pytest.mark.asyncio
    async def test_voice_activity_detection_speech(self, transcriber):
        """Test that speech-like audio is detected as voice activity"""
        # Generate synthetic speech-like audio with fundamental frequency and formants
        sample_rate = transcriber.sample_rate
        duration = 0.1  # 100ms
        t = np.linspace(0, duration, int(sample_rate * duration))

        # Create speech-like signal with fundamental frequency (150 Hz) and formants
        fundamental = 0.3 * np.sin(2 * np.pi * 150 * t)  # F0 at 150 Hz
        formant1 = 0.2 * np.sin(2 * np.pi * 800 * t)     # First formant at 800 Hz
        formant2 = 0.1 * np.sin(2 * np.pi * 1200 * t)    # Second formant at 1200 Hz

        speech_audio = (fundamental + formant1 + formant2).astype(np.float32)
        has_voice = transcriber.has_voice_activity(speech_audio)
        assert has_voice

    @pytest.mark.asyncio
    async def test_voice_activity_detection_music_rejected(self, transcriber):
        """Test that music-like audio is rejected as non-speech"""
        # Generate music-like audio with high frequency content but no speech characteristics
        sample_rate = transcriber.sample_rate
        duration = 0.1  # 100ms
        t = np.linspace(0, duration, int(sample_rate * duration))

        # Music with high frequencies but lacking speech formant structure
        music_audio = (0.3 * np.sin(2 * np.pi * 440 * t) +  # A4 note
                      0.2 * np.sin(2 * np.pi * 880 * t) +   # A5 note
                      0.1 * np.sin(2 * np.pi * 1760 * t)).astype(np.float32)  # A6 note

        has_voice = transcriber.has_voice_activity(music_audio)
        assert not has_voice

    @pytest.mark.asyncio
    async def test_voice_activity_detection_noise_rejected(self, transcriber):
        """Test that random noise is rejected as non-speech"""
        # Generate white noise that has energy but no speech structure
        noise_audio = np.random.random(1600).astype(np.float32) * 0.5
        has_voice = transcriber.has_voice_activity(noise_audio)
        assert not has_voice

    @pytest.mark.asyncio
    async def test_voice_activity_detection_low_frequency_rejected(self, transcriber):
        """Test that pure low-frequency sounds are rejected as non-speech"""
        # Generate low-frequency tone (below speech range)
        sample_rate = transcriber.sample_rate
        duration = 0.1  # 100ms
        t = np.linspace(0, duration, int(sample_rate * duration))

        # Pure low frequency (60 Hz hum)
        low_freq_audio = (0.5 * np.sin(2 * np.pi * 60 * t)).astype(np.float32)
        has_voice = transcriber.has_voice_activity(low_freq_audio)
        assert not has_voice

    @pytest.mark.asyncio
    async def test_continuous_listening_starts_properly(self, transcriber):
        """Test that continuous listening starts and can be stopped"""
        transcriber.is_listening = False

        # Start listening in background with timeout
        listen_task = asyncio.create_task(transcriber.start_continuous_listening())

        # Wait briefly and check it started
        await asyncio.sleep(0.1)
        assert transcriber.is_listening

        # Stop listening
        transcriber.stop_listening()

        # Cancel and wait for cleanup
        listen_task.cancel()
        try:
            await asyncio.wait_for(listen_task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        assert not transcriber.is_listening

    @pytest.mark.asyncio
    async def test_speech_interruption_stops_current_task(self, transcriber):
        """Test that speech detection interrupts current tasks"""
        interrupt_called = False

        def mock_interrupt():
            nonlocal interrupt_called
            interrupt_called = True

        transcriber.set_interrupt_callback(mock_interrupt)

        # Simulate speech detection triggering interruption
        transcriber._handle_speech_start()

        assert interrupt_called

    @pytest.mark.asyncio
    async def test_silence_timeout_triggers_transcription(self, transcriber):
        """Test that 2 seconds of silence triggers transcription and accumulates text"""
        transcription_called = False

        # Create speech-like audio buffer (2 seconds)
        sample_rate = transcriber.sample_rate
        duration = 2.0
        t = np.linspace(0, duration, int(sample_rate * duration))
        fundamental = 0.3 * np.sin(2 * np.pi * 150 * t)
        formant1 = 0.2 * np.sin(2 * np.pi * 800 * t)
        formant2 = 0.1 * np.sin(2 * np.pi * 1200 * t)
        mock_audio_buffer = (fundamental + formant1 + formant2).astype(np.float32)

        async def mock_transcribe(audio_data):
            nonlocal transcription_called
            transcription_called = True
            return "test transcription", "en"

        transcriber.transcribe_audio_buffer = mock_transcribe
        transcriber.speech_buffer = mock_audio_buffer
        transcriber.is_recording_speech = True

        # Simulate silence timeout
        await transcriber._handle_silence_timeout()

        assert transcription_called
        assert not transcriber.is_recording_speech
        assert transcriber.accumulated_text == "test transcription"

    @pytest.mark.asyncio
    async def test_speech_start_stops_recording_silence(self, transcriber):
        """Test that speech start stops silence recording and starts speech recording"""
        transcriber.is_recording_speech = False
        transcriber.silence_start_time = asyncio.get_event_loop().time()

        transcriber._handle_speech_start()

        assert transcriber.is_recording_speech
        assert transcriber.silence_start_time is None

    @pytest.mark.asyncio
    async def test_get_latest_transcription_returns_accumulated_text(self, transcriber):
        """Test that get_latest_transcription returns accumulated text and clears it"""
        # Set up accumulated text
        transcriber.accumulated_text = "hello world"
        transcriber.accumulated_language = "en"

        result = transcriber.get_latest_transcription()

        assert result == ("hello world", "en")
        # Should clear after getting
        assert transcriber.accumulated_text == ""
        assert transcriber.accumulated_language is None

        # Second call should return None
        result2 = transcriber.get_latest_transcription()
        assert result2 is None

    @pytest.mark.asyncio
    async def test_transcription_accumulation(self, transcriber):
        """Test that multiple transcriptions are accumulated"""
        # Mock transcribe to return different text each time
        call_count = 0

        async def mock_transcribe(audio_data):
            nonlocal call_count
            call_count += 1
            return f"phrase {call_count}", "en"

        transcriber.transcribe_audio_buffer = mock_transcribe

        # Simulate first transcription
        transcriber.speech_buffer = np.random.random(1600).astype(np.float32)
        transcriber.is_recording_speech = True
        await transcriber._handle_silence_timeout()

        assert transcriber.accumulated_text == "phrase 1"

        # Simulate second transcription
        transcriber.speech_buffer = np.random.random(1600).astype(np.float32)
        transcriber.is_recording_speech = True
        await transcriber._handle_silence_timeout()

        assert transcriber.accumulated_text == "phrase 1 phrase 2"

    @pytest.mark.asyncio
    async def test_clear_accumulated_transcription(self, transcriber):
        """Test clearing accumulated transcription"""
        transcriber.accumulated_text = "some text"
        transcriber.accumulated_language = "en"

        transcriber.clear_accumulated_transcription()

        assert transcriber.accumulated_text == ""
        assert transcriber.accumulated_language is None

    @pytest.mark.asyncio
    async def test_silence_timeout_with_empty_audio_queue(self, transcriber):
        """Test that silence timeout works even when audio queue is empty"""
        transcription_called = False

        async def mock_transcribe(audio_data):
            nonlocal transcription_called
            transcription_called = True
            return "timeout test", "en"

        transcriber.transcribe_audio_buffer = mock_transcribe

        # Set up state as if recording speech and silence started
        transcriber.is_recording_speech = True
        transcriber.silence_start_time = time.time() - 2.5  # 2.5 seconds ago (past timeout)
        transcriber.speech_buffer = np.random.random(1600).astype(np.float32)

        # Call the silence timeout check directly (simulates empty queue scenario)
        await transcriber._check_silence_timeout()

        assert transcription_called
        assert not transcriber.is_recording_speech
        assert transcriber.accumulated_text == "timeout test"

    @pytest.mark.asyncio
    async def test_no_silence_timeout_when_not_recording(self, transcriber):
        """Test that silence timeout check doesn't trigger when not recording speech"""
        transcription_called = False

        async def mock_transcribe(audio_data):
            nonlocal transcription_called
            transcription_called = True
            return "should not happen", "en"

        transcriber.transcribe_audio_buffer = mock_transcribe

        # Set up state as not recording speech
        transcriber.is_recording_speech = False
        transcriber.silence_start_time = time.time() - 5.0  # Long past timeout
        transcriber.speech_buffer = np.random.random(1600).astype(np.float32)

        # Call the silence timeout check
        await transcriber._check_silence_timeout()

        # Should not have triggered transcription
        assert not transcription_called
        assert transcriber.accumulated_text == ""

    @pytest.mark.asyncio
    async def test_whisper_model_loaded_at_initialization(self):
        """Test that Whisper model is loaded during initialization"""
        with patch('src.voice_assistant.audio.continuous_transcription.whisper.load_model') as mock_load:
            mock_model = Mock()
            mock_load.return_value = mock_model

            transcriber = ContinuousTranscriber(model_size="tiny")

            # Verify model was loaded during init
            mock_load.assert_called_once_with("tiny")
            assert transcriber.model is mock_model

    @pytest.mark.asyncio
    async def test_audio_queue_processing(self, transcriber):
        """Test that audio queue processing works correctly"""
        # Create speech-like audio chunk
        sample_rate = transcriber.sample_rate
        duration = transcriber.chunk_duration
        t = np.linspace(0, duration, transcriber.chunk_size)
        fundamental = 0.3 * np.sin(2 * np.pi * 150 * t)
        formant1 = 0.2 * np.sin(2 * np.pi * 800 * t)
        formant2 = 0.1 * np.sin(2 * np.pi * 1200 * t)
        speech_chunk = (fundamental + formant1 + formant2).astype(np.float32)

        # Process a chunk directly
        await transcriber.process_audio_chunk(speech_chunk)

        # Should have detected speech and started recording
        assert transcriber.is_recording_speech
        assert len(transcriber.speech_buffer) > 0


class TestInterruptibleTTSSpeaker:
    @pytest.fixture
    def speaker(self):
        return EdgeTTSSpeaker()

    @pytest.mark.asyncio
    async def test_speech_can_be_interrupted(self, speaker):
        """Test that TTS speech can be interrupted"""
        # Mock TTS generation to avoid actual network calls
        with patch.object(speaker, 'text_to_speech_async', return_value=b'fake_audio_data'):
            with patch('subprocess.Popen') as mock_popen:
                mock_process = Mock()
                mock_process.poll.return_value = None  # Process running
                mock_popen.return_value = mock_process

                # Start speaking
                speak_task = asyncio.create_task(speaker.speak_async("This is a long sentence that should be interrupted"))
                await asyncio.sleep(0.1)  # Let it start

                # Interrupt
                speaker.interrupt_speech()

                # The task should complete quickly due to interruption
                try:
                    await asyncio.wait_for(speak_task, timeout=2.0)
                except asyncio.TimeoutError:
                    speak_task.cancel()
                    await asyncio.sleep(0.1)

                assert speaker.is_interrupted

    @pytest.mark.asyncio
    async def test_interrupt_clears_after_new_speech(self, speaker):
        """Test that interrupt flag is cleared when starting new speech"""
        speaker.is_interrupted = True

        with patch.object(speaker, 'text_to_speech_async', return_value=b'fake_audio_data'):
            with patch('subprocess.Popen') as mock_popen:
                mock_process = Mock()
                mock_process.poll.return_value = 0  # Process completed
                mock_popen.return_value = mock_process

                await speaker.speak_async("New speech")

        assert not speaker.is_interrupted