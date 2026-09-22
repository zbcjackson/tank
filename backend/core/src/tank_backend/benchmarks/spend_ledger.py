"""Offline reservation arithmetic; callers must verify request bounds and prices."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO, TypedDict


class SpendLimitExceeded(RuntimeError):
    """The ledger stopped admission; this does not certify physical cleanup."""


@dataclass(frozen=True)
class SpendLimit:
    tokens: int
    nano_usd: int

    def __post_init__(self) -> None:
        if any(type(n) is not int or n < 0 for n in (self.tokens, self.nano_usd)):
            raise ValueError("Spend limits must be non-negative integers")


@dataclass(frozen=True)
class TokenAllowance:
    """Caller-verified token upper bounds and upper prices in nano-USD/token."""

    input_tokens: int
    output_tokens: int
    input_nano_usd: int
    output_nano_usd: int

    def __post_init__(self) -> None:
        if any(
            type(n) is not int or n < 0
            for n in (
                self.input_tokens,
                self.output_tokens,
                self.input_nano_usd,
                self.output_nano_usd,
            )
        ):
            raise ValueError("Allowances and prices must be non-negative integers")


@dataclass
class _Reservation:
    trial: str
    allowance: TokenAllowance
    input_tokens: int | None = None
    output_tokens: int | None = None
    status: str = "pending"


class SpendSnapshot(TypedDict):
    record_only: bool
    cost_status: str
    batch: dict[str, int]
    trials: dict[str, dict[str, int]]
    stop_reason: str | None
    requests: dict[str, dict[str, object]]


class SpendLedger:
    """One serial batch; monetary units are integer billionths of one USD."""

    def __init__(
        self, limit: SpendLimit, *, journal: Path | None = None, request_limit: int | None = None,
        record_only: bool = False,
    ) -> None:
        if request_limit is not None and (type(request_limit) is not int or request_limit < 0):
            raise ValueError("Request limit must be a non-negative integer")
        self.record_only = record_only
        self._request_limit = request_limit
        self._limit = limit
        self._trials: dict[str, SpendLimit] = {}
        self._requests: dict[str, _Reservation] = {}
        self._active: str | None = None
        self._stop_reason: str | None = None
        self._journal: TextIO | None = None
        self._closed = False
        if journal is not None:
            self._journal = journal.open("x", encoding="utf-8")
            try:
                self._persist()
                directory = os.open(journal.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except BaseException:
                self._journal.close()
                self._closed = True
                raise

    def _persist(self) -> None:
        if self._journal is None:
            return
        try:
            self._journal.write(json.dumps(self.snapshot(), ensure_ascii=False) + "\n")
            self._journal.flush()
            os.fsync(self._journal.fileno())
        except OSError as exc:
            self._stop_reason = self._stop_reason or "persistence_error"
            raise SpendLimitExceeded("persistence_error") from exc

    def close(self) -> None:
        """Retain unfinished reservations; existing journals are never resumed."""
        if self._closed:
            return
        try:
            self.finish_trial()
        finally:
            self._closed = True
            if self._journal is not None:
                self._journal.close()

    def _check_running(self) -> None:
        if self._closed:
            raise SpendLimitExceeded("ledger_closed")
        if self._stop_reason is not None:
            raise SpendLimitExceeded(self._stop_reason)

    def stop(self, reason: str) -> None:
        """Latch an external contract failure without releasing pending reservations."""
        if self._closed:
            raise SpendLimitExceeded("ledger_closed")
        self._stop_reason = self._stop_reason or reason
        self._persist()

    def start_trial(self, trial: str, limit: SpendLimit) -> None:
        self._check_running()
        if self._active is not None or trial in self._trials:
            raise ValueError("Trials must be serial and have unique IDs")
        self._trials[trial] = limit
        self._active = trial
        self._persist()

    def reserve(self, request_id: str, allowance: TokenAllowance) -> None:
        self._check_running()
        if self._active is None:
            raise ValueError("No active trial")
        if request_id in self._requests or any(
            r.status == "pending" for r in self._requests.values()
        ):
            raise ValueError("Requests must be serial and have unique IDs")
        if self._request_limit is not None and len(self._requests) >= self._request_limit:
            self.stop("batch_requests")
            raise SpendLimitExceeded("batch_requests")
        if self.record_only:
            allowance = TokenAllowance(0, 0, 0, 0)
        added_tokens = allowance.input_tokens + allowance.output_tokens
        added_cost = (
            allowance.input_tokens * allowance.input_nano_usd
            + allowance.output_tokens * allowance.output_nano_usd
        )
        for scope, totals in (
            ("trial", self._totals(self._trials[self._active], self._active)),
            ("batch", self._totals(self._limit)),
        ):
            for dimension, added in (("tokens", added_tokens), ("nano_usd", added_cost)):
                if not self.record_only and (
                    totals[f"charged_{dimension}"] + added > totals[f"limit_{dimension}"]
                ):
                    self._stop_reason = f"{scope}_{dimension}"
                    self._persist()
                    raise SpendLimitExceeded(self._stop_reason)
        self._requests[request_id] = _Reservation(self._active, allowance)
        self._persist()

    def settle(
        self, request_id: str, *, input_tokens: int | None, output_tokens: int | None
    ) -> None:
        if self._closed:
            raise SpendLimitExceeded("ledger_closed")
        request = self._requests[request_id]
        if request.status != "pending":
            raise ValueError("Request already settled")
        invalid = any(
            n is not None and (type(n) is not int or n < 0) for n in (input_tokens, output_tokens)
        )
        input_tokens = input_tokens if type(input_tokens) is int and input_tokens >= 0 else None
        output_tokens = output_tokens if type(output_tokens) is int and output_tokens >= 0 else None
        request.input_tokens = input_tokens
        request.output_tokens = output_tokens
        exceeded = not self.record_only and (
            (input_tokens is not None and input_tokens > request.allowance.input_tokens) or
            (output_tokens is not None and output_tokens > request.allowance.output_tokens)
        )
        if input_tokens is None or output_tokens is None:
            request.status = "unknown"
            self._stop_reason = self._stop_reason or (
                "bound_exceeded" if exceeded else "invalid_usage" if invalid else "unknown_usage"
            )
        elif exceeded:
            request.status = "bound_exceeded"
            self._stop_reason = self._stop_reason or "bound_exceeded"
        else:
            request.status = "known"
        self._persist()

    def finish_trial(self) -> None:
        if self._closed:
            raise SpendLimitExceeded("ledger_closed")
        for request_id, request in self._requests.items():
            if request.trial == self._active and request.status == "pending":
                self.settle(request_id, input_tokens=None, output_tokens=None)
        self._active = None
        self._persist()

    def _totals(self, limit: SpendLimit, trial: str | None = None) -> dict[str, int]:
        tokens = cost = known_tokens = known_cost = 0
        for request in self._requests.values():
            if trial is not None and request.trial != trial:
                continue
            allowance = request.allowance
            inputs = (
                request.input_tokens if request.input_tokens is not None else allowance.input_tokens
            )
            outputs = (
                request.output_tokens
                if request.output_tokens is not None
                else allowance.output_tokens
            )
            known = request.status in ("known", "bound_exceeded")
            if not known:
                inputs = max(inputs, allowance.input_tokens)
                outputs = max(outputs, allowance.output_tokens)
            tokens += inputs + outputs
            request_cost = inputs * allowance.input_nano_usd + outputs * allowance.output_nano_usd
            cost += request_cost
            if known:
                known_tokens += inputs + outputs
                known_cost += request_cost
        return {
            "limit_tokens": limit.tokens,
            "limit_nano_usd": limit.nano_usd,
            "charged_tokens": tokens,
            "charged_nano_usd": cost,
            "known_tokens": known_tokens,
            "known_nano_usd": known_cost,
            "reserved_tokens": tokens - known_tokens,
            "reserved_nano_usd": cost - known_cost,
        }

    def snapshot(self) -> SpendSnapshot:
        batch = self._totals(self._limit)
        if self._request_limit is not None:
            batch.update(limit_requests=self._request_limit, admitted_requests=len(self._requests))
        return {
            "record_only": self.record_only,
            "cost_status": "unpriced" if self.record_only else "contract_estimate",
            "batch": batch,
            "trials": {trial: self._totals(limit, trial) for trial, limit in self._trials.items()},
            "stop_reason": self._stop_reason,
            "requests": {key: asdict(value) for key, value in self._requests.items()},
        }
