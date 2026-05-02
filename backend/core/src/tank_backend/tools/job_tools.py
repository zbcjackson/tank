"""Job management tool — lets the LLM agent manage scheduled jobs conversationally."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

if TYPE_CHECKING:
    from ..jobs.scheduler import CronScheduler
    from ..jobs.store import JobStore

logger = logging.getLogger(__name__)


class JobManagementTool(BaseTool):
    """Manage autonomous scheduled jobs.

    Supports: create, list, update, run, enable, disable, delete, history.
    """

    def __init__(self, job_store: JobStore, scheduler: CronScheduler) -> None:
        self._store = job_store
        self._scheduler = scheduler

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="manage_jobs",
            description=(
                "Create, list, update, run, enable, disable, or delete "
                "scheduled autonomous jobs, or view run history and output. "
                "Jobs run on a cron schedule without user interaction. "
                "Stored in ~/.tank/jobs/."
            ),
            parameters=[
                ToolParameter(
                    name="action", type="string",
                    description=(
                        "Action to perform: create, list, update, run, enable, disable, "
                        "delete, history, status"
                    ),
                ),
                ToolParameter(
                    name="name", type="string", required=False,
                    description="Job name (for create/update/run/enable/disable/delete/history)",
                ),
                ToolParameter(
                    name="prompt", type="string", required=False,
                    description="What the agent should do each run (for create/update)",
                ),
                ToolParameter(
                    name="schedule", type="string", required=False,
                    description=(
                        "Cron expression or human-friendly schedule like 'every day at 9am', "
                        "'every 30m', 'weekdays at 14:30' (for create/update)"
                    ),
                ),
                ToolParameter(
                    name="delivery", type="string", required=False,
                    description=(
                        "JSON delivery config: {\"audio\": true, \"text\": true, "
                        "\"webhook_url\": \"...\"} (for create/update)"
                    ),
                ),
                ToolParameter(
                    name="approval_mode", type="string", required=False,
                    description=(
                        "Tool approval policy: 'always_deny' (default, safe) "
                        "or 'always_approve' (for create/update)"
                    ),
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "").strip().lower()

        dispatch = {
            "create": self._create,
            "list": self._list,
            "update": self._update,
            "run": self._run,
            "enable": self._enable,
            "disable": self._disable,
            "delete": self._delete,
            "history": self._history,
            "status": self._status,
        }

        handler = dispatch.get(action)
        if handler is None:
            return ToolResult(
                content=f"Unknown action '{action}'. Valid: {', '.join(dispatch.keys())}",
                error=True,
            )

        try:
            return await handler(kwargs)
        except Exception as e:
            logger.error("manage_jobs %s error: %s", action, e, exc_info=True)
            return ToolResult(content=f"Error: {e}", error=True)

    async def _create(self, kwargs: dict[str, Any]) -> ToolResult:
        from ..jobs.cron import validate_cron
        from ..jobs.models import JobDefinition

        name = kwargs.get("name")
        prompt = kwargs.get("prompt")
        schedule = kwargs.get("schedule")

        if not name or not prompt or not schedule:
            return ToolResult(content="Missing required fields: name, prompt, schedule", error=True)

        if not validate_cron(schedule):
            return ToolResult(
                content=f"Invalid schedule: '{schedule}'. Use a cron expression.",
                error=True,
            )

        # Check for duplicate name
        if self._store.get_job_by_name(name) is not None:
            return ToolResult(
                content=f"Job '{name}' already exists. Use 'update' to modify it.",
                error=True,
            )

        # Parse delivery config
        delivery_raw = kwargs.get("delivery")
        delivery_dict = {}
        if delivery_raw:
            if isinstance(delivery_raw, str):
                try:
                    delivery_dict = json.loads(delivery_raw)
                except json.JSONDecodeError:
                    return ToolResult(content="Invalid delivery JSON", error=True)
            elif isinstance(delivery_raw, dict):
                delivery_dict = delivery_raw

        job = JobDefinition.from_dict({
            "name": name,
            "prompt": prompt,
            "schedule": schedule,
            "delivery": delivery_dict,
            "approval_mode": kwargs.get("approval_mode", "always_deny"),
        })
        self._store.save_job(job)
        await self._scheduler.sync_schedules()

        return ToolResult(
            content=f"Created job '{name}' (schedule: {schedule})",
            display=f"Scheduled job '{name}'",
        )

    async def _list(self, kwargs: dict[str, Any]) -> ToolResult:
        jobs = self._store.list_jobs()
        if not jobs:
            return ToolResult(content="No scheduled jobs.")

        lines = []
        for job in jobs:
            status = "enabled" if job.enabled else "disabled"
            lines.append(
                f"- {job.name} [{status}] schedule={job.schedule}",
            )

        return ToolResult(content="\n".join(lines))

    async def _update(self, kwargs: dict[str, Any]) -> ToolResult:
        from ..jobs.cron import validate_cron
        from ..jobs.models import JobDefinition

        name = kwargs.get("name")
        if not name:
            return ToolResult(content="Missing required field: name", error=True)

        existing = self._store.get_job_by_name(name)
        if existing is None:
            return ToolResult(content=f"Job '{name}' not found", error=True)

        data = existing.to_dict()

        if kwargs.get("prompt"):
            data["prompt"] = kwargs["prompt"]
        if kwargs.get("schedule"):
            if not validate_cron(kwargs["schedule"]):
                return ToolResult(
                    content=f"Invalid schedule: '{kwargs['schedule']}'. Use a cron expression.",
                    error=True,
                )
            data["schedule"] = kwargs["schedule"]
        if kwargs.get("approval_mode"):
            data["approval_mode"] = kwargs["approval_mode"]
        if kwargs.get("delivery"):
            delivery_raw = kwargs["delivery"]
            if isinstance(delivery_raw, str):
                data["delivery"] = json.loads(delivery_raw)
            elif isinstance(delivery_raw, dict):
                data["delivery"] = delivery_raw

        updated = JobDefinition.from_dict(data)
        self._store.save_job(updated)
        await self._scheduler.sync_schedules()
        return ToolResult(content=f"Updated job '{name}'")

    async def _run(self, kwargs: dict[str, Any]) -> ToolResult:
        name = kwargs.get("name")
        if not name:
            return ToolResult(content="Missing required field: name", error=True)

        job = self._store.get_job_by_name(name)
        if job is None:
            return ToolResult(content=f"Job '{name}' not found", error=True)

        result = await self._scheduler.trigger_job(job.id)
        if result is None:
            return ToolResult(
                content=f"Cannot run '{name}' — already running or at capacity",
                error=True,
            )
        return ToolResult(content=f"Triggered job '{name}'")

    async def _enable(self, kwargs: dict[str, Any]) -> ToolResult:
        name = kwargs.get("name")
        if not name:
            return ToolResult(content="Missing required field: name", error=True)
        job = self._store.get_job_by_name(name)
        if job is None:
            return ToolResult(content=f"Job '{name}' not found", error=True)
        self._store.set_enabled(job.id, True)
        await self._scheduler.sync_schedules()
        return ToolResult(content=f"Enabled job '{name}'")

    async def _disable(self, kwargs: dict[str, Any]) -> ToolResult:
        name = kwargs.get("name")
        if not name:
            return ToolResult(content="Missing required field: name", error=True)
        job = self._store.get_job_by_name(name)
        if job is None:
            return ToolResult(content=f"Job '{name}' not found", error=True)
        self._store.set_enabled(job.id, False)
        await self._scheduler.sync_schedules()
        return ToolResult(content=f"Disabled job '{name}'")

    async def _delete(self, kwargs: dict[str, Any]) -> ToolResult:
        name = kwargs.get("name")
        if not name:
            return ToolResult(content="Missing required field: name", error=True)
        job = self._store.get_job_by_name(name)
        if job is None:
            return ToolResult(content=f"Job '{name}' not found", error=True)
        await self._scheduler.cancel_job(job.id)
        self._store.delete_job(job.id)
        await self._scheduler.sync_schedules()
        return ToolResult(content=f"Deleted job '{name}'")

    async def _history(self, kwargs: dict[str, Any]) -> ToolResult:
        name = kwargs.get("name")
        if not name:
            return ToolResult(content="Missing required field: name", error=True)
        job = self._store.get_job_by_name(name)
        if job is None:
            return ToolResult(content=f"Job '{name}' not found", error=True)

        runs = self._store.get_runs(job.id, limit=10)
        if not runs:
            return ToolResult(content=f"No runs found for job '{name}'")

        lines = [f"Recent runs for '{name}':"]
        for run in runs:
            path = f" → {run.output_path}" if run.output_path else ""
            error = f" error={run.error}" if run.error else ""
            lines.append(f"- [{run.status}] {run.started_at[:19]}{path}{error}")

        return ToolResult(content="\n".join(lines))

    async def _status(self, kwargs: dict[str, Any]) -> ToolResult:
        s = self._scheduler.status
        running = "running" if s["running"] else "stopped"
        return ToolResult(
            content=json.dumps(s, indent=2),
            display=f"Scheduler: {running}, {s['active_jobs']} active jobs",
        )
