"""Explicit image-capable completion service; task data admission still applies."""

from .task_model import TaskModel


class TaskVisualModel(TaskModel):
    """Shares the text service's SDK lifecycle, response checks and accounting."""

    _data_types = frozenset({"text", "image"})
