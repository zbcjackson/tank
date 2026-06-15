"""AgentTool — the ``agent`` tool for spawning sub-agents.

Phase 2 step 3: dispatch is routed through ``WorkerSupervisor``, which
persists every dispatch as a ``WorkerRunRow`` and posts ``worker.*``
bus events. The observable contract returned to the LLM is identical
to the pre-supervisor implementation — same keys, same error shape,
same depth / concurrency semantics — so callers don't see the change.

Phase 2 step 4 adds the ``run_in_background=True`` path. When
requested, dispatch returns ``{task_id, status: "running"}`` immediately
and the worker continues on the event loop. Terminal completion is
delivered via :class:`WorkerInboxObserver` (subscribed in Brain) so
the originating conversation surfaces the result on the next turn.

If ``WorkerSupervisor`` is not wired (e.g. legacy unit tests construct
``AgentTool`` directly with an ``AgentRunner``), we fall back to the
old ``AgentRunner.run_agent`` loop. The fallback exists only so we
can land Step 3 without rewriting every existing test in lockstep;
production paths always go through the supervisor.
"""

from __future__ import annotations

import logging
from typing import Any

from ..tools.base import (
    BaseTool,
    ToolContext,
    ToolInfo,
    ToolParameter,
)
from .base import AgentOutputType
from .runner import AgentRunner
from .supervisor import (
    ConcurrencyLimitExceeded,
    DepthLimitExceeded,
    WorkerSupervisor,
)

logger = logging.getLogger(__name__)


