import asyncio
import edge_tts
import sounddevice as sd
import tempfile
import os
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)

class EdgeTTSSpeaker:
    def __init__(self):
        self.chinese_voices = [
            "zh-CN-XiaoxiaoNeural",
            "zh-CN-YunxiNeural",
            "zh-CN-YunjianNeural",
            "zh-CN-XiaoyiNeural"
        ]
        self.english_voices = [
            "en-US-JennyNeural",
            "en-US-GuyNeural",
            "en-US-AriaNeural",
            "en-GB-SoniaNeural"
        ]

    async def get_available_voices(self) -> List[dict]:
        voices = await edge_tts.list_voices()
        return voices

    def select_voice_by_language(self, language: str, gender: str = "female") -> str:
        if language.startswith("zh") or language == "chinese":
            return self.chinese_voices[0] if gender == "female" else self.chinese_voices[1]
        else:
            return self.english_voices[0] if gender == "female" else self.english_voices[1]

    async def text_to_speech_async(
        self,
        text: str,
        voice: Optional[str] = None,
        language: str = "auto"
    ) -> bytes:
        if voice is None:
            voice = self.select_voice_by_language(language)

        logger.info(f"Converting text to speech with voice: {voice}")
        logger.info(f"Text: {text[:100]}{'...' if len(text) > 100 else ''}")

        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        return audio_data

    def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        language: str = "auto"
    ) -> bytes:
        return asyncio.run(self.text_to_speech_async(text, voice, language))

    async def speak_async(
        self,
        text: str,
        voice: Optional[str] = None,
        language: str = "auto"
    ):
        audio_data = await self.text_to_speech_async(text, voice, language)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_data)
            temp_file = f.name

        try:
            import subprocess
            subprocess.run(["afplay", temp_file], check=True)
        except subprocess.CalledProcessError:
            logger.warning("Could not play audio with afplay, trying alternative methods")
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(temp_file)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.1)
            except ImportError:
                logger.error("No audio playback method available")
        finally:
            os.unlink(temp_file)

    def speak(self, text: str, voice: Optional[str] = None, language: str = "auto"):
        asyncio.run(self.speak_async(text, voice, language))

    def save_speech_to_file(
        self,
        text: str,
        filename: str,
        voice: Optional[str] = None,
        language: str = "auto"
    ):
        audio_data = self.text_to_speech(text, voice, language)
        with open(filename, "wb") as f:
            f.write(audio_data)
        logger.info(f"Speech saved to: {filename}")