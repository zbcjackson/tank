import whisper
import sounddevice as sd
import numpy as np
import tempfile
import wave
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class WhisperTranscriber:
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model = None
        self.sample_rate = 16000

    def load_model(self):
        if self.model is None:
            logger.info(f"Loading Whisper model: {self.model_size}")
            self.model = whisper.load_model(self.model_size)

    def record_audio(self, duration: float = 5.0) -> np.ndarray:
        logger.info(f"Recording audio for {duration} seconds...")
        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32
        )
        sd.wait()
        return audio.flatten()

    def save_audio_to_temp_file(self, audio_data: np.ndarray) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f.name, 'wb') as wave_file:
                wave_file.setnchannels(1)
                wave_file.setsampwidth(2)
                wave_file.setframerate(self.sample_rate)

                audio_int16 = (audio_data * 32767).astype(np.int16)
                wave_file.writeframes(audio_int16.tobytes())

            return f.name

    def transcribe_audio(self, audio_path: str, language: Optional[str] = None) -> Tuple[str, str]:
        self.load_model()

        result = self.model.transcribe(
            audio_path,
            language=language,
            task='transcribe'
        )

        detected_language = result.get('language', 'unknown')
        text = result.get('text', '').strip()

        logger.info(f"Transcribed text ({detected_language}): {text}")
        return text, detected_language

    def transcribe_from_microphone(self, duration: float = 5.0, language: Optional[str] = None) -> Tuple[str, str]:
        audio_data = self.record_audio(duration)
        temp_file = self.save_audio_to_temp_file(audio_data)

        try:
            return self.transcribe_audio(temp_file, language)
        finally:
            import os
            os.unlink(temp_file)

    def detect_language(self, audio_path: str) -> str:
        self.load_model()
        result = self.model.transcribe(audio_path, task='transcribe')
        return result.get('language', 'unknown')