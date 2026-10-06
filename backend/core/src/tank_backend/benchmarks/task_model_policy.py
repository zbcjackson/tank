"""Experiment-owned limits and wire capture for governed task clients."""

from __future__ import annotations

import json
from typing import Literal

from ..llm.model_data import ModelRequest
from ..tools.computer_grounding import grounding_call_id
from .model_policy import BenchmarkModelPolicy
from .request_budget import RequestBudget, RequestLimitExceeded
from .spend_http import SpendControl
from .trace import TraceSink, image_hashes


class BenchmarkTaskPolicy:
    def __init__(
        self, trace: TraceSink, budget: RequestBudget | None, spend: SpendControl | None,
        *, secrets: tuple[str, ...] = (),
    ) -> None:
        self.trace, self.budget = trace, budget
        self.secrets = secrets
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

    def reserve(self, call_id: str, request: ModelRequest) -> None:
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

    async def request(self, call_id: str, request: ModelRequest) -> None:
        self.check()
        self.trace.event("sdk_request", request_id=call_id, model=request.model,
                         stream=bool(request.parameters.get("stream")),
                         image_sha256=image_hashes(request.parameters),
                         grounding_call_id=grounding_call_id.get())

    async def response(self, call_id: str, response: dict[str, object]) -> None:
        self.check()
        self.trace.event("sdk_response", request_id=call_id, result=self._redact(response))

    def _redact(self, value: object) -> object:
        text = json.dumps(value, ensure_ascii=False)
        for secret in self.secrets:
            if secret:
                text = text.replace(json.dumps(secret, ensure_ascii=False)[1:-1], "[REDACTED]")
        return json.loads(text)