class AgentTool(BaseTool):
    """Spawn a sub-agent to handle a complex task.

    The LLM calls this tool with a task description and an optional
    agent type. The dispatch goes through ``WorkerSupervisor`` so the
    run is persisted (resumable, listable, stoppable) — but the
    return shape stays identical to the pre-supervisor contract.
    """

    def __init__(
        self,
        runner: AgentRunner,
        *,
        supervisor: WorkerSupervisor | None = None,
    ) -> None:
        self._runner = runner
        self._supervisor = supervisor

    def get_info(self) -> ToolInfo:
        # Build description with available agent types
        defs = self._runner.definitions
        agent_list = ", ".join(
            f"'{name}'" for name in sorted(defs)
        ) if defs else "none configured"

        return ToolInfo(
            name="agent",
            description=(
                "Launch a sub-agent to handle a complex or time-consuming "
                "task. Set run_in_background=True to start the task NOW and "
                "keep talking to the user — the result arrives later as a "
                "notification. Use this for ANY work that takes more than a "
                "few seconds (research, multi-step analysis, web scraping, "
                "planning). This is NOT for scheduled/recurring work — for "
                "that use manage_jobs. "
                f"Available types: {agent_list}."
            ),
            parameters=[
                ToolParameter(
                    name="prompt",
                    type="string",
                    description="Clear, specific task description for the agent",
                    required=True,
                ),
                ToolParameter(
                    name="subagent_type",
                    type="string",
                    description=(
                        "Agent type to use (e.g. 'coder', 'researcher', "
                        "'tasker'). Defaults to 'coder'."
                    ),
                    required=False,
                ),
                ToolParameter(
                    name="description",
                    type="string",
                    description="Short description (3-5 words) for tracking",
                    required=False,
                ),
                ToolParameter(
                    name="run_in_background",
                    type="boolean",
                    description=(
                        "Start the task NOW and return immediately so you "
                        "can keep talking to the user. The worker runs in "
                        "the background; its result arrives as a "
                        "notification when done. Default: false. Set true "
                        "for time-consuming work, or whenever the user "
                        "says 'in background' / 'run X for me'."
                    ),
                    required=False,
                ),
            ],
        )

    async def execute(self, *, ctx: ToolContext | None = None, **kwargs: Any) -> dict[str, Any]:
        agent_type = kwargs.get("subagent_type", "coder")
        prompt: str = kwargs["prompt"]
        background = kwargs.get("run_in_background", False)
        description = kwargs.get("description", "")
        originating_conversation_id = ctx.session_id if ctx is not None else None

        agent_def = self._runner.get_definition(agent_type)
        if agent_def is None:
            available = sorted(self._runner.definitions.keys())
            return {
                "error": f"Agent type '{agent_type}' not found",
                "message": (
                    f"Agent type '{agent_type}' not found. "
                    f"Available: {', '.join(available)}"
                ),
            }

        if self._supervisor is not None:
            return await self._execute_via_supervisor(
                agent_def=agent_def,
                agent_type=agent_type,
                prompt=prompt,
                description=description,
                background=bool(background) or agent_def.background,
                originating_conversation_id=originating_conversation_id,
            )
        return await self._execute_via_runner(
            agent_def=agent_def,
            agent_type=agent_type,
            prompt=prompt,
            description=description,
            background=background or agent_def.background,
        )

    # ------------------------------------------------------------------
    # Supervisor-backed path (production)
    # ------------------------------------------------------------------

    async def _execute_via_supervisor(
        self,
        *,
        agent_def: Any,
        agent_type: str,
        prompt: str,
        description: str,
        background: bool,
        originating_conversation_id: str | None,
    ) -> dict[str, Any]:
        assert self._supervisor is not None  # noqa: S101
        try:
            if background:
                task_id = self._supervisor.run_background(
                    agent_def=agent_def,
                    prompt=prompt,
                    description=description,
                    originating_conversation_id=originating_conversation_id,
                )
                logger.info(
                    "AgentTool: '%s' dispatched in background (task=%s)",
                    agent_type, task_id,
                )
                return {
                    "agent_type": agent_type,
                    "description": description,
                    "task_id": task_id,
                    "status": "running",
                    "message": (
                        f"Agent '{agent_type}' dispatched in background. "
                        f"task_id={task_id}. Use agent_status(task_id) to "
                        f"check progress or agent_stop(task_id) to cancel."
                    ),
                }
            result = await self._supervisor.run_foreground(
                agent_def=agent_def,
                prompt=prompt,
                description=description,
                originating_conversation_id=originating_conversation_id,
            )
        except DepthLimitExceeded as e:
            return self._limit_error(agent_type, str(e))
        except ConcurrencyLimitExceeded as e:
            return self._limit_error(agent_type, str(e))

        if result.status == "completed":
            message = (
                result.output
                or f"Agent '{agent_type}' completed (no text output)."
            )
        else:
            # failed / cancelled / timeout — surface as a tool result
            # rather than raising. The LLM decides what to do next.
            message = self._format_failure_message(
                agent_type=agent_type, result=result,
            )

        logger.info(
            "AgentTool: '%s' %s (task=%s, %d chars)",
            agent_type, result.status, result.task_id, len(result.output),
        )
        return {
            "agent_type": agent_type,
            "description": description,
            "task_id": result.task_id,
            "status": result.status,
            "message": message,
        }

    @staticmethod
    def _format_failure_message(*, agent_type: str, result: Any) -> str:
        partial = result.output.strip()
        prefix = f"Agent '{agent_type}' {result.status}"
        if result.error:
            prefix += f": {result.error}"
        if partial:
            return f"{prefix}\n\nPartial output before {result.status}:\n{partial}"
        return f"{prefix}."

    @staticmethod
    def _limit_error(agent_type: str, detail: str) -> dict[str, Any]:
        return {
            "agent_type": agent_type,
            "error": detail,
            "message": f"Cannot spawn agent '{agent_type}': {detail}",
        }

    # ------------------------------------------------------------------
    # Legacy runner path — unit tests that construct AgentTool directly.
    # ------------------------------------------------------------------

    async def _execute_via_runner(
        self,
        *,
        agent_def: Any,
        agent_type: str,
        prompt: str,
        description: str,
        background: bool,
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        full_text = ""
        tool_calls = 0

        async for output in self._runner.run_agent(
            agent_def=agent_def,
            messages=messages,
            background=background or agent_def.background,
        ):
            if output.type == AgentOutputType.TOKEN:
                full_text += output.content
            elif output.type in (
                AgentOutputType.TOOL_EXECUTING,
                AgentOutputType.TOOL_RESULT,
            ):
                tool_calls += 1

        logger.info(
            "AgentTool: '%s' completed (%d chars, %d tool events)",
            agent_type, len(full_text), tool_calls,
        )

        return {
            "agent_type": agent_type,
            "description": description,
            "message": full_text or f"Agent '{agent_type}' completed (no text output).",
        }
