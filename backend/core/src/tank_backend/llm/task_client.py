"""Task SDK calls use core audit/telemetry, not process-wide payload tracing wrappers."""

from inspect import unwrap
from typing import Any

from openai import AsyncOpenAI
from openai.resources.chat import AsyncChat
from openai.resources.chat.completions import AsyncCompletions


class _TaskCompletions(AsyncCompletions):
    async def create(self, *args: Any, **kwargs: Any) -> Any:
        # Langfuse v4 decorates the SDK globally. Calling the original method on this
        # resource preserves SDK serialization while preventing an extra payload destination.
        return await unwrap(AsyncCompletions.create)(self, *args, **kwargs)


class _TaskChat(AsyncChat):
    @property
    def completions(self) -> AsyncCompletions:
        return _TaskCompletions(self._client)


class TaskOpenAI(AsyncOpenAI):
    task_governed = True

    @property
    def chat(self) -> AsyncChat:
        return _TaskChat(self)
