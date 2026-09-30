"""Host-owned, text-only model service for a single task."""

from __future__ import annotations

import math
from collections.abc import Iterable

import httpx
from openai.types.chat import ChatCompletionMessageParam

from ..agents.subagent import SubAgentContext, SubAgentModel, SubAgentStopped
from ..agents.task_resources import TaskResources
from .llm import LLM
from .model_transport import ChatCompletionsRoute, TaskModelTransport
from .profile import LLMProfile
from .task_client import TaskOpenAI


class TaskModel:
    """Plugins borrow complete(); only the host configures and closes the client."""

    def __init__(
        self, task_id: str, context: SubAgentContext, profile: LLMProfile,
        *, input_modalities: frozenset[str] = frozenset({"text"}),
    ) -> None:
        context.check("network")
        if (
            profile.extra_headers or profile.extra_body
            or not isinstance(profile.api_key, str) or not profile.api_key.strip()
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
        self._input_modalities = input_modalities
        self._context = context
        self._task_id = task_id
        self._credential = profile.api_key
        self._temperature = profile.temperature
        self._client: TaskOpenAI | None = None
        self._llm: LLM | None = None
        self._closed = False
        self._protocol_resources = TaskResources()
        self._transport_index = 0

    @property
    def credential_ref(self) -> str:
        return self._route.credential_ref

    def create_transport(
        self, route: ChatCompletionsRoute, *, inner: httpx.AsyncBaseTransport | None = None,
    ) -> TaskModelTransport:
        """Trusted protocol adapters borrow a host-bound route without receiving its key."""
        self._context.check("network")
        if self._closed:
            raise SubAgentStopped("model_closed")
        if (
            (route.url, route.model, route.credential_ref)
            != (self._route.url, self._route.model, self._route.credential_ref)
            or (route.allow_images and "image" not in self._input_modalities)
            or route.max_upload_bytes > (
                9_500_000 if "image" in self._input_modalities else self._route.max_upload_bytes
            )
        ):
            raise ValueError("protocol route differs from the approved task binding")
        transport = self._protocol_resources.acquire(
            f"transport-{self._transport_index}",
            lambda: TaskModelTransport(
                self._task_id, self._context, routes=(route,),
                credentials={route.credential_ref: self._credential},
                inner=inner or httpx.AsyncHTTPTransport(),
            ),
            lambda resource: resource.aclose(),
        )
        self._transport_index += 1
        return transport

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
                client = TaskOpenAI(
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
        try:
            await self._protocol_resources.aclose()
        finally:
            if self._client is not None:
                await self._client.close()


def resolve_plugin_profile(
    spec: SubAgentModel, profiles: dict[str, LLMProfile], legacy_key: object = None,
) -> LLMProfile:
    """Resolve a reference, or adapt an explicitly supplied legacy key inside the host."""
    profile = profiles.get(spec.profile)
    if profile is None:
        if not isinstance(legacy_key, str) or not legacy_key.strip() or "${" in legacy_key:
            raise ValueError("subagent model profile is not configured")
        profile = LLMProfile(
            spec.profile, legacy_key, spec.model, spec.base_url, capabilities=spec.input_modalities,
        )
    elif legacy_key is not None and legacy_key != profile.api_key:
        raise ValueError("legacy credential conflicts with the named model profile")
    if (
        profile.model != spec.model or profile.base_url.rstrip("/") != spec.base_url.rstrip("/")
        or (profile.capabilities and not spec.input_modalities <= profile.capabilities)
    ):
        raise ValueError("plugin model declaration differs from the approved profile")
    return profile
