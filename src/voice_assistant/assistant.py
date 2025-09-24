import asyncio
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from openai.types.chat import ChatCompletionMessageParam

from .audio.transcription import WhisperTranscriber
from .audio.tts import EdgeTTSSpeaker
from .llm.llm import LLM
from .tools.manager import ToolManager
from .config.settings import VoiceAssistantConfig, load_config, setup_logging

logger = logging.getLogger(__name__)

class VoiceAssistant:
    def __init__(self, config_path: Optional[Path] = None):
        self.config = load_config(config_path)
        setup_logging(self.config.log_level)

        self.transcriber = WhisperTranscriber(self.config.whisper_model_size)
        self.speaker = EdgeTTSSpeaker()
        self.llm = LLM(
            api_key=self.config.llm_api_key,
            model=self.config.llm_model,
            base_url=self.config.llm_base_url
        )
        self.tool_manager = ToolManager(serper_api_key=self.config.serper_api_key)

        self.conversation_history: List[ChatCompletionMessageParam] = []
        self.current_language = self.config.default_language
        self.is_running = False

        logger.info("Voice Assistant initialized successfully")

    def _get_system_prompt(self) -> str:
        return """You are Tank, a helpful voice assistant that provides conversational, spoken responses.

WORKFLOW:
1. Analyze the user's request to understand their true intention
2. Use tools to gather necessary information (call multiple times if needed)
3. Summarize and verify all tool information matches the user's request
4. Provide a concise, accurate response in the user's language

TOOL USAGE:
- Use appropriate tools for calculations, weather, time, and web searches
- For current events, news, or uncertain facts: use web_search
- If first attempt is insufficient, make additional tool calls
- Before responding, confirm all gathered information fully addresses the user's request

RESPONSE REQUIREMENTS:
- Keep responses concise (they will be spoken aloud)
- Be conversational and natural
- Ask for clarification when requests are unclear
- Match the user's language when possible
- Verify your response addresses their original request and conversation context

Your goal: Accomplish user requests accurately and completely through proper tool usage and verification.
"""

    def _add_to_conversation_history(self, role: str, content: str):
        message = {"role": role, "content": content}
        self.conversation_history.append(message)

        if len(self.conversation_history) > self.config.max_conversation_history * 2:
            self.conversation_history = self.conversation_history[-self.config.max_conversation_history * 2:]


    def _determine_voice(self, text: str, detected_language: str = None) -> str:
        if detected_language:
            if detected_language.startswith("zh"):
                return self.config.tts_voice_zh
            else:
                return self.config.tts_voice_en

        import re
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        if len(chinese_chars) > len(text) * 0.3:
            return self.config.tts_voice_zh
        else:
            return self.config.tts_voice_en

    async def process_voice_input(self, duration: float = None) -> Optional[str]:
        if duration is None:
            duration = self.config.audio_duration

        try:
            logger.info("Listening for voice input...")
            text, detected_language = self.transcriber.transcribe_from_microphone(
                duration=duration,
                language=self.current_language if self.current_language != "auto" else None
            )

            if not text.strip():
                logger.warning("No speech detected")
                return None

            self.current_language = detected_language
            logger.info(f"Transcribed ({detected_language}): {text}")

            return text

        except Exception as e:
            logger.error(f"Error processing voice input: {e}")
            await self.speaker.speak_async("Sorry, I couldn't hear you clearly. Please try again.")
            return None

    async def generate_response(self, user_input: str) -> str:
        try:
            self._add_to_conversation_history("user", user_input)

            system_prompt = self._get_system_prompt()
            tools = self.tool_manager.get_openai_tools()

            # Build messages for the API call
            messages = []
            messages.append({"role": "system", "content": system_prompt})
            messages.extend(self.conversation_history[:-1])  # Exclude the current user message
            messages.append({"role": "user", "content": user_input})

            # Pass the tool_manager as tool_executor to handle tool calls automatically
            response = await self.llm.chat_completion_async(
                messages=messages,
                tools=tools,
                tool_executor=self.tool_manager
            )

            message = response["choices"][0]["message"]
            content = message.get("content", "")

            # Log tool iterations if any occurred
            if response.get("tool_iterations", 0) > 1:
                logger.info(f"Completed response after {response['tool_iterations']} tool iterations")

            self._add_to_conversation_history("assistant", content)
            return content

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm sorry, I encountered an error while processing your request. Please try again."

    async def speak_response(self, text: str):
        try:
            voice = self._determine_voice(text, self.current_language)
            await self.speaker.speak_async(text, voice=voice, language=self.current_language)
        except Exception as e:
            logger.error(f"Error speaking response: {e}")

    async def conversation_loop(self):
        self.is_running = True
        logger.info("Starting voice assistant conversation loop")

        try:
            await self.speaker.speak_async(
                "你好！我是Tank语音助手。说'退出'来停止。",
                voice=self.config.tts_voice_zh
            )

            while self.is_running:
                print("\n🎤 Listening... (Press Ctrl+C to stop)")

                user_input = await self.process_voice_input()

                if user_input:
                    if user_input.lower().strip() in ["quit", "exit", "stop", "bye", "goodbye", "退出", "再见", "停止"]:
                        await self.speaker.speak_async("再见！祝你有美好的一天！", voice=self.config.tts_voice_zh)
                        break

                    print(f"🗣️  You said: {user_input}")

                    response = await self.generate_response(user_input)
                    print(f"🤖 Assistant: {response}")

                    await self.speak_response(response)

        except KeyboardInterrupt:
            logger.info("Conversation interrupted by user")
        except Exception as e:
            logger.error(f"Error in conversation loop: {e}")
        finally:
            self.is_running = False
            await self.speaker.speak_async("语音助手已停止。再见！", voice=self.config.tts_voice_zh)

    def stop(self):
        self.is_running = False
        logger.info("Voice assistant stop requested")

    async def check_system_status(self) -> Dict[str, Any]:
        status = {
            "transcriber": "unknown",
            "speaker": "unknown",
            "llm": "unknown",
            "tools": len(self.tool_manager.tools)
        }

        try:
            self.transcriber.load_model()
            status["transcriber"] = "ready"
        except Exception as e:
            status["transcriber"] = f"error: {e}"

        try:
            await self.speaker.speak_async("System check", voice=self.config.tts_voice_en)
            status["speaker"] = "ready"
        except Exception as e:
            status["speaker"] = f"error: {e}"

        try:
            if await self.llm.check_connection():
                status["llm"] = "ready"
            else:
                status["llm"] = "connection failed"
        except Exception as e:
            status["llm"] = f"error: {e}"

        return status