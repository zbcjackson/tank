"""TaskAgent — specialized for calculations, time, and structured tasks."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .chat_agent import ChatAgent

if TYPE_CHECKING:
    from ..llm.llm import LLM
    from ..tools.manager import ToolManager

_DEFAULT_TOOLS = ["calculate", "get_time", "get_weather"]


def _load_prompt(name: str) -> str:
    path = Path(__file__).parent.parent / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


class TaskAgent(ChatAgent):
    """Agent optimized for calculations, time queries, and structured tasks."""

    def __init__(
        self,
        llm: LLM,
        tool_manager: ToolManager | None = None,
        tool_filter: list[str] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> None:
        prompt = system_prompt or _load_prompt("task_prompt.txt") or (
            "You are a task-oriented assistant. Use the available tools to perform "
            "calculations, check the time, and complete structured tasks accurately. "
            "Show your work when performing calculations."
        )
        super().__init__(
            name="task",
            llm=llm,
            tool_manager=tool_manager,
            system_prompt=prompt,
            tool_filter=tool_filter or _DEFAULT_TOOLS,
            **kwargs,
        )
