import asyncio
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

from .audio.transcription import WhisperTranscriber
from .audio.tts import EdgeTTSSpeaker
from .llm.llm import LLM, Message
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
        self.tool_manager = ToolManager()

        self.conversation_history: List[Message] = []
        self.current_language = self.config.default_language
        self.is_running = False

        logger.info("Voice Assistant initialized successfully")

    def _get_system_prompt(self) -> str:
        tools_description = self.tool_manager.get_tools_description()

        return f"""You are Tank, a helpful voice assistant that can communicate in both Chinese and English.
You can answer questions, have conversations, and use tools to accomplish tasks.

Available tools:
{tools_description}

To use a tool, include the tool call in your response using this format: tool_name(parameters)

Guidelines:
- Be conversational and natural in your responses
- Keep responses concise since they will be spoken aloud
- When asked to perform calculations or get information, use the appropriate tools
- If you don't know the answer to a question, use the web_search tool to find current information
- Use web_search for current events, recent news, real-time information, or when you're unsure about facts
- Respond in the same language as the user when possible
- If you can't understand the user's request, ask for clarification
- Always provide helpful and accurate information
- Prioritize using web search for questions about current events, recent developments, or factual information you're uncertain about
"""

    def _add_to_conversation_history(self, role: str, content: str):
        message = Message(role=role, content=content)
        self.conversation_history.append(message)

        if len(self.conversation_history) > self.config.max_conversation_history * 2:
            self.conversation_history = self.conversation_history[-self.config.max_conversation_history * 2:]

    async def _process_llm_response(self, response: str) -> str:
        tool_call = self.tool_manager.parse_tool_call(response)

        if tool_call:
            logger.info(f"Detected tool call: {tool_call}")
            tool_result = await self.tool_manager.execute_tool(
                tool_call["tool_name"],
                **tool_call["parameters"]
            )

            if "error" in tool_result:
                tool_response = f"I encountered an error: {tool_result['error']}"
            else:
                tool_response = tool_result.get("message", str(tool_result))

            final_response = response.replace(
                f"{tool_call['tool_name']}({tool_call['parameters']})",
                tool_response
            )

            return final_response

        return response

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
            response = await self.llm.simple_chat_async(
                user_message=user_input,
                system_message=system_prompt,
                conversation_history=self.conversation_history[:-1]
            )

            processed_response = await self._process_llm_response(response)
            self._add_to_conversation_history("assistant", processed_response)

            return processed_response

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
                "你好！我是Tank语音助手。你可以用中文或英文和我对话。说'退出'或'exit'来停止。",
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