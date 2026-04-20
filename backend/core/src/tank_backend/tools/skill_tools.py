"""Skill tool wrappers — single router tool + management tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class UseSkillTool(BaseTool):
    """Single router tool — LLM calls this with a skill name + optional args.

    Supports two execution modes (set via ``context`` in SKILL.md):

    **inline** (default): The skill instructions are returned as the tool
    result.  The LLM reads them and follows them in subsequent turns of the
    same ``chat_stream`` loop.

    **fork**: Uses ``AgentRunner.run_agent()`` to create a sub-agent with
    the skill instructions as its system prompt.  The sub-agent gets all
    execution tools, approval, and UI streaming — same as any other agent.
    Auto-escalates to fork when ``allowed_tools`` is non-empty.
    """

    def __init__(self, manager: Any, agent_runner: Any = None) -> None:
        self._manager = manager
        self._agent_runner = agent_runner  # Set later via set_agent_runner()

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="use_skill",
            description=(
                "Execute a skill by name. Check the system-reminder for "
                "available skills. When a user's request matches a skill, "
                "prefer calling this tool over handling it yourself."
            ),
            parameters=[
                ToolParameter(
                    name="skill",
                    type="string",
                    description="The skill name (e.g. 'hello-world', 'summarize-webpage')",
                    required=True,
                ),
                ToolParameter(
                    name="args",
                    type="string",
                    description="Optional arguments for the skill",
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult | str:
        skill_name: str = kwargs["skill"]
        args: str = kwargs.get("args", "")

        result = await self._manager.invoke(skill_name, args)
        if "error" in result:
            return ToolResult(
                content=json.dumps(result, ensure_ascii=False),
                display=result.get("message", str(result.get("error"))),
                error=True,
            )

        context = result.get("context", "inline")
        allowed_tools = result.get("allowed_tools", [])

        # Auto-escalate to fork when the skill needs tools
        if context == "fork" or allowed_tools:
            return await self._execute_fork(result)

        return self._execute_inline(result)

    def _execute_inline(self, invoke_result: dict[str, Any]) -> str:
        """Inline mode: return skill instructions as plain string for LLM."""
        name = invoke_result["skill_name"]
        instructions = invoke_result["instructions"]

        return (
            f"SKILL ACTIVATED: {name}\n"
            f"You MUST now follow these instructions step by step. "
            f"Do NOT just describe what you would do — actually do it. "
            f"Use any tools needed to complete the task.\n\n"
            f"--- BEGIN SKILL INSTRUCTIONS ---\n"
            f"{instructions}\n"
            f"--- END SKILL INSTRUCTIONS ---"
        )

    async def _execute_fork(self, invoke_result: dict[str, Any]) -> ToolResult:
        """Fork mode: run skill via AgentRunner as a dynamic sub-agent."""
        name = invoke_result["skill_name"]
        instructions = invoke_result["instructions"]

        if self._agent_runner is None:
            logger.warning(
                "Fork mode requested for skill '%s' but AgentRunner "
                "not available — falling back to inline",
                name,
            )
            return self._execute_inline(invoke_result)

        from ..agents.base import AgentOutputType
        from ..agents.definition import AgentDefinition

        # Create a dynamic agent definition from the skill
        skill_agent_def = AgentDefinition(
            name=f"skill_{name}",
            description=f"Executing skill: {name}",
            system_prompt=(
                f"You are executing the skill '{name}'. "
                f"Follow the instructions below precisely. "
                f"Do NOT describe what you would do — actually execute "
                f"the commands using the tools available to you.\n\n"
                f"{instructions}"
            ),
            disallowed_tools=frozenset({
                "agent", "use_skill", "list_skills",
                "create_skill", "install_skill",
            }),
        )

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": instructions},
        ]

        full_text = ""
        tool_calls = 0

        async for output in self._agent_runner.run_agent(
            agent_def=skill_agent_def,
            messages=messages,
        ):
            if output.type == AgentOutputType.TOKEN:
                full_text += output.content
            elif output.type in (
                AgentOutputType.TOOL_EXECUTING,
                AgentOutputType.TOOL_RESULT,
            ):
                tool_calls += 1

        logger.info(
            "UseSkillTool fork: '%s' completed (%d chars, %d tool events)",
            name, len(full_text), tool_calls,
        )

        return ToolResult(
            content=json.dumps({
                "skill_name": name,
                "status": "forked",
                "output": full_text,
                "tool_calls": tool_calls,
            }, ensure_ascii=False),
            display=full_text or f"Skill '{name}' completed (no output).",
        )


class ListSkillsTool(BaseTool):
    """List all available skills with metadata."""

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="list_skills",
            description=(
                "List all available skills with their name, description, "
                "tags, risk level, and review status."
            ),
            parameters=[],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        skills = self._manager.registry.list_all()
        if not skills:
            return ToolResult(
                content=json.dumps({"skills": []}, ensure_ascii=False),
                display="No skills installed.",
            )

        entries = []
        for s in skills:
            entries.append({
                "name": s.metadata.name,
                "description": s.metadata.description,
                "version": s.metadata.version,
                "tags": list(s.metadata.tags),
                "allowed_tools": list(s.metadata.allowed_tools),
                "reviewed": s.reviewed,
                "approval": s.metadata.approval,
            })

        lines = [f"- {e['name']}: {e['description']}" for e in entries]
        return ToolResult(
            content=json.dumps({"skills": entries}, ensure_ascii=False),
            display=f"Available skills ({len(entries)}):\n" + "\n".join(lines),
        )


class CreateSkillTool(BaseTool):
    """Create a new skill from a description."""

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="create_skill",
            description=(
                "Create a new reusable skill. Provide a name, description, "
                "and detailed instructions. The skill will be reviewed "
                "automatically and registered if it passes."
            ),
            parameters=[
                ToolParameter(
                    name="name",
                    type="string",
                    description=(
                        "Skill name (lowercase alphanumeric + hyphens, "
                        "e.g. 'summarize-webpage')"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="Short description of what the skill does",
                    required=True,
                ),
                ToolParameter(
                    name="instructions",
                    type="string",
                    description=(
                        "Detailed markdown instructions for how to execute "
                        "the skill step by step"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="allowed_tools",
                    type="string",
                    description=(
                        "Comma-separated list of tools this skill needs "
                        "(e.g. 'web_search,web_scraper'). Empty if none."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        name: str = kwargs["name"]
        description: str = kwargs["description"]
        instructions: str = kwargs["instructions"]
        tools_str: str = kwargs.get("allowed_tools", "")
        allowed_tools = [t.strip() for t in tools_str.split(",") if t.strip()] if tools_str else []

        result = await self._manager.create(
            name=name,
            description=description,
            instructions=instructions,
            allowed_tools=allowed_tools,
        )
        is_error = "error" in result
        return ToolResult(
            content=json.dumps(result, ensure_ascii=False),
            display=result.get("message", str(result.get("error", ""))),
            error=is_error,
        )


class InstallSkillTool(BaseTool):
    """Install a skill from a git URL, ClawHub registry, or local path."""

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="install_skill",
            description=(
                "Install a skill from a git repository URL, ClawHub registry, "
                "or local path. For ClawHub, use 'clawhub:<slug>' format "
                "(e.g. 'clawhub:gifgrep'). Use search_skills to find slugs. "
                "If the source contains multiple skills, specify skill_name "
                "to install just one, or omit it to install all. "
                "Each skill is security reviewed before activation."
            ),
            parameters=[
                ToolParameter(
                    name="source",
                    type="string",
                    description=(
                        "Git URL (e.g. 'https://github.com/user/skills-repo'), "
                        "ClawHub slug (e.g. 'clawhub:gifgrep'), "
                        "or local path to a directory containing SKILL.md"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="skill_name",
                    type="string",
                    description=(
                        "Install only this skill from a multi-skill source. "
                        "Omit to install all skills found."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        source: str = kwargs["source"]
        skill_name: str | None = kwargs.get("skill_name") or None
        result = await self._manager.install(source, skill_name=skill_name)
        is_error = "error" in result
        return ToolResult(
            content=json.dumps(result, ensure_ascii=False),
            display=result.get("message", str(result.get("error", ""))),
            error=is_error,
        )


class ReloadSkillsTool(BaseTool):
    """Reload skills from disk — picks up new, updated, or removed skills."""

    def __init__(self, manager: Any) -> None:
        self._manager = manager

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="reload_skills",
            description=(
                "Rescan skill directories to pick up newly installed, "
                "updated, or removed skills without restarting the server. "
                "Call this after install_skill or create_skill to ensure "
                "the skill catalog is up to date."
            ),
            parameters=[],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        diff = self._manager.reload()
        added = diff["added"]
        removed = diff["removed"]
        updated = diff["updated"]

        parts: list[str] = []
        if added:
            parts.append(f"Added: {', '.join(added)}")
        if removed:
            parts.append(f"Removed: {', '.join(removed)}")
        if updated:
            parts.append(f"Updated: {', '.join(updated)}")

        display = ". ".join(parts) + "." if parts else "No changes detected."
        return ToolResult(
            content=json.dumps({"diff": diff}, ensure_ascii=False),
            display=display,
        )


class SearchSkillsTool(BaseTool):
    """Search the ClawHub registry for skills."""

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="search_skills",
            description=(
                "Search the ClawHub skill registry (clawhub.ai) for skills "
                "matching a query. Returns skill names, descriptions, and "
                "slugs that can be passed to install_skill as 'clawhub:<slug>'."
            ),
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="Search query (e.g. 'code review', 'git hooks')",
                    required=True,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        from ..skills.source import ClawHubSource

        query: str = kwargs["query"]
        try:
            candidates = await ClawHubSource.search(query)
        except Exception as e:
            logger.error("ClawHub search failed: %s", e)
            return ToolResult(
                content=json.dumps({"error": str(e)}, ensure_ascii=False),
                display=f"Search failed: {e}",
                error=True,
            )

        if not candidates:
            return ToolResult(
                content=json.dumps({"results": []}, ensure_ascii=False),
                display=f"No skills found for '{query}'.",
            )

        entries = [
            {
                "name": c.name,
                "description": c.description,
                "install_id": c.identifier,
            }
            for c in candidates
        ]
        lines = [
            f"- {e['name']}: {e['description']} (install: {e['install_id']})"
            for e in entries
        ]
        return ToolResult(
            content=json.dumps({"results": entries}, ensure_ascii=False),
            display=(
                f"Found {len(entries)} skill(s) on clawhub.ai:\n"
                + "\n".join(lines)
            ),
        )
