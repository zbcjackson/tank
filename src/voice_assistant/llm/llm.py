import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import logging
from openai import AsyncOpenAI

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
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        try:
            # Convert Message objects to dict format expected by OpenAI client
            message_dicts = [{"role": msg.role, "content": msg.content} for msg in messages]

            # Prepare kwargs for the API call
            api_kwargs = {
                "model": self.model,
                "messages": message_dicts,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream
            }

            # Add tools if provided
            if tools:
                api_kwargs["tools"] = tools

            response = await self.client.chat.completions.create(**api_kwargs)

            # Convert response to dict format for compatibility
            choice = response.choices[0]
            result = {
                "choices": [{
                    "message": {
                        "role": choice.message.role,
                        "content": choice.message.content
                    },
                    "finish_reason": choice.finish_reason
                }],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                } if response.usage else None,
                "model": response.model,
                "id": response.id
            }

            # Add tool calls if present
            if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
                result["choices"][0]["message"]["tool_calls"] = choice.message.tool_calls

            return result
        except Exception as e:
            logger.error(f"Chat completion error: {e}")
            raise

    async def check_connection(self) -> bool:
        try:
            test_messages = [Message(role="user", content="Hello, can you hear me?")]
            await self.chat_completion_async(test_messages, max_tokens=16)
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False