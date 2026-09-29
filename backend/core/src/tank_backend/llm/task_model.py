"""Host-owned, text-only model service for a single task."""

from __future__ import annotations

import math
from collections.abc import Iterable

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from ..agents.subagent import SubAgentContext, SubAgentStopped
from .llm import LLM
from .model_transport import ChatCompletionsRoute, TaskModelTransport
from .profile import LLMProfile


class TaskModel:
    """Plugins borrow complete(); only the host configures and closes the client."""

    def __init__(self, task_id: str, context: SubAgentContext, profile: LLMProfile) -> None:
        context.check("network")
        if (
            profile.extra_headers or profile.extra_body or not profile.api_key
            or (profile.temperature is not None and (
                isinstance(profile.temperature, bool)
                or not math.isfinite(profile.temperature) or not 0 <= profile.temperature <= 2
            ))
        ):
            raise ValueError("profile is incompatible with the task text model service")
        self._route = ChatCompletionsRoute(
            profile.base_url.rstrip("/") + "/chat/completions", profile.model,
            profile.name, max_output_tokens=profile.max_tokens,
        )
        self._context = context
        self._task_id = task_id
        self._credential = profile.api_key
        self._temperature = profile.temperature
        self._client: AsyncOpenAI | None = None
        self._llm: LLM | None = None
        self._closed = False

    async def complete(self, messages: Iterable[ChatCompletionMessageParam]) -> str:
        """One text completion, accounted at HTTP before returning any result."""
        self._context.check("network")
        if self._closed:
            raise SubAgentStopped("model_closed")
        if self._llm is None:
            maximum = self._route.max_output_tokens
            assert maximum is not None
            transport = TaskModelTransport(
                self._task_id, self._context, routes=(self._route,),
                credentials={self._route.credential_ref: self._credential},
                inner=httpx.AsyncHTTPTransport(),
            )
            http = httpx.AsyncClient(transport=transport, follow_redirects=False, trust_env=False)
            try:
                client = AsyncOpenAI(
                    api_key="host-managed",
                    base_url=self._route.url.removesuffix("chat/completions"),
                    max_retries=0, http_client=http,
                )
                self._llm = LLM(
                    api_key="host-managed", model=self._route.model,
                    base_url=str(client.base_url), temperature=self._temperature,
                    max_tokens=maximum, client=client,
                )
                self._client = client
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
        except Exception:
            # SDK exceptions may embed response bodies, request headers or provider secrets.
            self._context.check("network")
            raise SubAgentStopped("model_error", "text model request failed") from None

    async def aclose(self) -> None:
        self._closed = True
        self._credential = ""
        if self._client is not None:
            await self._client.close()
