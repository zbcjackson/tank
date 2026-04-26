"""Autonomous runner — headless agent execution for scheduled jobs."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from ..agents.base import AgentOutputType
from ..agents.definition import AgentDefinition
from .models import JobDefinition, JobRunResult

if TYPE_CHECKING:
    from ..plugin import AppConfig
    from .delivery import DeliveryManager
    from .store import JobStore

logger = logging.getLogger(__name__)


class _AutonomousApprovalPolicy:
    """Approval policy wrapper for headless execution.

    The approval gate has two outcomes: execute or park-for-user.
    In headless mode there's no user, so "park" effectively means "block."

    CommandSecurityPolicy collapses "dangerous" and "unknown" into a single
    ``needs_approval=True``. We can't distinguish them at this layer.

    approval_mode controls how to handle ``needs_approval=True``:

      "deny"  → keep it as True → gate parks the call → agent gets an error
                and must work around it. Only pre-approved safe commands run.
                This is the safe default.

      "auto"  → override to False → gate lets it through → command executes.
                This bypasses the approval gate entirely, including for
                dangerous commands. Use only for trusted jobs where you
                know the prompt won't produce harmful commands.
    """

    def __init__(self, real_policy: Any, approval_mode: str = "deny") -> None:
        self._real = real_policy
        self._auto = approval_mode == "auto"

    def needs_approval(
        self, tool_name: str, tool_args: dict[str, Any] | None = None,
    ) -> bool:
        if self._auto:
            return False
        return self._real.needs_approval(tool_name, tool_args)

    async def needs_approval_async(
        self, tool_name: str, tool_args: dict[str, Any] | None = None,
    ) -> bool:
        if self._auto:
            return False
        return await self._real.needs_approval_async(tool_name, tool_args)


class AutonomousRunner:
    """Execute jobs headlessly using the existing AgentRunner infrastructure."""

    def __init__(
        self,
        app_config: AppConfig,
        job_store: JobStore,
        delivery: DeliveryManager,
    ) -> None:
        self._app_config = app_config
        self._job_store = job_store
        self._delivery = delivery

    async def execute(self, job: JobDefinition) -> JobRunResult:
        """Run a job to completion without user interaction."""
        run_id = uuid.uuid4().hex
        self._job_store.record_run_start(job.id, run_id)
        start = time.monotonic()

        try:
            result_text = await self._run_agent(job, run_id)
            elapsed = time.monotonic() - start

            output_path = await self._delivery.deliver(job, run_id, result_text)

            stats = {"duration_s": round(elapsed, 2), "output_length": len(result_text)}
            self._job_store.record_run_end(
                job.id, run_id, status="succeeded",
                output_path=output_path, stats=stats,
            )
            logger.info(
                "Job '%s' succeeded (run=%s, %.1fs, %d chars)",
                job.name, run_id[:8], elapsed, len(result_text),
            )
            return JobRunResult(
                run_id=run_id, job_id=job.id, status="succeeded",
                output_path=output_path, stats=stats,
            )

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            error = f"Exceeded {job.timeout_seconds}s timeout"
            self._job_store.record_run_end(
                job.id, run_id, status="timeout", error=error,
                stats={"duration_s": round(elapsed, 2)},
            )
            logger.warning("Job '%s' timed out (run=%s, %.1fs)", job.name, run_id[:8], elapsed)
            return JobRunResult(run_id=run_id, job_id=job.id, status="timeout", error=error)

        except Exception as e:
            elapsed = time.monotonic() - start
            error = str(e)
            self._job_store.record_run_end(
                job.id, run_id, status="failed", error=error,
                stats={"duration_s": round(elapsed, 2)},
            )
            logger.error("Job '%s' failed (run=%s): %s", job.name, run_id[:8], e, exc_info=True)
            return JobRunResult(run_id=run_id, job_id=job.id, status="failed", error=error)

    async def _run_agent(self, job: JobDefinition, run_id: str) -> str:
        """Create a headless agent session and run to completion."""
        from ..agents.approval import PendingToolCallStore
        from ..agents.runner import AgentRunner
        from ..llm.profile import create_llm_from_profile
        from ..pipeline.bus import Bus
        from ..tools.manager import ToolManager

        llm = create_llm_from_profile(self._app_config.get_llm_profile(job.llm_profile))
        bus = Bus()
        tool_manager = ToolManager(app_config=self._app_config, bus=bus)

        try:
            approval_policy = self._build_approval_policy(job, tool_manager)
            agent_def = self._build_agent_def(job)

            runner = AgentRunner(
                llm=llm,
                tool_manager=tool_manager,
                bus=bus,
                approval_policy=approval_policy,
                pending_store=PendingToolCallStore(),
                definitions={agent_def.name: agent_def},
            )

            messages: list[dict[str, Any]] = [{"role": "user", "content": job.prompt}]
            output_parts: list[str] = []

            async with asyncio.timeout(job.timeout_seconds):
                async for output in runner.run_agent(
                    agent_def=agent_def,
                    messages=messages,
                    max_turns=job.max_iterations,
                ):
                    if output.type == AgentOutputType.TOKEN:
                        output_parts.append(output.content)

            return "".join(output_parts)
        finally:
            await tool_manager.cleanup()

    def _build_approval_policy(
        self, job: JobDefinition, tool_manager: Any,
    ) -> Any:
        """Wrap the real ToolApprovalPolicy for autonomous execution.

        The real policy (from ToolManager) still runs CommandSecurityPolicy
        to evaluate each command. The wrapper only controls what happens
        when the verdict is "require_approval" (no user to ask):
          "auto"  → approve it
          "deny"  → block it (agent gets an error)
        """
        real_policy = tool_manager.approval_policy
        return _AutonomousApprovalPolicy(real_policy, job.approval_mode)

    def _build_agent_def(self, job: JobDefinition) -> AgentDefinition:
        """Build an AgentDefinition from the job config.

        blocked_tools are added to disallowed_tools (agent can't see them).
        All other tools remain visible — security is handled by the
        approval policy wrapper + tool-internal policies.
        """
        disallowed = set(job.blocked_tools) if job.blocked_tools else set()

        system_prompt = (
            f"You are executing a scheduled autonomous job: '{job.name}'.\n"
            f"Complete the task described below. You have no interactive user — "
            f"work independently and produce a complete result.\n"
        )

        return AgentDefinition(
            name=f"job_{job.name}",
            description=f"Autonomous job: {job.name}",
            system_prompt=system_prompt,
            disallowed_tools=frozenset(disallowed),
            max_turns=job.max_iterations,
        )
