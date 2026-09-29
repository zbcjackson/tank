"""Token usage observer — tracks per-turn and cumulative token consumption.

Consumes normalized ``llm_usage`` Bus messages and aggregates usage by call ID.
This optional observer is not installed by the current production assembly.

Use cases:
- Budget notification (alert when cumulative tokens exceed threshold)
- Per-session token usage tracking
- External monitoring via the ``token_budget_exceeded`` Bus event
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from ...core.token_usage import TokenUsageLedger
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
        self._usage = TokenUsageLedger()
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

        call_id = payload.get("call_id") or uuid4().hex
        if not self._usage.record_event(call_id, payload):
            return

        self._last_turn_prompt = prompt
        self._last_turn_completion = completion
        self._last_turn_total = total

        logger.debug(
            "TokenUsage: turn=%d prompt=%d completion=%d total=%d cumulative=%d",
            self.turn_count, prompt, completion, total, self._usage.total_tokens,
        )

        # Post turn_usage event for external consumers
        self._bus.post(BusMessage(
            type="token_usage",
            source="TokenUsageObserver",
            payload={
                "turn": self.turn_count,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
                "cumulative_prompt_tokens": self._usage.prompt_tokens,
                "cumulative_completion_tokens": self._usage.completion_tokens,
                "cumulative_total_tokens": self._usage.total_tokens,
            },
        ))

        # Optional notification only; observers do not stop agents.
        if (
            self._budget > 0
            and self._usage.total_tokens >= self._budget
            and not self._budget_exceeded_posted
        ):
            self._budget_exceeded_posted = True
            self._bus.post(BusMessage(
                type="token_budget_exceeded",
                source="TokenUsageObserver",
                payload={
                    "budget": self._budget,
                    "used": self._usage.total_tokens,
                    "turn": self.turn_count,
                },
            ))
            logger.warning(
                "Token budget exceeded: %d / %d tokens after %d turns",
                self._usage.total_tokens, self._budget, self.turn_count,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        """Cumulative tokens used this session."""
        return self._usage.total_tokens

    @property
    def total_prompt_tokens(self) -> int:
        return self._usage.prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        return self._usage.completion_tokens

    @property
    def turn_count(self) -> int:
        return self._usage.call_count

    def summary(self) -> dict[str, int | float]:
        """Return a summary of token usage for this session."""
        elapsed = time.time() - self._session_start
        return {
            "total_prompt_tokens": self._usage.prompt_tokens,
            "total_completion_tokens": self._usage.completion_tokens,
            "total_tokens": self._usage.total_tokens,
            "turn_count": self.turn_count,
            "estimated_tokens": self._usage.estimated_tokens,
            "unknown_calls": len(self._usage.unknown_calls),
            "elapsed_seconds": round(elapsed, 1),
            "avg_tokens_per_turn": (
                round(self._usage.total_tokens / self.turn_count)
                if self.turn_count > 0 else 0
            ),
        }

    def reset(self) -> None:
        """Reset all counters (e.g., on new conversation)."""
        self._usage = TokenUsageLedger()
        self._budget_exceeded_posted = False
        self._session_start = time.time()
