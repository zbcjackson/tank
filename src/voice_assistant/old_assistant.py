import asyncio
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from openai.types.chat import ChatCompletionMessageParam

from .audio.continuous_transcription import ContinuousTranscriber
from .audio.output.tts_engine_edge import EdgeTTSEngine
from .llm.llm import LLM
from .tools.manager import ToolManager
from .config.settings import VoiceAssistantConfig, load_config, setup_logging

logger = logging.getLogger(__name__)

class VoiceAssistant:
    def __init__(self, config_path: Optional[Path] = None):
        self.config = load_config(config_path)
        setup_logging(self.config.log_level)

        self.transcriber = ContinuousTranscriber(self.config.whisper_model_size)
        self.speaker = EdgeTTSEngine(self.config)
        self.llm = LLM(
            api_key=self.config.llm_api_key,
            model=self.config.llm_model,
            base_url=self.config.llm_base_url
        )
        self.tool_manager = ToolManager(serper_api_key=self.config.serper_api_key)

        self.conversation_history: List[ChatCompletionMessageParam] = []
        self.current_language = self.config.default_language
        self.is_running = False

        # Current task management for interruption
        self.current_llm_task = None
        self.current_tts_task = None

        # Set up interruption callback
        self.transcriber.set_interrupt_callback(self._handle_speech_interruption)

        logger.info("Voice Assistant initialized successfully")

    def _handle_speech_interruption(self):
        """Handle speech interruption - cancel current tasks"""
        logger.info("Speech detected - interrupting current tasks")

        # Interrupt TTS
        self.speaker.interrupt_speech()

        # Cancel current LLM task if running
        if self.current_llm_task and not self.current_llm_task.done():
            self.current_llm_task.cancel()
            logger.info("Cancelled LLM task due to speech interruption")

        # Cancel current TTS task if running
        if self.current_tts_task and not self.current_tts_task.done():
            self.current_tts_task.cancel()
            logger.info("Cancelled TTS task due to speech interruption")

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

    async def wait_for_speech_input(self) -> Optional[str]:
        """Wait for speech input from continuous transcriber"""
        try:
            # Wait for transcription to become available
            while self.is_running:
                transcription = self.transcriber.get_latest_transcription()
                logger.info("Transcription received: %s", transcription)
                if transcription:
                    text, detected_language = transcription
                    if text.strip():
                        self.current_language = detected_language
                        logger.info(f"Received speech ({detected_language}): {text}")
                        return text  # Return the transcribed text

                # Small sleep to avoid busy waiting
                await asyncio.sleep(0.1)

            return None

        except Exception as e:
            logger.error(f"Error waiting for speech input: {e}")
            return None

    async def generate_response(self, user_input: str) -> str:
        logger.info(f"Generating response: {user_input}")
        try:
            self._add_to_conversation_history("user", user_input)

            system_prompt = self._get_system_prompt()
            tools = self.tool_manager.get_openai_tools()

            # Build messages for the API call
            messages = []
            messages.append({"role": "system", "content": system_prompt})
            messages.extend(self.conversation_history[:-1])  # Exclude the current user message
            messages.append({"role": "user", "content": user_input})

            # Create LLM task and track it for potential cancellation
            self.current_llm_task = asyncio.create_task(
                self.llm.chat_completion_async(
                    messages=messages,
                    tools=tools,
                    tool_executor=self.tool_manager
                )
            )

            try:
                response = await self.current_llm_task
            except asyncio.CancelledError:
                logger.info("LLM task was cancelled due to speech interruption")
                return ""

            message = response["choices"][0]["message"]
            content = message.get("content", "")

            # Log tool iterations if any occurred
            if response.get("tool_iterations", 0) > 1:
                logger.info(f"Completed response after {response['tool_iterations']} tool iterations")

            self._add_to_conversation_history("assistant", content)
            return content

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "对不起，出现错误，请重试。"
        finally:
            self.current_llm_task = None

    async def speak_response(self, text: str):
        if not text.strip():  # Don't speak empty responses
            return

        try:
            voice = self._determine_voice(text, self.current_language)

            # Create TTS task and track it for potential cancellation
            self.current_tts_task = asyncio.create_task(
                self.speaker.speak_async(text, voice=voice, language=self.current_language)
            )

            try:
                await self.current_tts_task
            except asyncio.CancelledError:
                logger.info("TTS task was cancelled due to speech interruption")

        except Exception as e:
            logger.error(f"Error speaking response: {e}")
        finally:
            self.current_tts_task = None

    async def conversation_loop(self):
        self.is_running = True

        try:
            # Start welcome message
            await self.speak_response("你好！我是Tank语音助手。")

            # Start continuous listening in background
            listening_task = asyncio.create_task(self.transcriber.start_continuous_listening())

            print("🎤 Tank is listening ...")

            while self.is_running:
                # Wait for speech input
                user_input = await self.wait_for_speech_input()

                if user_input:
                    # Check for exit commands
                    if user_input.lower().strip() in ["quit", "exit", "stop", "bye", "goodbye", "退出", "再见", "停止"]:
                        await self.speak_response("再见！祝你有美好的一天！")
                        break

                    print(f"🗣️  You said: {user_input}")

                    # Generate response (can be interrupted)
                    response = await self.generate_response(user_input)

                    if response:  # Only speak if we got a response (not interrupted)
                        # Clear transcription after LLM response is delivered
                        self.transcriber.clear_transcription_after_response()
                        print(f"🤖 Assistant: {response}")
                        await self.speak_response(response)

        except KeyboardInterrupt:
            logger.info("Conversation interrupted by user")
        except Exception as e:
            logger.error(f"Error in conversation loop: {e}")
        finally:
            self.is_running = False
            self.transcriber.stop_listening()

            # Wait for listening task to complete
            if 'listening_task' in locals():
                listening_task.cancel()
                try:
                    await listening_task
                except asyncio.CancelledError:
                    pass

            await self.speak_response("语音助手已停止。再见！")

    async def check_system_status(self) -> Dict[str, Any]:
        status = {
            "continuous_transcriber": "unknown",
            "speaker": "unknown",
            "llm": "unknown",
            "tools": len(self.tool_manager.tools)
        }

        try:
            self.transcriber.load_model()
            status["continuous_transcriber"] = "ready"
        except Exception as e:
            status["continuous_transcriber"] = f"error: {e}"

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