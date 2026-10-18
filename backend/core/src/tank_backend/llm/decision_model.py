"""Standalone core decision model: an SDK adapter, with no task or HTTP middleware."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import TypeVar, cast

from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    Image,
    JSONContent,
    Question,
    RetryPolicy,
    SystemOneResponse,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
)

from ..observability.model_observation import model_observation
from .decision_profile import DecisionModelProfile
from .model_data import ModelImageAsset

T = TypeVar("T")


def decision_usage(response: SystemOneResponse) -> tuple[int | None, int | None]:
    inputs, outputs = response.usage.input_tokens, response.usage.output_tokens
    if type(inputs) is int and inputs >= 0 and type(outputs) is int and outputs >= 0:
        return inputs, outputs
    return None, None


@dataclass(frozen=True)
class ChoiceResult:
    choice: str
    confidence: float
    probabilities: dict[str, float]
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class BoxResult:
    """Uncalibrated evidence only; it carries no executable action or task completion."""

    cardinality: ChoiceResult
    box: tuple[float, float, float, float]
    confidence: float | None
    input_tokens: int | None = None
    output_tokens: int | None = None


class DecisionModelError(RuntimeError):
    def __init__(
        self,
        reason: str,
        inputs: int | None = None,
        outputs: int | None = None,
        *,
        source: Exception | None = None,
    ):
        super().__init__(reason)
        self.input_tokens, self.output_tokens = inputs, outputs
        # Do not retain SDK bodies, headers, exception messages or credentials.
        cause = source.__cause__ if source is not None else None
        self.diagnostics: dict[str, str | int | None] = {
            "error_type": type(source).__name__ if source is not None else type(self).__name__,
            "http_status": source.status if isinstance(source, TypeSafeAPIError) else None,
            "cause_type": type(cause).__name__ if cause is not None else None,
        }


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
        json.dumps([state, options], allow_nan=False)
        question = Choice(
            instructions=instructions,
            criteria={k: cast(JSONContent, v) for k, v in options.items()},
        )
        return await self._complete(
            state,
            {"next_action": question},
            lambda response: self._choice(response, "next_action", options),
        )

    async def choose_image(
        self,
        *,
        state: dict[str, object],
        image: ModelImageAsset,
        instructions: str,
        options: dict[str, object],
    ) -> ChoiceResult:
        from .decision_image import image_choice_questions, image_request

        options = deepcopy(options)
        request = image_request(
            self.profile, state, image, image_choice_questions(instructions, options)
        )
        return await self._complete(
            request.parameters["state"],
            cast(dict[str, Question], request.parameters["questions"]),
            lambda response: self._choice(response, "next_action", options),
            image=image,
        )

    async def locate_image(
        self,
        *,
        state: dict[str, object],
        image: ModelImageAsset,
        target: str,
    ) -> BoxResult:
        from .decision_image import CARDINALITY, box_questions, image_request

        if self.profile.model != "jev-1.14.0":
            raise ValueError("Box requires the explicitly supported Jev 1.14 version")
        questions = box_questions(target)
        request = image_request(self.profile, state, image, questions)

        def decode(response: SystemOneResponse) -> BoxResult:
            cardinality = self._choice(response, "cardinality", dict(CARDINALITY))
            # These are two answers to one call; usage belongs only to BoxResult.
            cardinality = ChoiceResult(cardinality.choice, cardinality.confidence,
                                       cardinality.probabilities)
            answer = response.boxes.get("target")
            if answer is None:
                raise ValueError("missing box")
            box = (answer.box.left, answer.box.top, answer.box.right, answer.box.bottom)
            if (
                not all(math.isfinite(edge) and 0 <= edge <= 1 for edge in box)
                or not box[0] < box[2]
                or not box[1] < box[3]
                or answer.confidence is not None
                and (not math.isfinite(answer.confidence) or not 0 <= answer.confidence <= 1)
            ):
                raise ValueError("invalid box")
            return BoxResult(cardinality, box, answer.confidence, *decision_usage(response))

        return await self._complete(
            request.parameters["state"], cast(dict[str, Question], questions), decode, image=image
        )

    @staticmethod
    def _choice(response: SystemOneResponse, key: str, options: dict[str, object]) -> ChoiceResult:
        answer = response.choices.get(key)
        if (
            answer is None
            or answer.choice not in options
            or set(answer.probabilities) != set(options)
            or not math.isfinite(answer.confidence)
            or not 0 <= answer.confidence <= 1
            or not all(math.isfinite(v) and 0 <= v <= 1 for v in answer.probabilities.values())
            or not math.isclose(sum(answer.probabilities.values()), 1.0, abs_tol=0.02)
            or answer.probabilities[answer.choice] != max(answer.probabilities.values())
        ):
            raise ValueError("invalid choice")
        return ChoiceResult(
            answer.choice, answer.confidence, dict(answer.probabilities), *decision_usage(response)
        )

    async def _complete(
        self,
        state: dict[str, object],
        questions: dict[str, Question],
        decode: Callable[[SystemOneResponse], T],
        *,
        image: ModelImageAsset | None = None,
    ) -> T:
        if self._closed:
            raise DecisionModelError("model_closed")
        if self._client is None:
            self._client = AsyncTypeSafeClient(
                api_key=self._credential,
                model=self.profile.model,
                base_url=self.profile.url.removesuffix("/v1/systemone"),
                timeout=30,
                retry=RetryPolicy(max_retries=0),
                compression=False,
            )
        inputs = outputs = None
        with model_observation("decision.choose", self.profile.model) as observation:
            try:
                response = await self._client.system_one(
                    state=cast(JSONContent, state),
                    questions=questions,
                    assets={image.reference: Image(image.data)} if image is not None else None,
                    extra_headers={"TypeSafe-Danger-Zone-Images": "true"}
                    if image is not None
                    else None,
                )
                inputs, outputs = decision_usage(response)
                if response.model != self.profile.model or set(response.answers) != set(questions):
                    raise ValueError("unexpected model or answers")
                result = decode(response)
                if isinstance(result, ChoiceResult):
                    observation(choice=result.choice, confidence=result.confidence,
                                probabilities=result.probabilities,
                                candidates=len(result.probabilities),
                                input_tokens=inputs, output_tokens=outputs)
                elif isinstance(result, BoxResult):
                    observation(cardinality=result.cardinality.choice,
                                cardinality_confidence=result.cardinality.confidence,
                                cardinality_probabilities=result.cardinality.probabilities,
                                box=result.box, box_confidence=result.confidence,
                                input_tokens=inputs, output_tokens=outputs)
                else:
                    observation(input_tokens=inputs, output_tokens=outputs)
                return result
            except ValueError:
                observation(error="invalid_decision", input_tokens=inputs, output_tokens=outputs)
                raise DecisionModelError("invalid_decision", inputs, outputs) from None
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
                    source=exc,
                ) from None
            except Exception as exc:
                observation(error=type(exc).__name__)
                raise DecisionModelError("model_error", inputs, outputs, source=exc) from None

    async def aclose(self) -> None:
        self._closed = True
        self._credential = ""
        if self._client is not None:
            await self._client.aclose()
