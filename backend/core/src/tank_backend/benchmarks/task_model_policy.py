"""Experiment-owned limits and wire capture for governed task clients."""

from __future__ import annotations

import json
from typing import Literal

import httpx

from ..tools.computer_grounding import grounding_call_id
from .model_policy import BenchmarkModelPolicy
from .request_budget import RequestBudget, RequestLimitExceeded
from .spend_http import SpendControl
from .trace import TraceSink


class BenchmarkTaskPolicy:
    def __init__(
        self, trace: TraceSink, budget: RequestBudget | None, spend: SpendControl | None,
    ) -> None:
        self.trace, self.budget = trace, budget
        self.spend = BenchmarkModelPolicy(spend.ledger, spend.contracts) if spend else None
        self.active = True
        self._roles: dict[str, Literal["planner", "locator"]] = {}

    def check(self) -> None:
        if not self.active or self.trace.closed:
            raise RequestLimitExceeded("request outside active trial")
        if self.budget is not None and (not self.budget.active or self.budget.blocked):
            raise RequestLimitExceeded("request budget already stopped")
        if self.spend is not None:
            self.spend.check()

    def reserve(self, call_id: str, request: httpx.Request) -> None:
        self.check()
        role = "locator" if grounding_call_id.get() else "planner"
        if self.budget is not None:
            self.budget.reserve(role)
        try:
            if self.spend is not None:
                self.spend.reserve(call_id, request)
        except BaseException:
            if self.budget is not None:
                setattr(self.budget, role, getattr(self.budget, role) - 1)
            raise
        self._roles[call_id] = role

    def settle(self, call_id: str, inputs: int | None, outputs: int | None) -> None:
        try:
            if self.spend is not None:
                self.spend.settle(call_id, inputs, outputs)
        finally:
            self._roles.pop(call_id, None)

    def release_unsent(self, call_id: str) -> None:
        role = self._roles.pop(call_id, None)
        if role is None:
            return
        if self.spend is not None:
            self.spend.release_unsent(call_id)
        if self.budget is not None:
            setattr(self.budget, role, getattr(self.budget, role) - 1)

    async def request(self, call_id: str, request: httpx.Request) -> None:
        self.check()
        await self.trace.capture_request(request, request_id=call_id)

    async def response(self, call_id: str, response: httpx.Response) -> None:
        self.check()
        authorization = response.request.headers.get("authorization", "")
        key = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
        redactions = tuple({key.encode(), json.dumps(key)[1:-1].encode()}) if key else ()
        await self.trace.capture_response(response, redactions=redactions)
