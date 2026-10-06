"""Standalone core decision model: an SDK adapter, with no task or HTTP middleware."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import httpx2
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    JSONContent,
    RetryPolicy,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
)

from ..observability.model_observation import model_observation
from .decision_profile import DecisionModelProfile


@dataclass(frozen=True)
class ChoiceResult:
    choice: str
    confidence: float
    probabilities: dict[str, float]
    input_tokens: int | None = None
    output_tokens: int | None = None


class DecisionModelError(RuntimeError):
    def __init__(self, reason: str, inputs: int | None = None, outputs: int | None = None):
        super().__init__(reason)
        self.input_tokens, self.output_tokens = inputs, outputs


class DecisionModel:
    """Own a lazy SDK client. Callers only supply state, instructions and options."""

    def __init__(self, profile: DecisionModelProfile, *, credential: str):
        if not credential.strip():
            raise ValueError("Decision model credential is missing")
        self.profile = profile
        self._credential = credential
        self._client: AsyncTypeSafeClient | None = None
        self._closed = False

    async def choose(
        self, *, state: dict[str, object], instructions: str, options: dict[str, object]
    ) -> ChoiceResult:
        if self._closed:
            raise DecisionModelError("model_closed")
        if (
            not isinstance(state, dict)
            or not isinstance(instructions, str)
            or not isinstance(options, dict)
            or not 1 <= len(options) <= 255
            or any(not isinstance(k, str) or not k.strip() or len(k) > 128 for k in options)
            or any(not isinstance(v, (str, dict)) for v in options.values())
        ):
            raise ValueError("Choice requires bounded named options and structured state")
        options = dict(options)
        question = Choice(
            instructions=instructions,
            criteria={k: cast(JSONContent, v) for k, v in options.items()},
        )
        if self._client is None:
            self._client = AsyncTypeSafeClient(
                api_key=self._credential,
                model=self.profile.model,
                base_url=self.profile.url.removesuffix("/v1/systemone"),
                retry=RetryPolicy(max_retries=0),
                http_client=httpx2.AsyncClient(
                    transport=httpx2.AsyncHTTPTransport(),
                    timeout=30,
                    follow_redirects=False,
                    trust_env=False,
                ),
            )
        inputs = outputs = None
        with model_observation("decision.choose", self.profile.model) as observation:
            try:
                response = await self._client.system_one(
                    state=cast(JSONContent, state), questions={"next_action": question}
                )
                inputs, outputs = response.usage.input_tokens, response.usage.output_tokens
                if not (
                    type(inputs) is int and inputs >= 0 and type(outputs) is int and outputs >= 0
                ):
                    inputs = outputs = None
                answer = response.choices.get("next_action")
                if (
                    response.model != self.profile.model
                    or set(response.answers) != {"next_action"}
                    or answer is None
                    or answer.choice not in options
                    or set(answer.probabilities) != set(options)
                    or not math.isfinite(answer.confidence)
                    or not 0 <= answer.confidence <= 1
                    or not all(
                        math.isfinite(v) and 0 <= v <= 1 for v in answer.probabilities.values()
                    )
                    or not math.isclose(sum(answer.probabilities.values()), 1.0, abs_tol=0.02)
                    or answer.probabilities[answer.choice] != max(answer.probabilities.values())
                ):
                    raise DecisionModelError("invalid_decision", inputs, outputs)
                observation(choice=answer.choice, input_tokens=inputs, output_tokens=outputs)
                return ChoiceResult(
                    answer.choice, answer.confidence, dict(answer.probabilities), inputs, outputs
                )
            except DecisionModelError as exc:
                observation(
                    error=str(exc), input_tokens=exc.input_tokens, output_tokens=exc.output_tokens
                )
                raise
            except TypeSafeAPIError as exc:
                usage = (
                    exc.body.get("usage")
                    if isinstance(exc, TypeSafeAPIResponseValidationError)
                    and isinstance(exc.body, dict)
                    else None
                )
                if isinstance(usage, dict):
                    i, o = usage.get("input_tokens"), usage.get("output_tokens")
                    if type(i) is int and i >= 0 and type(o) is int and o >= 0:
                        inputs, outputs = i, o
                observation(error=type(exc).__name__, input_tokens=inputs, output_tokens=outputs)
                raise DecisionModelError(
                    "invalid_decision"
                    if isinstance(exc, TypeSafeAPIResponseValidationError)
                    else "model_error",
                    inputs,
                    outputs,
                ) from None
            except Exception as exc:
                observation(error=type(exc).__name__)
                raise DecisionModelError("model_error", inputs, outputs) from None

    async def aclose(self) -> None:
        self._closed = True
        self._credential = ""
        if self._client is not None:
            await self._client.aclose()
