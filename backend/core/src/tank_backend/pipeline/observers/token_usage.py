"""Token usage observer — tracks per-turn and cumulative token consumption.

Subscribes to ``llm_usage`` Bus messages (posted by Brain after each LLM
iteration via the USAGE yield from ``chat_stream``) and accumulates
prompt/completion/total token counts.

Use cases:
- Budget enforcement (alert when cumulative tokens exceed threshold)
- Per-session cost tracking
- External monitoring via the ``token_budget_exceeded`` Bus event
"""

from __future__ import annotations

import logging
import time

from ..bus import Bus, BusMessage

logger = logging.getLogger(__name__)


class TokenUsageObserver:
    """Accumulates token usage and posts budget alerts.

    Subscribes to ``llm_usage`` messages. When ``budget_tokens`` is set,
    posts a ``token_budget_exceeded`` message the first time cumulative
    tokens cross the threshold.
    """

    def __init__(
        self,
        bus: Bus,
        budget_tokens: int = 0,
    ) -> None:
        self._bus = bus
        self._budget = budget_tokens
        self._budget_exceeded_posted = False

        # Per-session accumulators
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_tokens = 0
        self._turn_count = 0
        self._session_start = time.time()

        # Per-turn snapshot (last seen)
        self._last_turn_prompt = 0
        self._last_turn_completion = 0
        self._last_turn_total = 0

        bus.subscribe("llm_usage", self._on_llm_usage)

    def _on_llm_usage(self, message: BusMessage) -> None:
        """Handle an llm_usage Bus message from Brain."""
        payload = message.payload
        if not isinstance(payload, dict):
            return

        prompt = payload.get("prompt_tokens", 0)
        completion = payload.get("completion_tokens", 0)
        total = payload.get("total_tokens", 0)

        self._total_prompt_tokens += prompt
        self._total_completion_tokens += completion
        self._total_tokens += total
        self._turn_count += 1

        self._last_turn_prompt = prompt
        self._last_turn_completion = completion
        self._last_turn_total = total

        logger.debug(
            "TokenUsage: turn=%d prompt=%d completion=%d total=%d cumulative=%d",
            self._turn_count, prompt, completion, total, self._total_tokens,
        )

        # Post turn_usage event for external consumers
        self._bus.post(BusMessage(
            type="token_usage",
            source="TokenUsageObserver",
            payload={
                "turn": self._turn_count,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
                "cumulative_prompt_tokens": self._total_prompt_tokens,
                "cumulative_completion_tokens": self._total_completion_tokens,
                "cumulative_total_tokens": self._total_tokens,
            },
        ))

        # Budget enforcement
        if (
            self._budget > 0
            and self._total_tokens >= self._budget
            and not self._budget_exceeded_posted
        ):
            self._budget_exceeded_posted = True
            self._bus.post(BusMessage(
                type="token_budget_exceeded",
                source="TokenUsageObserver",
                payload={
                    "budget": self._budget,
                    "used": self._total_tokens,
                    "turn": self._turn_count,
                },
            ))
            logger.warning(
                "Token budget exceeded: %d / %d tokens after %d turns",
                self._total_tokens, self._budget, self._turn_count,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        """Cumulative tokens used this session."""
        return self._total_tokens

    @property
    def total_prompt_tokens(self) -> int:
        return self._total_prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        return self._total_completion_tokens

    @property
    def turn_count(self) -> int:
        return self._turn_count

    def summary(self) -> dict[str, int | float]:
        """Return a summary of token usage for this session."""
        elapsed = time.time() - self._session_start
        return {
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_tokens": self._total_tokens,
            "turn_count": self._turn_count,
            "elapsed_seconds": round(elapsed, 1),
            "avg_tokens_per_turn": (
                round(self._total_tokens / self._turn_count)
                if self._turn_count > 0 else 0
            ),
        }

    def reset(self) -> None:
        """Reset all counters (e.g., on new conversation)."""
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_tokens = 0
        self._turn_count = 0
        self._budget_exceeded_posted = False
        self._session_start = time.time()
