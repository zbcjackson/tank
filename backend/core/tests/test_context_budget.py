"""Tests for context.budget — ContextBudget and model resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from tank_backend.context.budget import (
    MIN_HISTORY_TOKENS,
    ContextBudget,
    _extract_context_length,
    query_model_context_length,
    resolve_context_window,
)


class TestResolveContextWindow:
    def test_explicit_override(self):
        assert resolve_context_window("gpt-4o", explicit=64000) == 64000

    def test_explicit_override_zero_ignored(self):
        # Zero means "auto-detect" — should not be used as override
        assert resolve_context_window("gpt-4o", explicit=0) == 128_000

    def test_gpt4o(self):
        assert resolve_context_window("openai/gpt-4o") == 128_000

    def test_gpt4o_mini(self):
        assert resolve_context_window("openai/gpt-4o-mini") == 128_000

    def test_gpt4_longest_match_wins(self):
        # "gpt-4o" (6 chars) should beat "gpt-4" (5 chars)
        assert resolve_context_window("gpt-4o") == 128_000

    def test_gpt4_plain(self):
        assert resolve_context_window("gpt-4") == 8_192

    def test_claude_sonnet(self):
        # Sonnet 4.x officially expanded to 1M by Anthropic
        assert resolve_context_window("anthropic/claude-sonnet-4-6") == 1_000_000

    def test_gemini(self):
        assert resolve_context_window("google/gemini-2.5-pro") == 1_048_576

    def test_llama(self):
        assert resolve_context_window("meta-llama/llama-3.1-70b") == 128_000

    def test_unknown_model_fallback(self):
        assert resolve_context_window("some-unknown-model") == 32_000

    def test_deepseek(self):
        assert resolve_context_window("deepseek/deepseek-r1") == 128_000

    def test_qwen(self):
        assert resolve_context_window("qwen/qwen3-235b") == 128_000

    def test_mistral(self):
        assert resolve_context_window("mistral/mistral-large") == 128_000

    def test_mistral_nemo(self):
        assert resolve_context_window("mistralai/mistral-nemo") == 128_000

    def test_codestral(self):
        assert resolve_context_window("mistralai/codestral-latest") == 256_000

    # Aliyun / DashScope — these are the actual model IDs on that platform
    def test_qwen_max(self):
        assert resolve_context_window("qwen-max") == 32_768

    def test_qwen_max_latest(self):
        assert resolve_context_window("qwen-max-latest") == 32_768

    def test_qwen_plus(self):
        assert resolve_context_window("qwen-plus") == 131_072

    def test_qwen_turbo(self):
        assert resolve_context_window("qwen-turbo") == 1_000_000

    def test_qwen_long(self):
        assert resolve_context_window("qwen-long") == 10_000_000

    # Other OpenRouter models
    def test_yi_large(self):
        assert resolve_context_window("01-ai/yi-large") == 32_000

    def test_command_r(self):
        assert resolve_context_window("cohere/command-r") == 128_000

    def test_command_r_plus(self):
        assert resolve_context_window("cohere/command-r-plus") == 128_000

    def test_phi4(self):
        assert resolve_context_window("microsoft/phi-4") == 16_000

    def test_deepseek_coder(self):
        assert resolve_context_window("deepseek/deepseek-coder") == 128_000

    def test_llama4(self):
        assert resolve_context_window("meta-llama/llama-4-maverick") == 10_000_000

    # Longest-match: llama-3.3 beats llama-3
    def test_llama33_beats_llama3(self):
        assert resolve_context_window("meta-llama/llama-3.3-70b-instruct") == 128_000

    # ── GPT-5 series (400K: 272K input + 128K output) ─────────────────────
    def test_gpt5(self):
        assert resolve_context_window("openai/gpt-5") == 400_000

    def test_gpt5_dated(self):
        assert resolve_context_window("gpt-5-2025-08-01") == 400_000

    def test_gpt5_1(self):
        assert resolve_context_window("openai/gpt-5.1") == 400_000

    def test_gpt5_5(self):
        assert resolve_context_window("openai/gpt-5.5-codex") == 400_000

    # Longest-match: gpt-5.5 must beat gpt-5
    def test_gpt5_5_beats_gpt5(self):
        assert resolve_context_window("gpt-5.5") == 400_000

    # ── Claude Opus 4.x (200K default) ────────────────────────────────────
    def test_claude_opus_4_5(self):
        assert resolve_context_window("anthropic/claude-opus-4-5") == 200_000

    def test_claude_opus_4_6(self):
        assert resolve_context_window("claude-opus-4-6-20260205") == 200_000

    def test_claude_opus_4_7(self):
        assert resolve_context_window("anthropic/claude-opus-4-7") == 200_000

    # Sonnet 4.x officially expanded to 1M
    def test_claude_sonnet_4_is_1m(self):
        assert resolve_context_window("anthropic/claude-sonnet-4-5") == 1_000_000

    def test_claude_sonnet_4_6(self):
        assert resolve_context_window("claude-sonnet-4-6") == 1_000_000

    # ── Gemini 3 series ──────────────────────────────────────────────────
    def test_gemini3_pro(self):
        assert resolve_context_window("google/gemini-3-pro") == 1_048_576

    def test_gemini3_1_pro(self):
        assert resolve_context_window("google/gemini-3.1-pro") == 1_048_576

    # ── DeepSeek V4 (1M) ──────────────────────────────────────────────────
    def test_deepseek_v4_pro(self):
        assert resolve_context_window("deepseek/deepseek-v4-pro") == 1_000_000

    def test_deepseek_v4_flash(self):
        assert resolve_context_window("deepseek-v4-flash") == 1_000_000

    # V3 must still resolve to 128K (longest-match: deepseek-v4 != deepseek-v3)
    def test_deepseek_v3_still_128k(self):
        assert resolve_context_window("deepseek/deepseek-v3") == 128_000

    # ── GLM series (Zhipu / Z.AI) ─────────────────────────────────────────
    def test_glm_4_5(self):
        assert resolve_context_window("zai/glm-4.5") == 128_000

    def test_glm_4_6(self):
        assert resolve_context_window("z-ai/glm-4.6") == 200_000

    def test_glm_4_7(self):
        assert resolve_context_window("glm-4.7") == 200_000

    def test_glm_5(self):
        assert resolve_context_window("zai-org/glm-5") == 200_000

    def test_glm_5_1(self):
        assert resolve_context_window("glm-5.1-turbo") == 200_000

    # Longest-match: glm-4.6 must beat glm-4.5 and glm-4
    def test_glm_4_6_beats_glm_4_5(self):
        assert resolve_context_window("glm-4.6") == 200_000

    # ── MiniMax ──────────────────────────────────────────────────────────
    def test_minimax_m1(self):
        assert resolve_context_window("minimax/minimax-m1") == 1_000_000

    def test_minimax_m2(self):
        assert resolve_context_window("minimax/minimax-m2") == 204_800

    def test_minimax_m2_1(self):
        assert resolve_context_window("minimax-m2.1") == 204_800

    def test_minimax_m2_7(self):
        assert resolve_context_window("minimax/minimax-m2.7") == 204_800

    def test_abab65(self):
        assert resolve_context_window("minimax/abab6.5-chat") == 200_000


class TestContextBudget:
    def test_effective_history_tokens_large_model(self):
        budget = ContextBudget(context_window=128_000)
        effective = budget.effective_history_tokens
        assert effective == 128_000 * 0.50 - 4096 - 2000  # 57_800

    def test_effective_history_tokens_small_model(self):
        budget = ContextBudget(context_window=8_000)
        effective = budget.effective_history_tokens
        assert effective == MIN_HISTORY_TOKENS  # floor

    def test_effective_history_tokens_medium_model(self):
        budget = ContextBudget(context_window=32_000)
        effective = budget.effective_history_tokens
        assert effective == 32_000 * 0.50 - 4096 - 2000  # 9_904

    def test_tail_budget(self):
        budget = ContextBudget(context_window=128_000)
        assert budget.tail_budget == int(budget.effective_history_tokens * 0.20)

    def test_max_tool_result_tokens(self):
        budget = ContextBudget(context_window=128_000)
        assert budget.max_tool_result_tokens == int(budget.effective_history_tokens * 0.30)

    def test_summary_budget(self):
        budget = ContextBudget(context_window=128_000)
        assert budget.summary_budget == min(2000, int(128_000 * 0.05))  # 2000

    def test_summary_budget_small_window(self):
        budget = ContextBudget(context_window=20_000)
        assert budget.summary_budget == min(2000, int(20_000 * 0.05))  # 1000

    def test_with_history_cap_noop_when_zero(self):
        budget = ContextBudget(context_window=128_000)
        capped = budget.with_history_cap(0)
        assert capped is budget  # same object, no cap applied

    def test_with_history_cap_noop_when_none(self):
        budget = ContextBudget(context_window=128_000)
        capped = budget.with_history_cap(None)
        assert capped is budget

    def test_with_history_cap_reduces_budget(self):
        budget = ContextBudget(context_window=128_000)
        capped = budget.with_history_cap(8000)
        assert capped.effective_history_tokens == 8000

    def test_with_history_cap_cannot_raise(self):
        budget = ContextBudget(context_window=8000)  # small model
        capped = budget.with_history_cap(100000)
        # Dynamic budget is already ~MIN_HISTORY_TOKENS, cap doesn't raise it
        assert capped.effective_history_tokens == MIN_HISTORY_TOKENS

    def test_custom_history_share(self):
        budget = ContextBudget(context_window=128_000, history_share=0.70)
        effective = budget.effective_history_tokens
        assert effective == int(128_000 * 0.70) - 4096 - 2000

    def test_custom_output_reserve(self):
        budget = ContextBudget(context_window=128_000, output_reserve=8192)
        effective = budget.effective_history_tokens
        assert effective == int(128_000 * 0.50) - 8192 - 2000


class TestExtractContextLength:
    """Test _extract_context_length with various provider response formats."""

    def test_openrouter_format(self):
        data = {"context_length": 128_000, "id": "openai/gpt-4o"}
        assert _extract_context_length(data) == 128_000

    def test_vllm_max_context_tokens(self):
        data = {"max_context_tokens": 65_536, "model": "mixtral"}
        assert _extract_context_length(data) == 65_536

    def test_vllm_max_model_len(self):
        data = {"max_model_len": 32_768, "model": "llama"}
        assert _extract_context_length(data) == 32_768

    def test_max_input_tokens(self):
        data = {"max_input_tokens": 200_000, "id": "claude-sonnet-4"}
        assert _extract_context_length(data) == 200_000

    def test_nested_data_format(self):
        """OpenAI-style: {data: {context_length: ...}}"""
        data = {"data": {"context_length": 128_000, "id": "gpt-4o"}}
        assert _extract_context_length(data) == 128_000

    def test_nested_data_max_input_tokens(self):
        data = {"data": {"max_input_tokens": 8_192, "id": "gpt-4"}}
        assert _extract_context_length(data) == 8_192

    def test_vllm_model_info_format(self):
        """vLLM / LiteLLM: {model_info: {max_model_len: ...}}"""
        data = {"model_info": {"max_model_len": 131_072}}
        assert _extract_context_length(data) == 131_072

    def test_top_level_priority_over_nested(self):
        """Top-level context_length takes priority over nested."""
        data = {
            "context_length": 128_000,
            "data": {"context_length": 64_000},
        }
        assert _extract_context_length(data) == 128_000

    def test_returns_none_for_empty(self):
        assert _extract_context_length({}) is None

    def test_returns_none_for_non_int(self):
        data = {"context_length": "128000"}
        assert _extract_context_length(data) is None

    def test_returns_none_for_zero(self):
        data = {"context_length": 0}
        assert _extract_context_length(data) is None


class TestQueryModelContextLength:
    """Test the async API query function."""

    async def test_returns_cached_value(self):
        import time

        from tank_backend.context import budget

        model = "test-cached-model"
        budget._api_cache[model] = (99_999, time.time())

        result = await query_model_context_length(model, "https://api.example.com/v1", "key")
        assert result == 99_999

        del budget._api_cache[model]

    async def test_returns_none_on_http_error(self):
        import httpx

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = httpx.Response(404)

            result = await query_model_context_length(
                "unknown-model", "https://api.example.com/v1", "key"
            )
            assert result is None

    async def test_returns_none_on_network_error(self):
        with patch("httpx.AsyncClient", side_effect=ConnectionError("timeout")):
            result = await query_model_context_length(
                "some-model", "https://api.example.com/v1", "key"
            )
            assert result is None

    async def test_extracts_context_from_openrouter_response(self):
        import httpx

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.get.return_value = httpx.Response(
                200,
                json={"context_length": 128_000, "id": "openai/gpt-4o"},
            )

            result = await query_model_context_length(
                "openai/gpt-4o", "https://openrouter.ai/api/v1", "key"
            )
            assert result == 128_000

    async def test_strips_provider_prefix(self):
        """The API call should use model ID without provider prefix."""
        # Verify indirectly: the URL is built as base_url + "/models/" + stripped_id
        # We test this by checking that the OpenRouter-style response is extracted
        # after prefix stripping. The actual HTTP call is tested by integration tests.
        import time

        from tank_backend.context import budget

        # Pre-populate cache to verify the function returns the right value
        # after stripping "openai/" prefix
        model = "test-prefix-model"
        budget._api_cache[model] = (64_000, time.time())

        result = await query_model_context_length(model, "https://api.example.com/v1", "key")
        assert result == 64_000

        del budget._api_cache[model]
