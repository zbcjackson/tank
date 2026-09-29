"""Policy-free, per-call token accounting shared by tasks and telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass
class TokenUsageLedger:
    """Count usage once; unknown and estimated values never become known zero.

    This object has no admission limits, prices, persistence or execution lifecycle.
    Callers keep the same instance for the lifetime of their accounting scope.
    """

    prompt_tokens: int = field(default=0, init=False)
    completion_tokens: int = field(default=0, init=False)
    estimated_tokens: int = field(default=0, init=False)
    _calls: set[str] = field(default_factory=set, init=False, repr=False)
    _unknown: set[str] = field(default_factory=set, init=False, repr=False)
    _estimates: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens + self.estimated_tokens

    @property
    def call_count(self) -> int:
        return len(self._calls) + len(self._estimates) + len(self._unknown)

    @property
    def call_ids(self) -> frozenset[str]:
        return frozenset(self._calls | self._estimates.keys())

    @property
    def unknown_calls(self) -> frozenset[str]:
        return frozenset(self._unknown)

    def record(self, call_id: str, prompt_tokens: int, completion_tokens: int) -> bool:
        if any(type(n) is not int or n < 0 for n in (prompt_tokens, completion_tokens)):
            raise ValueError("usage must be non-negative integers")
        if call_id in self._calls:
            return False
        self.estimated_tokens -= self._estimates.pop(call_id, 0)
        self._unknown.discard(call_id)
        self._calls.add(call_id)
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        return True

    def record_estimate(self, call_id: str, total_tokens: int) -> bool:
        if type(total_tokens) is not int or total_tokens < 0:
            raise ValueError("estimated usage must be a non-negative integer")
        if call_id in self._calls or call_id in self._estimates:
            return False
        self._unknown.discard(call_id)
        self._estimates[call_id] = total_tokens
        self.estimated_tokens += total_tokens
        return True

    def record_unknown(self, call_id: str) -> bool:
        if call_id in self._calls or call_id in self._estimates or call_id in self._unknown:
            return False
        self._unknown.add(call_id)
        return True

    def record_event(self, call_id: str, metadata: Mapping[str, object]) -> bool:
        """Consume Tank's normalized USAGE event, never a provider response schema."""
        prompt, completion = metadata.get("prompt_tokens"), metadata.get("completion_tokens")
        total = metadata.get("total_tokens")
        if metadata.get("estimated") is not True and (
            "prompt_tokens" in metadata or "completion_tokens" in metadata
        ):
            if type(prompt) is not int or type(completion) is not int:
                raise ValueError("known usage requires integer input/output counts")
            if total is not None and (type(total) is not int or total != prompt + completion):
                raise ValueError("usage total disagrees with input/output counts")
            return self.record(call_id, prompt, completion)
        if type(total) is int:
            return self.record_estimate(call_id, total)
        return self.record_unknown(call_id)

    def snapshot(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "estimated_tokens": self.estimated_tokens,
            "total_tokens": self.total_tokens,
            "known_calls": len(self._calls),
            "estimated_calls": len(self._estimates),
            "unknown_calls": len(self._unknown),
        }
