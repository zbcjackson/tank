"""Health dataclasses and aggregation for pipeline monitoring."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueueHealth:
    """Snapshot of a single ThreadedQueue's health state."""

    name: str
    size: int
    maxsize: int
    last_consumed_at: float | None  # monotonic timestamp
    is_stuck: bool
    consumer_alive: bool


@dataclass(frozen=True)
class ProcessorHealth:
    """Snapshot of a single Processor's health state."""

    name: str
    is_running: bool
    consecutive_failures: int
    last_error: str | None


@dataclass(frozen=True)
class PipelineHealth:
    """Aggregate health snapshot for an entire pipeline."""

    running: bool
    processors: list[ProcessorHealth]
    queues: list[QueueHealth]
    is_healthy: bool


@dataclass(frozen=True)
class ComponentHealth:
    """Health of one logical component (pipeline, llm, langfuse, etc.)."""

    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    detail: str
    checked_at: float = field(default_factory=time.time)


class HealthAggregator:
    """Collects health from multiple named check functions into a unified response.

    Each registered check is a callable returning ``ComponentHealth``.
    ``check_all()`` runs them all and produces a JSON-serializable dict
    suitable for the ``/health`` endpoint.
    """

    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], ComponentHealth]] = {}

    def register(self, name: str, check: Callable[[], ComponentHealth]) -> None:
        """Register a named health check function."""
        self._checks[name] = check

    def check_all(self) -> dict[str, Any]:
        """Run all registered health checks, return unified result.

        Returns ``{"status": "healthy"|"degraded"|"unhealthy", "components": {...}}``.
        Overall status is the worst status among all components.
        """
        components: dict[str, Any] = {}
        worst = "healthy"

        for name, check_fn in self._checks.items():
            try:
                result = check_fn()
            except Exception:
                logger.error("Health check %r failed", name, exc_info=True)
                result = ComponentHealth(
                    name=name,
                    status="unhealthy",
                    detail="Health check raised an exception",
                )

            components[name] = {
                "status": result.status,
                "detail": result.detail,
                "checked_at": result.checked_at,
            }

            if result.status == "unhealthy":
                worst = "unhealthy"
            elif result.status == "degraded" and worst == "healthy":
                worst = "degraded"

        return {"status": worst, "components": components}

    def is_healthy(self) -> bool:
        """Quick liveness check — just verifies the process is responsive."""
        return True
