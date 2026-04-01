"""Tests for LLM retry logic with exponential backoff."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from tank_backend.llm.llm import LLM, MAX_RETRY_ATTEMPTS, RETRY_BASE_DELAY


@pytest.fixture
def llm():
    """Create LLM instance with mocked client."""
    return LLM(
        api_key="test-key",
        model="test-model",
        base_url="https://test.api",
        temperature=0.7,
        max_tokens=1000,
    )


@pytest.fixture
def mock_completion():
    """Create a mock completion response."""
    choice = MagicMock()
    choice.message.content = "Test response"
    choice.message.tool_calls = None
    choice.finish_reason = "stop"
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage.prompt_tokens = 10
    completion.usage.completion_tokens = 5
    completion.usage.total_tokens = 15
    completion.model = "test-model"
    completion.id = "test-id"
    return completion


async def test_succeeds_on_first_attempt(llm, mock_completion):
    """Test that successful requests don't retry."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_completion

        result = await llm._create_with_retry(
            model="test-model",
            messages=[{"role": "user", "content": "test"}],
        )

        assert result == mock_completion
        assert mock_create.call_count == 1


async def test_retries_on_rate_limit_then_succeeds(llm, mock_completion):
    """Test retry on RateLimitError."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [
            RateLimitError("Rate limit exceeded", response=MagicMock(), body=None),
            mock_completion,
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await llm._create_with_retry(
                model="test-model",
                messages=[{"role": "user", "content": "test"}],
            )

            assert result == mock_completion
            assert mock_create.call_count == 2
            assert mock_sleep.call_count == 1
            mock_sleep.assert_called_once_with(RETRY_BASE_DELAY)


async def test_retries_on_timeout_then_succeeds(llm, mock_completion):
    """Test retry on APITimeoutError."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [
            APITimeoutError(request=MagicMock()),
            mock_completion,
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await llm._create_with_retry(
                model="test-model",
                messages=[{"role": "user", "content": "test"}],
            )

            assert result == mock_completion
            assert mock_create.call_count == 2
            assert mock_sleep.call_count == 1


async def test_retries_on_server_error_then_succeeds(llm, mock_completion):
    """Test retry on InternalServerError."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [
            InternalServerError("Server error", response=MagicMock(), body=None),
            mock_completion,
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await llm._create_with_retry(
                model="test-model",
                messages=[{"role": "user", "content": "test"}],
            )

            assert result == mock_completion
            assert mock_create.call_count == 2
            assert mock_sleep.call_count == 1


async def test_retries_on_connection_error_then_succeeds(llm, mock_completion):
    """Test retry on APIConnectionError."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [
            APIConnectionError(request=MagicMock()),
            mock_completion,
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await llm._create_with_retry(
                model="test-model",
                messages=[{"role": "user", "content": "test"}],
            )

            assert result == mock_completion
            assert mock_create.call_count == 2
            assert mock_sleep.call_count == 1


async def test_does_not_retry_auth_error(llm):
    """Test that AuthenticationError is not retried."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = AuthenticationError(
            "Invalid API key", response=MagicMock(), body=None
        )

        with pytest.raises(AuthenticationError):
            await llm._create_with_retry(
                model="test-model",
                messages=[{"role": "user", "content": "test"}],
            )

        assert mock_create.call_count == 1


async def test_does_not_retry_bad_request(llm):
    """Test that BadRequestError is not retried."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = BadRequestError(
            "Invalid request", response=MagicMock(), body=None
        )

        with pytest.raises(BadRequestError):
            await llm._create_with_retry(
                model="test-model",
                messages=[{"role": "user", "content": "test"}],
            )

        assert mock_create.call_count == 1


async def test_exhausts_all_retries_then_raises(llm):
    """Test that all retries are exhausted before raising."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = RateLimitError("Rate limit", response=MagicMock(), body=None)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(RateLimitError):
                await llm._create_with_retry(
                    model="test-model",
                    messages=[{"role": "user", "content": "test"}],
                )

            assert mock_create.call_count == MAX_RETRY_ATTEMPTS
            assert mock_sleep.call_count == MAX_RETRY_ATTEMPTS - 1


async def test_retry_delay_is_exponential(llm):
    """Test that retry delays follow exponential backoff."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = RateLimitError("Rate limit", response=MagicMock(), body=None)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(RateLimitError):
                await llm._create_with_retry(
                    model="test-model",
                    messages=[{"role": "user", "content": "test"}],
                )

            # Verify exponential backoff: 1s, 2s
            assert mock_sleep.call_count == 2
            calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert calls[0] == RETRY_BASE_DELAY  # 1.0s
            assert calls[1] == RETRY_BASE_DELAY * 2  # 2.0s


async def test_chat_stream_uses_retry(llm, mock_completion):
    """Test that chat_stream uses retry logic."""
    # Create a mock async stream
    async def mock_stream():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "test"
        chunk.choices[0].delta.tool_calls = None
        chunk.choices[0].delta.reasoning_content = None
        yield chunk

    mock_stream_obj = MagicMock()
    mock_stream_obj.__aiter__ = lambda self: mock_stream()
    mock_stream_obj.close = AsyncMock()
    mock_stream_obj.response = MagicMock()
    mock_stream_obj.response.aclose = AsyncMock()

    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [
            RateLimitError("Rate limit", response=MagicMock(), body=None),
            mock_stream_obj,
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            gen = llm.chat_stream(
                messages=[{"role": "user", "content": "test"}],
                tools=None,
                tool_executor=None,
            )

            chunks = []
            async for update_type, content, _metadata in gen:
                chunks.append((update_type, content))

            assert mock_create.call_count == 2
            assert len(chunks) > 0


async def test_chat_completion_async_uses_retry(llm, mock_completion):
    """Test that chat_completion_async uses retry logic."""
    with patch.object(llm.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = [
            RateLimitError("Rate limit", response=MagicMock(), body=None),
            mock_completion,
        ]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await llm.chat_completion_async(
                messages=[{"role": "user", "content": "test"}],
                temperature=0.7,
                max_tokens=1000,
            )

            assert mock_create.call_count == 2
            assert result["choices"][0]["message"]["content"] == "Test response"
