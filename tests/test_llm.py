import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from src.voice_assistant.llm.llm import LLM

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

            messages = [{"role": "user", "content": "Hello"}]
            result = await llm.chat_completion_async(messages)

            assert result["choices"][0]["message"]["content"] == "Test response"

    @pytest.mark.asyncio
    async def test_chat_completion_with_messages(self, llm):
        with patch.object(llm.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = Mock()
            mock_response.choices[0].message.role = "assistant"
            mock_response.choices[0].message.content = "Hello back!"
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage = Mock()
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 5
            mock_response.usage.total_tokens = 15
            mock_response.model = "test/model"
            mock_response.id = "test_id"

            mock_create.return_value = mock_response

            messages = [{"role": "user", "content": "Hello"}]
            result = await llm.chat_completion_async(messages)
            assert result["choices"][0]["message"]["content"] == "Hello back!"

    def test_message_format(self):
        # Test basic message format
        message = {"role": "user", "content": "Test"}
        assert message["role"] == "user"
        assert message["content"] == "Test"

        # Test tool message format
        tool_message = {
            "role": "tool",
            "content": "Tool result",
            "tool_call_id": "call_123",
            "name": "test_tool"
        }
        assert tool_message["role"] == "tool"
        assert tool_message["content"] == "Tool result"
        assert tool_message["tool_call_id"] == "call_123"
        assert tool_message["name"] == "test_tool"

        # Test assistant message with optional content
        assistant_message = {"role": "assistant", "content": None}
        assert assistant_message["role"] == "assistant"
        assert assistant_message["content"] is None

    @pytest.mark.asyncio
    async def test_chat_completion_with_tool_calls(self, llm):
        # Mock tool executor
        mock_tool_executor = Mock()
        mock_tool_executor.execute_openai_tool_call = AsyncMock()
        mock_tool_executor.execute_openai_tool_call.return_value = {
            "message": "Tool executed successfully",
            "result": 42
        }

        with patch.object(llm.client.chat.completions, 'create', new_callable=AsyncMock) as mock_create:
            # First response: assistant with tool calls
            mock_tool_call = Mock()
            mock_tool_call.id = "call_123"
            mock_tool_call.function.name = "test_tool"
            mock_tool_call.function.arguments = '{"query": "test"}'

            first_response = Mock()
            first_response.choices = [Mock()]
            first_response.choices[0].message = Mock()
            first_response.choices[0].message.role = "assistant"
            first_response.choices[0].message.content = None
            first_response.choices[0].message.tool_calls = [mock_tool_call]
            first_response.choices[0].finish_reason = "tool_calls"
            first_response.usage = Mock()
            first_response.usage.prompt_tokens = 10
            first_response.usage.completion_tokens = 5
            first_response.usage.total_tokens = 15
            first_response.model = "test/model"
            first_response.id = "test_id_1"

            # Second response: final assistant response
            second_response = Mock()
            second_response.choices = [Mock()]
            second_response.choices[0].message = Mock()
            second_response.choices[0].message.role = "assistant"
            second_response.choices[0].message.content = "Based on the tool result, the answer is 42."
            # Ensure no tool_calls in final response
            delattr(second_response.choices[0].message, 'tool_calls') if hasattr(second_response.choices[0].message, 'tool_calls') else None
            second_response.choices[0].finish_reason = "stop"
            second_response.usage = Mock()
            second_response.usage.prompt_tokens = 15
            second_response.usage.completion_tokens = 10
            second_response.usage.total_tokens = 25
            second_response.model = "test/model"
            second_response.id = "test_id_2"

            # Mock the API calls - first returns tool call, second returns final answer
            mock_create.side_effect = [first_response, second_response]

            messages = [{"role": "user", "content": "What is the answer?"}]
            result = await llm.chat_completion_async(
                messages=messages,
                tools=[{"type": "function", "function": {"name": "test_tool"}}],
                tool_executor=mock_tool_executor
            )

            # Verify the result
            assert result["choices"][0]["message"]["content"] == "Based on the tool result, the answer is 42."
            assert result["tool_iterations"] == 2
            assert result["usage"]["total_tokens"] == 40  # 15 + 25 from both calls

            # Verify tool executor was called
            mock_tool_executor.execute_openai_tool_call.assert_called_once_with(mock_tool_call)

            # Verify API was called twice (once with tool call, once with tool result)
            assert mock_create.call_count == 2