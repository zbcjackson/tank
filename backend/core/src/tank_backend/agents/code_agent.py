"""CodeAgent — specialized for code execution in sandbox."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .chat_agent import ChatAgent

if TYPE_CHECKING:
    from ..llm.llm import LLM
    from ..tools.manager import ToolManager

_DEFAULT_TOOLS = ["sandbox_exec", "sandbox_bash", "sandbox_process"]


def _load_prompt(name: str) -> str:
    path = Path(__file__).parent.parent / "prompts" / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


class CodeAgent(ChatAgent):
    """Agent optimized for code execution in a sandboxed environment."""

    def __init__(
        self,
        llm: LLM,
        tool_manager: ToolManager | None = None,
        tool_filter: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        prompt = system_prompt or _load_prompt("code_prompt.txt") or (
            "You are a code execution assistant. Use the sandbox tools to run "
            "Python code and shell commands safely. Always explain what the code does "
            "before executing it. Handle errors gracefully and suggest fixes."
        )
        super().__init__(
            name="code",
            llm=llm,
            tool_manager=tool_manager,
            system_prompt=prompt,
            tool_filter=tool_filter or _DEFAULT_TOOLS,
        )
