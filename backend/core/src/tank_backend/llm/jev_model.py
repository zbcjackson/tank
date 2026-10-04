"""Core-owned TypeSafe SDK adapter; UI semantics remain with the caller."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

import httpx
import httpx2
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    JSONContent,
    RetryPolicy,
    TypeSafeAPIResponseValidationError,
)

from ..agents.subagent import SubAgentContext, SubAgentStopped
from .decision_profile import DecisionModelProfile, validate_version
from .model_transport import TaskModelTransport, json_object


@dataclass(frozen=True)
class ChoiceResult:
    choice: str
    confidence: float
    probabilities: dict[str, float]


@dataclass(frozen=True)
class JevChoiceRoute:
    url: str
    model: str
    credential_ref: str
    max_upload_bytes: int = 65536

    def __post_init__(self) -> None:
        validate_version(self.model)
        url = httpx.URL(self.url)
        if (url.scheme != "https" or not url.host or url.userinfo or url.query or url.fragment
                or not self.credential_ref or type(self.max_upload_bytes) is not int
                or not 0 < self.max_upload_bytes <= 65536):
            raise ValueError("Jev requires an exact HTTPS endpoint and bounded upload")

    @property
    def operation(self) -> str:
        return "jev_choice"

    def is_streaming(self, request: httpx.Request) -> bool:
        return False

    def validate(self, request: httpx.Request) -> None:
        if request.method != "POST" or len(request.content) > self.max_upload_bytes:
            raise ValueError("Jev request exceeds approved bounds")
        data = json_object(request.content)
        if set(data) != {"model", "state", "questions"} or data["model"] != self.model:
            raise ValueError("Jev request outside approved protocol")
        if not isinstance(data["state"], dict):
            raise ValueError("Jev decision state must be an object")
        questions = data["questions"]
        if not isinstance(questions, dict) or len(questions) != 1:
            raise ValueError("Jev requires one choice question")
        question = next(iter(questions.values()))
        if (not isinstance(question, dict)
                or set(question) != {"type", "instructions", "criteria"}
                or question["type"] != "choice"
                or not isinstance(question["instructions"], str)):
            raise ValueError("Jev requires a Choice question")
        criteria = question["criteria"]
        if (not isinstance(criteria, dict) or not 1 <= len(criteria) <= 255
                or any(not isinstance(key, str) or not key.strip() or len(key) > 128
                       for key in criteria)
                or any(not isinstance(value, (str, dict)) for value in criteria.values())):
            raise ValueError("Jev requires bounded criteria")

    def read_usage(self, response: httpx.Response) -> tuple[int, int]:
        if not response.is_success:
            raise ValueError("Jev response was not successful")
        usage = json_object(response.content).get("usage")
        if not isinstance(usage, dict):
            raise ValueError("Jev usage is unknown")
        inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
        if type(inputs) is not int or type(outputs) is not int or inputs < 0 or outputs < 0:
            raise ValueError("Jev usage is invalid")
        return inputs, outputs


class _SDKTransport(httpx2.AsyncBaseTransport):
    """Bridge the SDK's httpx2 wire objects to Tank's existing governed transport."""

    def __init__(self, transport: TaskModelTransport) -> None:
        self.transport = transport

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        governed = httpx.Request(request.method, str(request.url), headers=request.headers.raw,
                                content=await request.aread(), extensions=request.extensions)
        response = await self.transport.handle_async_request(governed)
        try:
            content = await response.aread()
            headers = [(k, v) for k, v in response.headers.raw
                       if k.lower() not in (b"content-encoding", b"content-length")]
            return httpx2.Response(response.status_code, headers=headers, content=content)
        finally:
            await response.aclose()

    async def aclose(self) -> None:
        await self.transport.aclose()

class TaskDecisionModel:
    """Borrowed choice capability. Only core configures, authenticates and closes it."""

    def __init__(self, task_id: str, context: SubAgentContext,
                 profile: DecisionModelProfile, credential: str) -> None:
        context.check("network")
        if not credential.strip():
            raise ValueError("Decision model credential is missing")
        self._route = JevChoiceRoute(profile.url, profile.model, profile.credential_env)
        self._task_id, self._context = task_id, context
        self._credential = credential
        self._client: AsyncTypeSafeClient | None = None
        self._closed = False

    async def choose(self, *, state: dict[str, object], instructions: str,
                     options: dict[str, object]) -> ChoiceResult:
        self._context.check("network")
        if self._closed:
            raise SubAgentStopped("model_closed")
        # Validate the bounded public input before allocating SDK/HTTP resources.
        if (not isinstance(state, dict) or not isinstance(instructions, str)
                or not isinstance(options, dict) or not 1 <= len(options) <= 255
                or any(not isinstance(k, str) or not k.strip() or len(k) > 128 for k in options)
                or any(not isinstance(v, (str, dict)) for v in options.values())):
            raise ValueError("Choice requires bounded named options and structured state")
        question = Choice(instructions=instructions,
                          criteria={k: cast(JSONContent, v) for k, v in options.items()})
        if self._client is None:
            transport = TaskModelTransport(
                self._task_id, self._context, routes=(self._route,),
                credentials={self._route.credential_ref: self._credential},
                inner=httpx.AsyncHTTPTransport(),
            )
            http = httpx2.AsyncClient(transport=_SDKTransport(transport), timeout=30,
                                     follow_redirects=False, trust_env=False)
            try:
                self._client = AsyncTypeSafeClient(
                    api_key="host-managed", model=self._route.model,
                    base_url=self._route.url.removesuffix("/v1/systemone"),
                    retry=RetryPolicy(max_retries=0), http_client=http,
                )
            except BaseException:
                await http.aclose()
                raise
        try:
            response = await self._client.system_one(
                state=cast(JSONContent, state), questions={"next_action": question},
            )
            self._context.check("network")
            # SDK validates wire types; Tank additionally binds the answer to this request.
            raw = json_object(response.raw_http_response.content)
            answers = raw.get("answers")
            if (response.model != self._route.model or not isinstance(answers, dict)
                    or set(answers) != {"next_action"}):
                raise SubAgentStopped("invalid_decision")
            answer = response.choices.get("next_action")
            if (answer is None or answer.choice not in options
                    or set(answer.probabilities) != set(options)
                    or not math.isfinite(answer.confidence) or not 0 <= answer.confidence <= 1
                    or not all(math.isfinite(v) and 0 <= v <= 1
                               for v in answer.probabilities.values())
                    or not math.isclose(sum(answer.probabilities.values()), 1.0, abs_tol=0.02)
                    or answer.probabilities[answer.choice] != max(answer.probabilities.values())):
                raise SubAgentStopped("invalid_decision")
            return ChoiceResult(answer.choice, answer.confidence, dict(answer.probabilities))
        except SubAgentStopped:
            raise
        except TypeSafeAPIResponseValidationError:
            self._context.check("network")
            raise SubAgentStopped("invalid_decision") from None
        except Exception:
            self._context.check("network")
            raise SubAgentStopped("model_error", "Decision model request failed") from None

    async def aclose(self) -> None:
        self._closed = True
        self._credential = ""
        if self._client is not None:
            await self._client.aclose()
