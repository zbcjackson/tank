"""ContextBudget — dynamic token budget derived from model capabilities.

Replaces the fixed ``max_history_tokens`` with a budget that adapts to the
model's actual context window.  Resolution order:

1. Explicit config override (``context.context_window``)
2. Model name pattern matching (``MODEL_CONTEXT_DEFAULTS`` table)
3. Fallback: 32,000 tokens

API-based detection (``query_model_context_length``) can be called
separately to resolve the context window from the provider's ``/models``
endpoint, then passed as the ``explicit`` parameter to
``resolve_context_window``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

MIN_HISTORY_TOKENS = 2048
DEFAULT_CONTEXT_WINDOW = 32_000

# Model context windows keyed by lowercased substring.  Longest match wins
# (e.g. "gpt-4.1" beats "gpt-4" for model "gpt-4.1-mini").
#
# When adding entries, put more-specific patterns first so the longest-match
# rule works correctly.  Provider prefixes (openai/, anthropic/, deepseek/)
# are stripped before matching.
MODEL_CONTEXT_DEFAULTS: dict[str, int] = {
    # ── OpenAI ────────────────────────────────────────────────────────────
    # GPT-5 series: 400K total (272K input + 128K output) per OpenAI API docs.
    # The number here is the full context window (what the API accepts).
    "gpt-5.5": 400_000,
    "gpt-5.1": 400_000,
    "gpt-5": 400_000,
    "gpt-4.1": 1_047_576,
    "gpt-4.5": 128_000,
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4-0125": 128_000,
    "gpt-4-1106": 128_000,
    "gpt-4": 8_192,
    "o4-mini": 200_000,
    "o3": 200_000,
    "o1-mini": 128_000,
    "o1": 200_000,
    "gpt-3.5-turbo": 16_385,
    # ── Anthropic ─────────────────────────────────────────────────────────
    # Opus 4.x defaults to 200K (1M is an opt-in beta tier).
    # Sonnet 4.5/4.6 officially expanded to 1M.
    "claude-sonnet-4": 1_000_000,
    "claude-opus-4": 200_000,
    "claude-haiku-4": 200_000,
    "claude-3.5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-haiku": 200_000,
    # ── Google ─────────────────────────────────────────────────────────────
    "gemini-3": 1_048_576,
    "gemini-2.5": 1_048_576,
    "gemini-2.0": 1_048_576,
    "gemini-1.5": 1_048_576,
    "gemini-1.0": 32_000,
    # ── Meta ───────────────────────────────────────────────────────────────
    "llama-4": 10_000_000,
    "llama-3.3": 128_000,
    "llama-3.1": 128_000,
    "llama-3": 8_192,
    # ── Mistral ────────────────────────────────────────────────────────────
    "mistral-large": 128_000,
    "mistral-medium": 32_000,
    "mistral-small": 32_000,
    "mistral-nemo": 128_000,
    "codestral": 256_000,
    "mixtral-8x22b": 65_536,
    "mixtral-8x7b": 32_000,
    # ── DeepSeek ───────────────────────────────────────────────────────────
    # V4 series jumped to 1M (V3 and earlier stayed at 128K).
    "deepseek-v4": 1_000_000,
    "deepseek-r1": 128_000,
    "deepseek-v3": 128_000,
    "deepseek-chat": 128_000,
    "deepseek-coder": 128_000,
    # ── Qwen / Aliyun DashScope ────────────────────────────────────────────
    # DashScope exposes these as the model ID directly (no provider prefix).
    "qwen-long": 10_000_000,
    "qwen-turbo": 1_000_000,
    "qwen-max": 32_768,
    "qwen-plus": 131_072,
    # Open-source Qwen releases (via OpenRouter, vLLM, etc.)
    "qwen3": 128_000,
    "qwen2.5": 128_000,
    "qwen2": 32_000,
    # ── Zhipu / Z.AI (GLM series) ──────────────────────────────────────────
    # GLM-4.6/4.7 and GLM-5/5.1 are 200K; GLM-4.5 remains 128K.
    "glm-5.1": 200_000,
    "glm-5": 200_000,
    "glm-4.7": 200_000,
    "glm-4.6": 200_000,
    "glm-4.5": 128_000,
    "glm-4": 128_000,
    # ── MiniMax ────────────────────────────────────────────────────────────
    # M1 is the 1M-token lightning-attention model.
    # M2/M2.1/M2.7 are ~200K (204,800 per Vercel/OpenRouter specs).
    # abab6.5 is the older 200K series.
    "minimax-m1": 1_000_000,
    "minimax-m2": 204_800,
    "abab6.5": 200_000,
    # ── Other providers (common on OpenRouter) ─────────────────────────────
    "yi-large": 32_000,
    "yi-lightning": 16_000,
    "command-r-plus": 128_000,
    "command-r": 128_000,
    "phi-4": 16_000,
    "phi-3.5": 128_000,
    "dbrx": 32_000,
}


def resolve_context_window(model: str, explicit: int | None = None) -> int:
    """Resolve the context window for a model identifier.

    Args:
        model: Full model identifier (e.g. ``openai/gpt-4o``, ``claude-sonnet-4-6``).
        explicit: Explicit override from config.  Takes priority if set.

    Returns:
        Context window in tokens.
    """
    if explicit is not None and explicit > 0:
        return explicit

    # Strip provider prefix (e.g. "openai/" → "")
    model_id = model.split("/")[-1].lower()

    # Longest substring match wins (prevents "gpt-4" matching before "gpt-4o")
    best_match = ""
    best_window = DEFAULT_CONTEXT_WINDOW
    for pattern, window in MODEL_CONTEXT_DEFAULTS.items():
        if pattern in model_id and len(pattern) > len(best_match):
            best_match = pattern
            best_window = window

    if best_match:
        logger.debug("Context window for '%s': %d (matched '%s')", model, best_window, best_match)
        return best_window

    logger.debug("Context window for '%s': %d (fallback)", model, DEFAULT_CONTEXT_WINDOW)
    return DEFAULT_CONTEXT_WINDOW


@dataclass(frozen=True)
class ContextBudget:
    """Dynamic token budget derived from model capabilities.

    Attributes:
        context_window: Model's full context window in tokens.
        history_share: Fraction of window allocated to conversation history.
        output_reserve: Tokens reserved for LLM output.
        headroom: Safety buffer for message overhead and future turns.
        history_cap: Hard cap on effective_history_tokens (0 = no cap).
    """

    context_window: int
    history_share: float = 0.50
    output_reserve: int = 4096
    headroom: int = 2000
    history_cap: int = 0

    @property
    def effective_history_tokens(self) -> int:
        """Max tokens available for conversation history."""
        raw = int(self.context_window * self.history_share) - self.output_reserve - self.headroom
        effective = max(MIN_HISTORY_TOKENS, raw)
        if self.history_cap > 0:
            effective = min(effective, self.history_cap)
        return effective

    @property
    def tail_budget(self) -> int:
        """Token budget for the protected tail (recent messages)."""
        return int(self.effective_history_tokens * 0.20)

    @property
    def max_tool_result_tokens(self) -> int:
        """Max tokens allowed for a single tool result before pruning."""
        return int(self.effective_history_tokens * 0.30)

    @property
    def summary_budget(self) -> int:
        """Max tokens for the compaction summary."""
        return min(2000, int(self.context_window * 0.05))

    def with_history_cap(self, cap: int | None) -> ContextBudget:
        """Return a copy with an optional hard cap on history tokens.

        When ``cap > 0``, it overrides the dynamic budget.
        When ``cap == 0`` or ``None``, dynamic budget is used as-is.
        """
        if cap is not None and cap > 0:
            return ContextBudget(
                context_window=self.context_window,
                history_share=self.history_share,
                output_reserve=self.output_reserve,
                headroom=self.headroom,
                history_cap=cap,
            )
        return self


# ---------------------------------------------------------------------------
# API-based context window detection
# ---------------------------------------------------------------------------

# Simple in-memory cache: model_id → (context_window, timestamp)
_api_cache: dict[str, tuple[int, float]] = {}
_API_CACHE_TTL = 3600.0  # 1 hour


def _extract_context_length(data: dict[str, Any]) -> int | None:
    """Extract context length from a provider-specific model metadata response.

    Tries known field names in priority order:
      - ``context_length``       — OpenRouter, some vLLM deployments
      - ``max_context_tokens``   — alternative vLLM field
      - ``max_input_tokens``     — returned by some providers
      - ``max_model_len``        — vLLM native field
      - ``data.context_length``  — OpenAI-style nested response

    Also checks ``model_info`` sub-dict used by some providers (vLLM, LiteLLM).
    """
    # Top-level fields (provider-dependent naming)
    for key in ("context_length", "max_context_tokens", "max_input_tokens", "max_model_len"):
        val = data.get(key)
        if isinstance(val, int) and val > 0:
            return val

    # Nested: {"data": {"context_length": ...}} (OpenAI /models/{id} format)
    nested = data.get("data")
    if isinstance(nested, dict):
        for key in ("context_length", "max_context_tokens", "max_input_tokens"):
            val = nested.get(key)
            if isinstance(val, int) and val > 0:
                return val

    # vLLM / LiteLLM: {"model_info": {"max_model_len": ...}}
    model_info = data.get("model_info")
    if isinstance(model_info, dict):
        for key in ("max_model_len", "context_length", "max_context_tokens"):
            val = model_info.get(key)
            if isinstance(val, int) and val > 0:
                return val

    return None


async def query_model_context_length(
    model: str,
    base_url: str,
    api_key: str,
) -> int | None:
    """Query the provider's ``/models`` endpoint for the actual context length.

    Works with OpenRouter, OpenAI, vLLM, LiteLLM, and any OpenAI-compatible
    API that returns context length in model metadata.

    Args:
        model: Model identifier (e.g. ``openai/gpt-4o``).
        base_url: API base URL (e.g. ``https://openrouter.ai/api/v1``).
        api_key: API key for authentication.

    Returns:
        Context length in tokens, or ``None`` if the query fails.
    """
    import time

    import httpx

    # Check cache
    now = time.time()
    cached = _api_cache.get(model)
    if cached and now - cached[1] < _API_CACHE_TTL:
        return cached[0]

    # Strip provider prefix for the API call
    model_id = model.split("/")[-1]
    url = f"{base_url.rstrip('/')}/models/{model_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            if resp.status_code != 200:
                logger.debug("Model API returned %d for %s", resp.status_code, model_id)
                return None
            data = resp.json()

            context_length = _extract_context_length(data)
            if context_length is not None:
                _api_cache[model] = (context_length, now)
                logger.info(
                    "Detected context_length=%d for %s via API",
                    context_length,
                    model_id,
                )
                return context_length

            logger.debug("No context_length in model metadata for %s", model_id)
            return None
    except Exception:
        logger.debug("Failed to query model API for %s", model_id, exc_info=True)
        return None
