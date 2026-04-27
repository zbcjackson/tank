"""Jobs REST API — CRUD for scheduled jobs, trigger runs, view history."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..jobs.cron import parse_human_schedule, validate_cron
from ..jobs.models import JobDefinition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"], redirect_slashes=False)

# Injected from server.py
_job_store = None
_scheduler = None


def set_job_store(store: Any) -> None:
    global _job_store  # noqa: PLW0603
    _job_store = store


def set_scheduler(scheduler: Any) -> None:
    global _scheduler  # noqa: PLW0603
    _scheduler = scheduler


def _get_store():
    if _job_store is None:
        raise HTTPException(503, "Job store not initialized")
    return _job_store


def _get_scheduler():
    if _scheduler is None:
        raise HTTPException(503, "Scheduler not initialized")
    return _scheduler


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------

class DeliveryRequest(BaseModel):
    audio: bool = False
    audio_voice: str | None = None
    audio_priority: str = "low"
    audio_idle_threshold: int = 300
    text: bool = True
    text_path: str | None = None
    webhook_url: str | None = None
    webhook_headers: dict[str, str] = Field(default_factory=dict)


class CreateJobRequest(BaseModel):
    name: str
    prompt: str
    schedule: str
    enabled: bool = True
    agent: str = "chat"
    llm_profile: str = "default"
    max_iterations: int = 30
    timeout_seconds: int = 300
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] | None = None
    delivery: DeliveryRequest = Field(default_factory=DeliveryRequest)
    approval_mode: str = "always_deny"


class UpdateJobRequest(BaseModel):
    name: str | None = None
    prompt: str | None = None
    schedule: str | None = None
    enabled: bool | None = None
    agent: str | None = None
    llm_profile: str | None = None
    max_iterations: int | None = None
    timeout_seconds: int | None = None
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] | None = None
    delivery: DeliveryRequest | None = None
    approval_mode: str | None = None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _resolve_schedule(raw: str) -> str:
    """Resolve a schedule string — try human-friendly first, then raw cron."""
    human = parse_human_schedule(raw)
    if human is not None:
        return human
    if validate_cron(raw):
        return raw
    raise HTTPException(
        400,
        f"Invalid schedule: '{raw}'. "
        "Use cron (e.g. '0 9 * * *') or human-friendly (e.g. 'every day at 9am').",
    )


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("")
async def list_jobs() -> list[dict[str, Any]]:
    """List all job definitions with schedule info."""
    store = _get_store()
    jobs = store.list_jobs()
    result = []
    for job in jobs:
        entry = job.to_dict()
        result.append(entry)
    return result


@router.post("", status_code=201)
async def create_job(req: CreateJobRequest) -> dict[str, Any]:
    """Create a new scheduled job."""
    store = _get_store()

    schedule = _resolve_schedule(req.schedule)

    existing = store.get_job_by_name(req.name)
    if existing is not None:
        raise HTTPException(409, f"Job with name '{req.name}' already exists")

    now = datetime.now(timezone.utc).isoformat()
    job = JobDefinition.from_dict({
        "id": uuid.uuid4().hex,
        "name": req.name,
        "prompt": req.prompt,
        "schedule": schedule,
        "enabled": req.enabled,
        "agent": req.agent,
        "llm_profile": req.llm_profile,
        "max_iterations": req.max_iterations,
        "timeout_seconds": req.timeout_seconds,
        "allowed_tools": req.allowed_tools,
        "blocked_tools": req.blocked_tools,
        "delivery": req.delivery.model_dump(),
        "approval_mode": req.approval_mode,
        "created_at": now,
        "updated_at": now,
    })
    store.save_job(job)
    logger.info("Created job '%s' (schedule=%s)", job.name, schedule)

    entry = job.to_dict()
    return entry


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    """Get job details."""
    store = _get_store()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job.to_dict()


@router.put("/{job_id}")
async def update_job(job_id: str, req: UpdateJobRequest) -> dict[str, Any]:
    """Update a job definition (partial update)."""
    store = _get_store()
    existing = store.get_job(job_id)
    if existing is None:
        raise HTTPException(404, f"Job '{job_id}' not found")

    data = existing.to_dict()
    updates = req.model_dump(exclude_none=True)

    if "schedule" in updates:
        updates["schedule"] = _resolve_schedule(updates["schedule"])
    if "delivery" in updates:
        d = updates["delivery"]
        updates["delivery"] = (
            d.model_dump() if hasattr(d, "model_dump") else d
        )

    data.update(updates)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    updated = JobDefinition.from_dict(data)
    store.save_job(updated)
    logger.info("Updated job '%s'", updated.name)

    entry = updated.to_dict()
    return entry


@router.delete("/{job_id}")
async def delete_job(job_id: str) -> dict[str, str]:
    """Delete a job, cancel it if running, and remove its history."""
    store = _get_store()
    scheduler = _get_scheduler()

    # Cancel if currently running
    await scheduler.cancel_job(job_id)

    if not store.delete_job(job_id):
        raise HTTPException(404, f"Job '{job_id}' not found")
    logger.info("Deleted job '%s'", job_id)
    return {"status": "deleted", "job_id": job_id}


@router.post("/{job_id}/run")
async def trigger_run(job_id: str) -> dict[str, Any]:
    """Trigger an immediate run of a job."""
    scheduler = _get_scheduler()
    result = await scheduler.trigger_job(job_id)
    if result is None:
        raise HTTPException(
            409, "Cannot trigger job — not found, already running, or scheduler at capacity"
        )
    return {"status": "triggered", "job_id": job_id}


@router.get("/{job_id}/runs")
async def list_runs(job_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """List recent runs for a job."""
    store = _get_store()
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    runs = store.get_runs(job_id, limit=limit)
    return [r.to_dict() for r in runs]


@router.post("/{job_id}/enable")
async def enable_job(job_id: str) -> dict[str, Any]:
    """Enable a job."""
    store = _get_store()
    if not store.set_enabled(job_id, True):
        raise HTTPException(404, f"Job '{job_id}' not found")
    return {"status": "enabled", "job_id": job_id}


@router.post("/{job_id}/disable")
async def disable_job(job_id: str) -> dict[str, Any]:
    """Disable a job."""
    store = _get_store()
    if not store.set_enabled(job_id, False):
        raise HTTPException(404, f"Job '{job_id}' not found")
    return {"status": "disabled", "job_id": job_id}


@router.get("/scheduler/status", tags=["scheduler"])
async def scheduler_status() -> dict[str, Any]:
    """Get scheduler health and status."""
    scheduler = _get_scheduler()
    return scheduler.status


@router.post("/scheduler/reload-seed", tags=["scheduler"])
async def reload_seed() -> dict[str, Any]:
    """Reload seed.yaml — sync mode. Creates new jobs, removes stale ones."""
    scheduler = _get_scheduler()
    return scheduler.reload_seed()
