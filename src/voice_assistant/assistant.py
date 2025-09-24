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
        return """You are Tank, a helpful voice assistant.
You can answer questions, have conversations, and use available tools to accomplish tasks.

First, analyze the user's request carefully to understand their intention. Then follow these guidelines:

Core Guidelines:
- Be conversational and natural in your responses
- Keep responses concise since they will be spoken aloud
- Analyze the user's request thoroughly to understand what they really need
- Call tools multiple times if needed to ensure you have complete and accurate information
- Ask users for clarification when their request is unclear or ambiguous
- Double-check whether your final response truly matches the user's request before responding
- The goal is to accomplish the user's request accurately and completely

Tool Usage:
- When asked to perform calculations, get weather, time, or search for information, use the appropriate tools
- If you don't know the answer to a question, use the web_search tool to find current information
- Use web_search for current events, recent news, real-time information, or when you're unsure about facts
- Don't hesitate to make multiple tool calls if the first attempt doesn't fully address the user's needs
- Prioritize using web search for questions about current events, recent developments, or factual information you're uncertain about

Communication:
- Respond in the same language as the user when possible
- If you can't understand the user's request, ask for clarification
- Always provide helpful and accurate information
- Before finalizing your response, verify it addresses the user's original request and conversation context
"""

    def _add_to_conversation_history(self, role: str, content: str):
        message = Message(role=role, content=content)
        self.conversation_history.append(message)

        if len(self.conversation_history) > self.config.max_conversation_history * 2:
            self.conversation_history = self.conversation_history[-self.config.max_conversation_history * 2:]

    async def _process_llm_response(self, response: str, tool_calls=None) -> str:
        if not tool_calls:
            return response

        # Execute tool calls
        tool_results = []
        for tool_call in tool_calls:
            logger.info(f"Executing tool: {tool_call.function.name}")
            result = await self.tool_manager.execute_openai_tool_call(tool_call)

            if "error" in result:
                tool_results.append(f"Error using {tool_call.function.name}: {result['error']}")
            else:
                tool_results.append(result.get("message", str(result)))

        # Combine response with tool results
        if response:
            return f"{response}\n\n{' '.join(tool_results)}"
        else:
            return ' '.join(tool_results)

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
            messages.append(Message(role="system", content=system_prompt))
            messages.extend(self.conversation_history[:-1])  # Exclude the current user message
            messages.append(Message(role="user", content=user_input))

            response = await self.llm.chat_completion_async(
                messages=messages,
                tools=tools
            )

            message = response["choices"][0]["message"]
            content = message.get("content", "")
            tool_calls = message.get("tool_calls")

            processed_response = await self._process_llm_response(content, tool_calls)
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