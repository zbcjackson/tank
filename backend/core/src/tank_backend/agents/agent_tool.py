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

import json
import logging
import time
from typing import Any

from ..tools.base import (
    BaseTool,
    ToolContext,
    ToolInfo,
    ToolParameter,
    ToolResult,
)
from .base import AgentOutputType
from .runner import AgentRunner
from .subagent import SubAgentAuthorization
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
        # A5: one-time tokens authorizing a computer-control dispatch the
        # user just approved (round-trips through ConfirmActionTool).
        self._issued_tokens: dict[str, tuple[str, str]] = {}

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

    async def execute(self, *, ctx: ToolContext | None = None, **kwargs: Any) -> ToolResult:
        agent_type = kwargs.get("subagent_type", "coder")
        prompt: str = kwargs["prompt"]
        background = kwargs.get("run_in_background", False)
        description = kwargs.get("description", "")
        originating_conversation_id = ctx.session_id if ctx is not None else None

        agent_def = self._runner.get_definition(agent_type)
        if agent_def is None:
            available = sorted(self._runner.definitions.keys())
            return ToolResult(
                content=json.dumps({
                    "error": f"Agent type '{agent_type}' not found",
                    "available": available,
                }, ensure_ascii=False),
                error=True,
            )

        permissions = (self._runner.extension_permissions(agent_def)
                       if agent_def.extension else frozenset())
        # A5 dispatch gate: launching an agent whose toolset controls the
        # computer needs ONE user approval; the approved re-entry carries a
        # token and the run inherits the authorization for its actions.
        authorized = self._consume_authorization_token(kwargs)
        if not authorized and (permissions or self._computer_gate_needed(agent_def)):
            return self._park_dispatch_approval(
                kwargs=kwargs, prompt=prompt, ctx=ctx, permissions=permissions,
            )
        allowed_categories = {"computer"} if authorized else None
        authorization = SubAgentAuthorization(permissions) if authorized else None

        if self._supervisor is not None:
            return await self._execute_via_supervisor(
                agent_def=agent_def,
                agent_type=agent_type,
                prompt=prompt,
                description=description,
                background=bool(background) or agent_def.background,
                originating_conversation_id=originating_conversation_id,
                allowed_categories=allowed_categories,
                authorization=authorization,
            )
        return await self._execute_via_runner(
            agent_def=agent_def,
            agent_type=agent_type,
            prompt=prompt,
            description=description,
            background=background or agent_def.background,
            allowed_categories=allowed_categories,
            authorization=authorization,
        )

    # ------------------------------------------------------------------
    # A5: computer-control dispatch approval
    # ------------------------------------------------------------------

    def _computer_gate_needed(self, agent_def: Any) -> bool:
        policy = getattr(self._runner, "_approval_policy", None)
        # ``is not True`` keeps duck-typed fakes (unit-test mocks) open.
        if policy is None or policy.computer_requires_approval() is not True:
            return False
        if agent_def.extension:
            return bool(self._runner.extension_permissions(agent_def))
        if agent_def.engine:
            registry = getattr(self._runner, "_registry", None)
            manifest = registry.get_manifest(agent_def.engine) if registry is not None else None
            # Engine agents ignore toolsets: approval follows declared capabilities.
            return manifest is None or "desktop_executor" in manifest.needs
        tool_filter = agent_def.tool_filter
        if tool_filter is None and agent_def.toolset:
            tool_filter = self._runner._resolve_toolset(agent_def.toolset)
        if tool_filter is None:
            # Unfiltered agents see every tool, computer tools included.
            return True
        return any(
            policy.category_for(name) == "computer" for name in tool_filter
        )

    def _consume_authorization_token(self, kwargs: dict[str, Any]) -> bool:
        token = kwargs.pop("authorization_token", None)
        if not token or token not in self._issued_tokens:
            return False
        approved = self._issued_tokens.pop(token)
        return approved == (kwargs.get("prompt", ""), kwargs.get("subagent_type", "coder"))

    def _park_dispatch_approval(
        self, *, kwargs: dict[str, Any], prompt: str, ctx: Any,
        permissions: frozenset[str] = frozenset(),
    ) -> ToolResult:
        import secrets

        from .approval import PendingToolCall, make_approval_id

        store = getattr(self._runner, "_pending_store", None)
        bus = getattr(self._runner, "_bus", None)
        if store is None or bus is None:
            # No approval machinery (unit-test runners): refuse to run
            # computer control silently.
            return ToolResult(
                content=(
                    "APPROVAL REQUIRED: this agent controls the computer "
                    "(mouse/keyboard) and needs user approval, but no "
                    "approval channel is configured."
                ),
                display="Computer control needs approval",
                error=True,
            )

        token = secrets.token_hex(8)
        self._issued_tokens[token] = (prompt, kwargs.get("subagent_type", "coder"))
        scope = ", ".join(sorted(permissions)) if permissions else "control mouse & keyboard"
        description = f"{scope}: {prompt[:120]}"
        pending = PendingToolCall(
            approval_id=make_approval_id(),
            tool_name="agent",
            tool_args={**kwargs, "authorization_token": token},
            tool_call_id="dispatch",
            arguments_raw="",
            description=description,
            session_id=(ctx.session_id if ctx is not None else ""),
            created_at=time.time(),
        )
        store.park(pending)

        import uuid as uuid_mod

        from ..core.events import DisplayMessage, UpdateType
        from ..pipeline.bus import BusMessage

        bus.post(
            BusMessage(
                type="ui_message",
                source="approval_gate",
                payload=DisplayMessage(
                    speaker="Brain",
                    text=description,
                    is_user=False,
                    # Real id: the frontend anchors approval cards by msg_id —
                    # an empty one makes a second card in the same
                    # conversation a duplicate that never renders.
                    msg_id=f"approval_{uuid_mod.uuid4().hex[:8]}",
                    is_final=False,
                    update_type=UpdateType.APPROVAL,
                    metadata={
                        "approval_id": pending.approval_id,
                        "tool_name": "agent",
                        "tool_args": pending.tool_args,
                        "permissions": sorted(permissions),
                    },
                ),
                timestamp=time.time(),
            ),
        )
        return ToolResult(
            content=(
                f"APPROVAL REQUIRED: the user must confirm {scope} "
                "before this agent can run. Ask the user; "
                "on confirmation the dispatch resumes automatically."
            ),
            display="Computer control needs approval",
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
        allowed_categories: set[str] | None = None,
        authorization: SubAgentAuthorization | None = None,
    ) -> ToolResult:
        assert self._supervisor is not None  # noqa: S101
        extension_kwargs: dict[str, Any] = ({"authorization": authorization}
                                           if agent_def.extension else {})
        try:
            if background:
                task_id = self._supervisor.run_background(
                    agent_def=agent_def,
                    prompt=prompt,
                    description=description,
                    originating_conversation_id=originating_conversation_id,
                    allowed_categories=allowed_categories,
                    **extension_kwargs,
                )
                logger.info(
                    "AgentTool: '%s' dispatched in background (task=%s)",
                    agent_type, task_id,
                )
                return ToolResult(
                    content=json.dumps({
                        "agent_type": agent_type,
                        "description": description,
                        "task_id": task_id,
                        "status": "running",
                        "message": (
                            f"Agent '{agent_type}' dispatched in background. "
                            f"task_id={task_id}. Use agent_status(task_id) to "
                            f"check progress or agent_stop(task_id) to cancel."
                        ),
                    }, ensure_ascii=False),
                    display=f"Agent '{agent_type}' dispatched (task={task_id})",
                )
            result = await self._supervisor.run_foreground(
                agent_def=agent_def,
                prompt=prompt,
                description=description,
                originating_conversation_id=originating_conversation_id,
                allowed_categories=allowed_categories,
                **extension_kwargs,
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
        return ToolResult(
            content=json.dumps({
                "agent_type": agent_type,
                "description": description,
                "task_id": result.task_id,
                "status": result.status,
                "message": message,
            }, ensure_ascii=False),
            display=f"Agent '{agent_type}' {result.status}",
        )

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
    def _limit_error(agent_type: str, detail: str) -> ToolResult:
        return ToolResult(
            content=json.dumps({
                "agent_type": agent_type,
                "error": detail,
                "message": f"Cannot spawn agent '{agent_type}': {detail}",
            }, ensure_ascii=False),
            error=True,
        )

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
        allowed_categories: set[str] | None = None,
        authorization: SubAgentAuthorization | None = None,
    ) -> ToolResult:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]

        full_text = ""
        tool_calls = 0
        run_kwargs: dict[str, Any] = {}
        if allowed_categories:
            run_kwargs["allowed_categories"] = allowed_categories

        if agent_def.extension:
            run_kwargs["authorization"] = authorization
        async for output in self._runner.run_agent(
            agent_def=agent_def,
            messages=messages,
            background=background or agent_def.background,
            **run_kwargs,
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

        return ToolResult(
            content=json.dumps({
                "agent_type": agent_type,
                "description": description,
                "message": full_text or f"Agent '{agent_type}' completed (no text output).",
            }, ensure_ascii=False),
            display=f"Agent '{agent_type}' completed",
        )
