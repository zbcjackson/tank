import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from src.voice_assistant.llm.openrouter import OpenRouterLLM, Message

class TestOpenRouterLLM:
    @pytest.fixture
    def llm(self):
        return OpenRouterLLM(api_key="test_key", model="test/model", base_url="https://test.api.com")

    def test_initialization(self, llm):
        assert llm.api_key == "test_key"
        assert llm.model == "test/model"
        assert llm.base_url == "https://test.api.com"
        assert "Authorization" in llm.headers

    def test_default_initialization(self):
        llm = OpenRouterLLM(api_key="test_key")
        assert llm.api_key == "test_key"
        assert llm.model == "anthropic/claude-3-5-nano"
        assert llm.base_url == "https://openrouter.ai/api/v1"

    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_chat_completion_async(self, mock_client, llm):
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        mock_response.raise_for_status.return_value = None

        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)

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