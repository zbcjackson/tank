"""Opt-in HTTP spend gate using externally reviewed provider context ceilings."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import NoReturn

import httpx

from .spend_ledger import SpendLedger, SpendLimit, SpendLimitExceeded, TokenAllowance
from .trace import TraceSink


def _json_object(data: str | bytes) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    result = json.loads(data, object_pairs_hook=unique)
    if not isinstance(result, dict):
        raise ValueError("JSON object required")
    return result


@dataclass(frozen=True)
class ContextWindowContract:
    url: str
    model: str
    allowance: TokenAllowance
    evidence: str

    def __post_init__(self) -> None:
        url = httpx.URL(self.url)
        if (
            not self.evidence.strip()
            or not self.model.strip()
            or url.scheme != "https"
            or not url.host
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Context contract requires evidence, model and uncredentialed HTTPS URL"
            )


@dataclass
class SpendSession:
    control: SpendControl
    trace: TraceSink
    active: bool = True
    pending: str | None = None
    body: bytearray = field(default_factory=bytearray)
    streaming: bool = False
    response_ok: bool = False

    def block(self, reason: str) -> NoReturn:
        self.control.ledger.stop(reason)
        self.trace.event("spend_blocked", reason=reason)
        raise SpendLimitExceeded(reason)

    def reserve(self, request: httpx.Request) -> str:
        if not self.active or self.control.active is not self:
            raise SpendLimitExceeded("request outside active spend trial")
        try:
            body = _json_object(request.content)
        except ValueError:
            self.block("request_contract")
        contract = next(
            (
                c
                for c in self.control.contracts
                if c.url == str(request.url) and c.model == body.get("model")
            ),
            None,
        )
        allowed = {
            "model",
            "messages",
            "tools",
            "tool_choice",
            "max_tokens",
            "stream",
            "stream_options",
            "temperature",
            "enable_thinking",
        }
        maximum = body.get("max_tokens")
        if (
            contract is None
            or request.method != "POST"
            or set(body) - allowed
            or body.get("enable_thinking") is not False
            or type(body.get("stream")) is not bool
            or type(maximum) is not int
            or not 0 < maximum <= contract.allowance.output_tokens
            or (body["stream"] and body.get("stream_options") != {"include_usage": True})
        ):
            self.block("request_contract")
        request_id = uuid.uuid4().hex
        self.control.ledger.reserve(request_id, contract.allowance)
        self.pending = request_id
        self.body.clear()
        self.streaming = body["stream"] is True
        self.response_ok = False
        request.headers["Accept-Encoding"] = "identity"
        request.extensions["tank_spend"] = (self, request_id)
        self.trace.event(
            "spend_reserved",
            request_id=request_id,
            contract=asdict(contract),
            request_sha256=hashlib.sha256(request.content).hexdigest(),
        )
        return request_id

    async def capture_response(self, response: httpx.Response) -> None:
        if (
            not self.active
            or self.control.active is not self
            or response.request.extensions.get("tank_spend") != (self, self.pending)
        ):
            raise SpendLimitExceeded("response outside active spend request")
        self.response_ok = (
            response.is_success
            and response.headers.get("content-encoding", "identity") == "identity"
        )
        if response.is_stream_consumed:
            self.body.extend(response.content)
        else:
            if not isinstance(response.stream, httpx.AsyncByteStream):
                self.block("response_stream_contract")
            response.stream = _SpendStream(response.stream, self, self.pending)

    def settle(self, usage: object) -> None:
        if not self.active or self.pending is None:
            raise SpendLimitExceeded("usage outside active spend request")
        request_id = self.pending
        inputs = outputs = None
        try:
            if not self.response_ok or usage is None or len(self.body) > 2_000_000:
                raise ValueError("incomplete response usage")
            text = self.body.decode("utf-8")
            if self.streaming:
                events = text.replace("\r\n", "\n").split("\n\n")
                values = [
                    "\n".join(
                        line[5:].lstrip(" ")
                        for line in event.split("\n")
                        if line.startswith("data:")
                    )
                    for event in events
                ]
                if "[DONE]" not in values:
                    raise ValueError("unfinished SSE")
                records = [_json_object(value) for value in values if value and value != "[DONE]"]
                usages = [r["usage"] for r in records if isinstance(r, dict) and r.get("usage")]
                if len(usages) != 1:
                    raise ValueError("missing or repeated usage")
                raw = usages[0]
            else:
                raw = _json_object(text).get("usage")
            if not isinstance(raw, dict):
                raise ValueError("missing usage")
            counts: list[int] = []
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = raw.get(key)
                if type(value) is not int or value < 0:
                    raise ValueError("invalid usage")
                counts.append(value)
            if counts[0] + counts[1] != counts[2]:
                raise ValueError("invalid usage")
            inputs, outputs = counts[:2]
        except (ValueError, TypeError, AttributeError):
            pass
        self.control.ledger.settle(request_id, input_tokens=inputs, output_tokens=outputs)
        self.pending = None
        snapshot = self.control.ledger.snapshot()
        self.trace.event(
            "spend_settled", request_id=request_id, record=snapshot["requests"][request_id]
        )
        if snapshot["stop_reason"]:
            raise SpendLimitExceeded(snapshot["stop_reason"])


class SpendControl:
    """Share one ledger across serial driver trials; never supplies live defaults."""

    def __init__(
        self,
        ledger: SpendLedger,
        trial_limit: SpendLimit,
        contracts: tuple[ContextWindowContract, ...],
    ) -> None:
        self.ledger, self.trial_limit, self.contracts = ledger, trial_limit, contracts
        self.active: SpendSession | None = None

    def start(self, trace: TraceSink) -> SpendSession:
        self.ledger.start_trial(str(trace.trial_dir.resolve()), self.trial_limit)
        self.active = SpendSession(self, trace)
        return self.active

    def finish(self, session: SpendSession) -> None:
        if self.active is not session or not session.active:
            raise ValueError("spend trial already closed or owned by another control")
        self.ledger.finish_trial()
        session.active = False
        self.active = None
        session.trace.event("spend_budget", **self.ledger.snapshot())


class _SpendStream(httpx.AsyncByteStream):
    def __init__(
        self, inner: httpx.AsyncByteStream, session: SpendSession, request_id: str | None
    ) -> None:
        self.inner, self.session, self.request_id = inner, session, request_id

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.inner:
            if self.session.active and self.session.pending == self.request_id:
                self.session.body.extend(chunk)
                if len(self.session.body) > 2_000_000:
                    raise SpendLimitExceeded("response evidence too large")
            yield chunk

    async def aclose(self) -> None:
        await self.inner.aclose()


active_spend_session: ContextVar[SpendSession | None] = ContextVar("spend_session", default=None)
