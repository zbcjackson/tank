"""Explicit experiment policy for the production model transport's narrow hooks."""

from __future__ import annotations

import httpx

from ..llm.model_transport import json_object
from .spend_http import ContextWindowContract
from .spend_ledger import SpendLedger, SpendLimitExceeded, TokenAllowance


class BenchmarkModelPolicy:
    """The experiment owns trial/batch lifetime; a task cannot close the batch."""

    def __init__(
        self, ledger: SpendLedger, contracts: tuple[ContextWindowContract, ...],
    ) -> None:
        self.ledger = ledger
        self._contracts = contracts

    def check(self) -> None:
        reason = self.ledger.snapshot()["stop_reason"]
        if reason is not None:
            raise SpendLimitExceeded(reason)

    def reserve(self, call_id: str, request: httpx.Request) -> None:
        data = json_object(request.content)
        if self.ledger.record_only:
            self.ledger.reserve(call_id, TokenAllowance(0, 0, 0, 0))
            return
        maximum = data.get("max_tokens", data.get("max_completion_tokens"))
        contract = next((item for item in self._contracts if (
            item.url == str(request.url) and item.model == data.get("model")
        )), None)
        if (
            contract is None or request.method != "POST"
            or (maximum is None and contract.output_cap_required)
            or (maximum is not None and (
                type(maximum) is not int or not 0 < maximum <= contract.allowance.output_tokens
            ))
        ):
            self.ledger.stop("request_contract")
            raise SpendLimitExceeded("request_contract")
        self.ledger.reserve(call_id, contract.allowance)

    def settle(self, call_id: str, inputs: int | None, outputs: int | None) -> None:
        self.ledger.settle(call_id, input_tokens=inputs, output_tokens=outputs)

    def release_unsent(self, call_id: str) -> None:
        self.ledger.release_unsent(call_id)
