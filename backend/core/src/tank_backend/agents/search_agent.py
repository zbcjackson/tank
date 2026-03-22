"""SearchAgent — specialized for web search and information retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .chat_agent import ChatAgent

if TYPE_CHECKING:
    from ..llm.llm import LLM
    from ..tools.manager import ToolManager

_DEFAULT_TOOLS = ["web_search", "web_scraper"]


def _load_prompt(name: str) -> str:
    path = Path(__file__).parent.parent / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


class SearchAgent(ChatAgent):
    """Agent optimized for web search and information retrieval."""

    def __init__(
        self,
        llm: LLM,
        tool_manager: ToolManager | None = None,
        tool_filter: list[str] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> None:
        prompt = system_prompt or _load_prompt("search_prompt.txt") or (
            "You are a search assistant. Use the available search tools to find "
            "accurate, up-to-date information. Always cite your sources when possible. "
            "If a search returns no useful results, say so clearly."
        )
        super().__init__(
            name="search",
            llm=llm,
            tool_manager=tool_manager,
            system_prompt=prompt,
            tool_filter=tool_filter or _DEFAULT_TOOLS,
            **kwargs,
        )
