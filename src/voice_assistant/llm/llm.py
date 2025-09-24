import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel, Field
import logging
from openai import AsyncOpenAI
from openai import APIError, RateLimitError, APIConnectionError, AuthenticationError

logger = logging.getLogger(__name__)

class Message(BaseModel):
    role: str = Field(..., description="The role of the message sender")
    content: str = Field(..., description="The content of the message")

class LLM:
    def __init__(self, api_key: str, model: str = "anthropic/claude-3-5-nano", base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

        # Initialize OpenAI client with custom base URL and headers
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "Tank Voice Assistant"
            }
        )

    async def chat_completion_async(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False
    ) -> Dict[str, Any]:
        try:
            # Convert Message objects to dict format expected by OpenAI client
            message_dicts = [{"role": msg.role, "content": msg.content} for msg in messages]

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=message_dicts,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )

            # Convert response to dict format for compatibility
            return {
                "choices": [
                    {
                        "message": {
                            "role": response.choices[0].message.role,
                            "content": response.choices[0].message.content
                        },
                        "finish_reason": response.choices[0].finish_reason
                    }
                ],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                } if response.usage else None,
                "model": response.model,
                "id": response.id
            }
        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise
        except RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded: {e}")
            raise
        except APIConnectionError as e:
            logger.error(f"OpenAI API connection error: {e}")
            raise
        except AuthenticationError as e:
            logger.error(f"OpenAI authentication error: {e}")
            raise
        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise

    async def chat_completion_stream_async(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> AsyncGenerator[str, None]:
        try:
            # Convert Message objects to dict format expected by OpenAI client
            message_dicts = [{"role": msg.role, "content": msg.content} for msg in messages]

            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=message_dicts,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )

            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
        except APIError as e:
            logger.error(f"OpenAI API stream error: {e}")
            raise
        except RateLimitError as e:
            logger.error(f"OpenAI stream rate limit exceeded: {e}")
            raise
        except APIConnectionError as e:
            logger.error(f"OpenAI stream API connection error: {e}")
            raise
        except AuthenticationError as e:
            logger.error(f"OpenAI stream authentication error: {e}")
            raise
        except Exception as e:
            logger.error(f"Chat completion stream error: {e}")
            raise

    def chat_completion(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> str:
        import asyncio
        result = asyncio.run(self.chat_completion_async(messages, temperature, max_tokens))
        return result["choices"][0]["message"]["content"]

    async def simple_chat_async(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        conversation_history: Optional[List[Message]] = None
    ) -> str:
        messages = []

        if system_message:
            messages.append(Message(role="system", content=system_message))

        if conversation_history:
            messages.extend(conversation_history)

        messages.append(Message(role="user", content=user_message))

        logger.info(f"Sending {len(messages)} messages to LLM")
        logger.debug(f"User message: {user_message}")

        result = await self.chat_completion_async(messages)
        response = result["choices"][0]["message"]["content"]

        logger.info(f"LLM response: {response[:100]}{'...' if len(response) > 100 else ''}")
        return response

    def simple_chat(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        conversation_history: Optional[List[Message]] = None
    ) -> str:
        import asyncio
        return asyncio.run(self.simple_chat_async(user_message, system_message, conversation_history))

    async def check_connection(self) -> bool:
        try:
            test_messages = [Message(role="user", content="Hello, can you hear me?")]
            await self.chat_completion_async(test_messages, max_tokens=16)
            return True
        except APIError as e:
            logger.error(f"Connection check API error: {e}")
            return False
        except RateLimitError as e:
            logger.error(f"Connection check rate limit exceeded: {e}")
            return False
        except APIConnectionError as e:
            logger.error(f"Connection check API connection error: {e}")
            return False
        except AuthenticationError as e:
            logger.error(f"Connection check authentication error: {e}")
            return False
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False