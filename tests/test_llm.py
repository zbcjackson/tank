import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from src.voice_assistant.llm.llm import LLM, Message

class TestLLM:
    @pytest.fixture
    def llm(self):
        return LLM(api_key="test_key", model="test/model", base_url="https://test.api.com")

    def test_initialization(self, llm):
        assert llm.api_key == "test_key"
        assert llm.model == "test/model"
        assert llm.base_url == "https://test.api.com"
        assert hasattr(llm, 'client')
        assert llm.client.api_key == "test_key"

    def test_default_initialization(self):
        llm = LLM(api_key="test_key")
        assert llm.api_key == "test_key"
        assert llm.model == "anthropic/claude-3-5-nano"
        assert llm.base_url == "https://openrouter.ai/api/v1"

    @pytest.mark.asyncio
    async def test_chat_completion_async(self, llm):
        with patch.object(llm.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = Mock()
            mock_response.choices[0].message.role = "assistant"
            mock_response.choices[0].message.content = "Test response"
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage = Mock()
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 5
            mock_response.usage.total_tokens = 15
            mock_response.model = "test/model"
            mock_response.id = "test_id"

            mock_create.return_value = mock_response

            messages = [Message(role="user", content="Hello")]
            result = await llm.chat_completion_async(messages)

            assert result["choices"][0]["message"]["content"] == "Test response"

    @pytest.mark.asyncio
    async def test_simple_chat_async(self, llm):
        with patch.object(llm, 'chat_completion_async') as mock_completion:
            mock_completion.return_value = {
                "choices": [{"message": {"content": "Hello back!"}}]
            }

            response = await llm.simple_chat_async("Hello")
            assert response == "Hello back!"

    def test_message_model(self):
        message = Message(role="user", content="Test")
        assert message.role == "user"
        assert message.content == "Test"