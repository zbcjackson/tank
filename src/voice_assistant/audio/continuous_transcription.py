import whisper
import sounddevice as sd
import numpy as np
import asyncio
import tempfile
import wave
from typing import Optional, Tuple, Callable
import logging
import time
import threading
import queue

logger = logging.getLogger(__name__)

class ContinuousTranscriber:
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model = None
        self.sample_rate = 16000
        self.chunk_duration = 0.1  # 100ms chunks
        self.chunk_size = int(self.sample_rate * self.chunk_duration)

        # Voice activity detection parameters
        self.energy_threshold = 0.01  # Adjust based on testing
        self.silence_timeout = 2.0  # 2 seconds of silence before transcription

        # State management
        self.is_listening = False
        self.is_recording_speech = False
        self.speech_buffer = np.array([], dtype=np.float32)
        self.silence_start_time = None

        # Accumulated transcription storage
        self.accumulated_text = ""
        self.accumulated_language = None

        # Interrupt system
        self.interrupt_callback = None

        # Thread-safe audio processing
        self.audio_queue = queue.Queue()
        self.loop = None

    def load_model(self):
        if self.model is None:
            logger.info(f"Loading Whisper model: {self.model_size}")
            self.model = whisper.load_model(self.model_size)

    def has_voice_activity(self, audio_chunk: np.ndarray) -> bool:
        """Detect if audio chunk contains speech using spectral analysis"""
        # Calculate RMS energy first - if too low, definitely not speech
        energy = np.sqrt(np.mean(audio_chunk ** 2))
        if energy <= self.energy_threshold:
            return False

        # Apply speech-specific spectral analysis
        return self._is_speech_like(audio_chunk, energy)

    def _is_speech_like(self, audio_chunk: np.ndarray, energy: float) -> bool:
        """Analyze audio chunk to determine if it contains speech-like characteristics"""
        # Apply window function to reduce spectral leakage
        windowed = audio_chunk * np.hanning(len(audio_chunk))

        # Compute FFT
        fft = np.fft.rfft(windowed)
        magnitude = np.abs(fft)

        # Convert to frequency bins (Hz)
        freqs = np.fft.rfftfreq(len(audio_chunk), 1.0 / self.sample_rate)

        # Define speech frequency ranges
        low_freq_range = (85, 255)      # Fundamental frequency range for speech
        mid_freq_range = (255, 2000)    # Formant range
        high_freq_range = (2000, 8000)  # High-frequency speech content

        # Get energy in each frequency band
        low_energy = self._get_band_energy(magnitude, freqs, low_freq_range)
        mid_energy = self._get_band_energy(magnitude, freqs, mid_freq_range)
        high_energy = self._get_band_energy(magnitude, freqs, high_freq_range)

        total_speech_energy = low_energy + mid_energy + high_energy

        # Check if most energy is in speech frequencies
        speech_energy_ratio = total_speech_energy / (np.sum(magnitude) + 1e-10)

        # Speech characteristics:
        # 1. Significant energy in fundamental frequency range (85-255 Hz)
        # 2. Strong formant energy (255-2000 Hz)
        # 3. At least 60% of energy in speech frequency range
        # 4. Not dominated by very low frequencies (which indicates non-speech sounds)

        has_fundamental = low_energy > 0.1 * total_speech_energy
        has_formants = mid_energy > 0.3 * total_speech_energy
        sufficient_speech_ratio = speech_energy_ratio > 0.6

        return has_fundamental and has_formants and sufficient_speech_ratio

    def _get_band_energy(self, magnitude: np.ndarray, freqs: np.ndarray, freq_range: Tuple[float, float]) -> float:
        """Get total energy in a frequency band"""
        mask = (freqs >= freq_range[0]) & (freqs <= freq_range[1])
        return np.sum(magnitude[mask] ** 2)

    def set_interrupt_callback(self, callback: Callable):
        """Set callback function to call when speech interruption occurs"""
        self.interrupt_callback = callback

    def _handle_speech_start(self):
        """Handle detection of speech start"""
        logger.debug("Speech detected - starting recording")

        # Interrupt any ongoing tasks
        if self.interrupt_callback:
            self.interrupt_callback()

        # Start recording speech
        self.is_recording_speech = True
        self.silence_start_time = None

        # Reset speech buffer if needed
        if len(self.speech_buffer) == 0:
            self.speech_buffer = np.array([], dtype=np.float32)

    def _handle_speech_end(self):
        """Handle detection of speech end (start silence timer)"""
        logger.debug("Speech ended - starting silence timer")
        self.silence_start_time = time.time()

    async def _handle_silence_timeout(self):
        """Handle silence timeout - transcribe accumulated speech and add to accumulated text"""
        if len(self.speech_buffer) > 0:
            logger.info("Silence timeout - transcribing speech")
            try:
                text, language = await self.transcribe_audio_buffer(self.speech_buffer)

                # Accumulate transcribed text
                if text.strip():
                    if self.accumulated_text:
                        self.accumulated_text += " " + text.strip()
                    else:
                        self.accumulated_text = text.strip()
                        self.accumulated_language = language

                    logger.info(f"Transcribed: {text}")
                    logger.info(f"Accumulated text: {self.accumulated_text}")

            except Exception as e:
                logger.error(f"Error transcribing speech: {e}")

        # Reset state
        self.is_recording_speech = False
        self.speech_buffer = np.array([], dtype=np.float32)
        self.silence_start_time = None

    async def transcribe_audio_buffer(self, audio_data: np.ndarray, language: Optional[str] = None) -> Tuple[str, str]:
        """Transcribe audio buffer using Whisper"""
        self.load_model()

        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f.name, 'wb') as wave_file:
                wave_file.setnchannels(1)
                wave_file.setsampwidth(2)
                wave_file.setframerate(self.sample_rate)

                audio_int16 = (audio_data * 32767).astype(np.int16)
                wave_file.writeframes(audio_int16.tobytes())

            temp_file = f.name

        try:
            # Run transcription in thread pool to avoid blocking
            loop = asyncio.get_event_loop()

            # Create a wrapper function to handle the arguments properly
            def transcribe_wrapper():
                if language:
                    return self.model.transcribe(temp_file, language=language, task='transcribe')
                else:
                    return self.model.transcribe(temp_file, task='transcribe')

            result = await loop.run_in_executor(None, transcribe_wrapper)

            detected_language = result.get('language', 'unknown')
            text = result.get('text', '').strip()

            return text, detected_language

        finally:
            import os
            try:
                os.unlink(temp_file)
            except OSError:
                pass

    async def process_audio_chunk(self, audio_chunk: np.ndarray):
        """Process a single audio chunk for voice activity"""
        has_voice = self.has_voice_activity(audio_chunk)

        if has_voice:
            # Voice detected
            if not self.is_recording_speech:
                self._handle_speech_start()

            # Add to speech buffer
            self.speech_buffer = np.concatenate([self.speech_buffer, audio_chunk])

        else:
            # No voice detected
            if self.is_recording_speech:
                if self.silence_start_time is None:
                    self._handle_speech_end()
                elif time.time() - self.silence_start_time > self.silence_timeout:
                    await self._handle_silence_timeout()

    async def _check_silence_timeout(self):
        """Check if silence timeout has elapsed (for when audio queue is empty)"""
        if (self.is_recording_speech and
            self.silence_start_time is not None and
            time.time() - self.silence_start_time > self.silence_timeout):
            await self._handle_silence_timeout()

    async def _process_audio_queue(self):
        """Process audio chunks from the queue in the event loop"""
        while self.is_listening:
            try:
                # Get audio chunk from queue with timeout
                try:
                    audio_chunk = self.audio_queue.get(timeout=0.1)
                    await self.process_audio_chunk(audio_chunk)
                    self.audio_queue.task_done()
                except queue.Empty:
                    # Check for silence timeout even when queue is empty
                    await self._check_silence_timeout()
                    # Small sleep to avoid busy waiting
                    await asyncio.sleep(0.1)
                    continue
            except Exception as e:
                logger.error(f"Error processing audio chunk: {e}")
                await asyncio.sleep(0.1)

    async def start_continuous_listening(self):
        """Start continuous audio listening in background"""
        self.is_listening = True
        self.loop = asyncio.get_running_loop()
        logger.info("Starting continuous audio listening")

        def audio_callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio callback status: {status}")

            # Convert to float32 and flatten
            audio_chunk = indata[:, 0].astype(np.float32)

            # Put chunk in queue for processing in the event loop
            if self.is_listening:
                try:
                    self.audio_queue.put_nowait(audio_chunk)
                except queue.Full:
                    logger.warning("Audio queue is full, dropping chunk")

        # Start audio queue processing task
        queue_task = asyncio.create_task(self._process_audio_queue())

        try:
            with sd.InputStream(
                callback=audio_callback,
                samplerate=self.sample_rate,
                channels=1,
                blocksize=self.chunk_size,
                dtype=np.float32
            ):
                while self.is_listening:
                    await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Error in continuous listening: {e}")
        finally:
            self.is_listening = False
            # Cancel queue processing task
            queue_task.cancel()
            try:
                await queue_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped continuous audio listening")

    def stop_listening(self):
        """Stop continuous listening"""
        logger.info("Stopping continuous audio listening")
        self.is_listening = False

    def get_latest_transcription(self) -> Optional[Tuple[str, str]]:
        """Get and clear the accumulated transcription result"""
        if self.accumulated_text:
            result = (self.accumulated_text, self.accumulated_language or "unknown")
            # Clear accumulated text after retrieval
            self.accumulated_text = ""
            self.accumulated_language = None
            logger.info(f"result: {self.accumulated_text}")
            return result
        return None

    def clear_accumulated_transcription(self):
        """Clear accumulated transcription without returning it"""
        self.accumulated_text = ""
        self.accumulated_language = None