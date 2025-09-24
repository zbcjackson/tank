import httpx
import json
from typing import List, Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

class Message(BaseModel):
    role: str = Field(..., description="The role of the message sender")
    content: str = Field(..., description="The content of the message")

class LLM:
    def __init__(self, api_key: str, model: str = "anthropic/claude-3-5-nano", base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "Voice Assistant"
        }

    async def chat_completion_async(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=60.0
            )
            response.raise_for_status()
            return response.json()

    async def chat_completion_stream_async(
        self,
        messages: List[Message],
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                url,
                headers=self.headers,
                json=payload,
                timeout=60.0
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            continue

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
            await self.chat_completion_async(test_messages, max_tokens=10)
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False