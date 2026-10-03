"""Host-owned non-streaming JSON calls through the shared model transport."""

from __future__ import annotations

import json

import httpx

from ..agents.subagent import SubAgentContext, SubAgentStopped
from .model_transport import ModelRoute, TaskModelTransport, json_object


class TaskJSONModel:
    """A trusted host installs one route; callers cannot replace its destination or key."""

    def __init__(
        self, task_id: str, context: SubAgentContext, route: ModelRoute, credential: str,
    ) -> None:
        context.check("network")
        url = httpx.URL(route.url)
        if (url.scheme != "https" or not url.host or url.userinfo or url.query or url.fragment
                or not credential.strip() or not route.credential_ref):
            raise ValueError("JSON model requires an exact HTTPS endpoint and credential")
        self._task_id, self._context, self._route = task_id, context, route
        self._credential = credential
        self._client: httpx.AsyncClient | None = None
        self._closed = False

    @property
    def model_name(self) -> str:
        return self._route.model

    async def request(self, payload: dict[str, object]) -> dict[str, object]:
        self._context.check("network")
        if self._closed:
            raise SubAgentStopped("model_closed")
        request = httpx.Request(
            "POST", self._route.url, headers={"Content-Type": "application/json"},
            content=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        )
        self._route.validate(request)
        if self._route.is_streaming(request):
            raise ValueError("JSON model does not support streaming")
        if self._client is None:
            transport = TaskModelTransport(
                self._task_id, self._context, routes=(self._route,),
                credentials={self._route.credential_ref: self._credential},
                inner=httpx.AsyncHTTPTransport(),
            )
            self._client = httpx.AsyncClient(
                transport=transport, follow_redirects=False, trust_env=False, timeout=30,
            )
        try:
            response = await self._client.send(request)
            return json_object(response.content)
        except Exception:
            self._context.check("network")
            raise SubAgentStopped("model_error", "JSON model request failed") from None

    async def aclose(self) -> None:
        self._closed = True
        self._credential = ""
        if self._client is not None:
            await self._client.aclose()
