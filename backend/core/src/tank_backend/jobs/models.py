"""Data models for autonomous job scheduling."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DeliveryConfig:
    """How to deliver job results."""

    audio: bool = False
    audio_voice: str | None = None
    audio_priority: str = "low"  # "low" | "normal" | "high"
    audio_idle_threshold: int = 300  # seconds of silence before auto-play

    text: bool = True
    text_path: str | None = None  # custom output path override

    webhook_url: str | None = None
    webhook_headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio": self.audio,
            "audio_voice": self.audio_voice,
            "audio_priority": self.audio_priority,
            "audio_idle_threshold": self.audio_idle_threshold,
            "text": self.text,
            "text_path": self.text_path,
            "webhook_url": self.webhook_url,
            "webhook_headers": dict(self.webhook_headers),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DeliveryConfig:
        return DeliveryConfig(
            audio=data.get("audio", False),
            audio_voice=data.get("audio_voice"),
            audio_priority=data.get("audio_priority", "low"),
            audio_idle_threshold=data.get("audio_idle_threshold", 300),
            text=data.get("text", True),
            text_path=data.get("text_path"),
            webhook_url=data.get("webhook_url"),
            webhook_headers=data.get("webhook_headers") or {},
        )


@dataclass(frozen=True)
class JobDefinition:
    """Immutable definition of an autonomous job."""

    id: str
    name: str
    prompt: str
    schedule: str  # cron expression
    enabled: bool = True

    agent: str = "chat"
    llm_profile: str = "default"
    max_iterations: int = 30
    timeout_seconds: int = 300
    allowed_tools: tuple[str, ...] | None = None
    blocked_tools: tuple[str, ...] | None = None

    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    approval_mode: str = "always_deny"  # "always_approve" | "always_deny"

    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "agent": self.agent,
            "llm_profile": self.llm_profile,
            "max_iterations": self.max_iterations,
            "timeout_seconds": self.timeout_seconds,
            "allowed_tools": list(self.allowed_tools) if self.allowed_tools else None,
            "blocked_tools": list(self.blocked_tools) if self.blocked_tools else None,
            "delivery": self.delivery.to_dict(),
            "approval_mode": self.approval_mode,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @staticmethod
    def from_dict(data: dict[str, Any]) -> JobDefinition:
        allowed = data.get("allowed_tools")
        blocked = data.get("blocked_tools")
        delivery_raw = data.get("delivery") or {}
        now = datetime.now(timezone.utc).isoformat()
        return JobDefinition(
            id=data.get("id") or uuid.uuid4().hex,
            name=data["name"],
            prompt=data["prompt"],
            schedule=data["schedule"],
            enabled=data.get("enabled", True),
            agent=data.get("agent", "chat"),
            llm_profile=data.get("llm_profile", "default"),
            max_iterations=data.get("max_iterations", 30),
            timeout_seconds=data.get("timeout_seconds", 300),
            allowed_tools=tuple(allowed) if allowed else None,
            blocked_tools=tuple(blocked) if blocked else None,
            delivery=DeliveryConfig.from_dict(delivery_raw),
            approval_mode=data.get("approval_mode", "always_deny"),
            created_at=data.get("created_at") or now,
            updated_at=data.get("updated_at") or now,
        )

    @staticmethod
    def from_json(text: str) -> JobDefinition:
        return JobDefinition.from_dict(json.loads(text))


@dataclass(frozen=True)
class JobRunResult:
    """Result of a single job execution."""

    run_id: str
    job_id: str
    status: str  # "pending" | "running" | "succeeded" | "failed" | "timeout"
    started_at: str = ""
    finished_at: str = ""
    output_path: str | None = None
    error: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job_id": self.job_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "output_path": self.output_path,
            "error": self.error,
            "stats": dict(self.stats),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> JobRunResult:
        return JobRunResult(
            run_id=data["run_id"],
            job_id=data["job_id"],
            status=data["status"],
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            output_path=data.get("output_path"),
            error=data.get("error"),
            stats=data.get("stats") or {},
        )
