"""Host-owned, text-only model service for a single task."""

from __future__ import annotations

import math
from collections.abc import Iterable

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from ..agents.subagent import SubAgentContext, SubAgentStopped
from .llm import LLM
from .model_data import chat_data_types
from .profile import LLMProfile


class TaskModel:
    """Plugins borrow complete(); only the host configures and closes the client."""

    _data_types = frozenset({"text"})

    def __init__(
        self, task_id: str, context: SubAgentContext, profile: LLMProfile,
    ) -> None:
        context.check("network")
        if (
            profile.extra_headers or (profile.extra_body and not (
                set(profile.extra_body) == {"enable_thinking"}
                and profile.extra_body["enable_thinking"] is False
            ))
            or not isinstance(profile.api_key, str) or not profile.api_key.strip()
            or (profile.temperature is not None and (
                isinstance(profile.temperature, bool)
                or not math.isfinite(profile.temperature) or not 0 <= profile.temperature <= 2
            ))
        ):
            raise ValueError("profile is incompatible with the task text model service")
        self._extra_body: dict[str, object] = (
            {"enable_thinking": False} if profile.extra_body else {}
        )
        url = httpx.URL(profile.base_url)
        if (url.scheme != "https" or not url.host or url.userinfo or url.query or url.fragment
                or type(profile.max_tokens) is not int or profile.max_tokens <= 0):
            raise ValueError("Text model requires HTTPS and a positive output limit")
        self._profile = profile
        self._context = context
        self._task_id = task_id
        self._credential = profile.api_key
        self._temperature = profile.temperature
        self._client: AsyncOpenAI | None = None
        self._llm: LLM | None = None
        self._closed = False

    async def complete(self, messages: Iterable[ChatCompletionMessageParam]) -> str:
        """One text completion, accounted at the SDK call before returning any result."""
        self._context.check("network")
        if self._closed:
            raise SubAgentStopped("model_closed")
        messages = list(messages)
        try:
            if not chat_data_types(messages) <= self._data_types:
                raise ValueError("unsupported service data")
        except ValueError:
            raise SubAgentStopped("model_data_denied") from None
        if self._llm is None:
            profile = self._profile
            http = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(),
                                     follow_redirects=False, trust_env=False)
            try:
                self._client = AsyncOpenAI(api_key=self._credential, base_url=profile.base_url,
                                           max_retries=0, http_client=http)
                self._llm = LLM(api_key=self._credential, model=profile.model,
                                base_url=profile.base_url, temperature=self._temperature,
                                max_tokens=profile.max_tokens, client=self._client,
                                extra_body=self._extra_body.copy()).bind_task(
                                    self._context, self._task_id)
            except BaseException:
                await http.aclose()
                raise
        try:
            response = await self._llm.complete_response(list(messages), retry=False)
            if len(response.choices) != 1:
                raise ValueError("expected one completion")
            choice = response.choices[0]
            if (choice.finish_reason != "stop" or choice.message.tool_calls
                    or choice.message.function_call
                    or choice.message.refusal or not isinstance(choice.message.content, str)):
                raise ValueError("expected a completed text response")
            return choice.message.content
        except SubAgentStopped:
            raise
        except Exception:
            # SDK exceptions may embed response bodies, request headers or provider secrets.
            self._context.check("network")
            raise SubAgentStopped("model_error", "text model request failed") from None

    async def aclose(self) -> None:
        self._closed = True
        self._credential = ""
        if self._llm is not None:
            await self._llm.aclose()
        if self._client is not None:
            await self._client.close()
