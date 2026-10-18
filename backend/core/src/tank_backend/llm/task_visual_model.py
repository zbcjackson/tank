"""Explicit image-capable completion service; task data admission still applies."""

from collections.abc import Iterable

from openai.types.chat import ChatCompletionMessageParam

from .task_model import TaskModel


class TaskVisualModel(TaskModel):
    """Shares the text service's SDK lifecycle, response checks and accounting."""

    _data_types = frozenset({"text", "image"})

    async def complete_json(self, messages: Iterable[ChatCompletionMessageParam]) -> str:
        """Request JSON-object output; callers still validate fields and semantics."""
        return await self._complete(messages, json_object=True)
