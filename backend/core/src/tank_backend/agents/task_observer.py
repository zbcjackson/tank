"""Optional task model telemetry; never owns accounting or admission."""

from __future__ import annotations

import logging
from typing import Any

from ..pipeline.bus import Bus, BusMessage
from .subagent import SubAgentObserver

logger = logging.getLogger(__name__)


class TaskObserver:
    def __init__(self, bus: Bus, delegate: SubAgentObserver | None = None) -> None:
        self._bus = bus
        self._delegate = delegate

    def on_event(self, kind: str, metadata: dict[str, Any]) -> None:
        try:
            if kind == "model_call":
                self._publish_model(metadata)
        finally:
            if self._delegate is not None:
                self._delegate.on_event(kind, metadata)

    def _publish_model(self, metadata: dict[str, Any]) -> None:
        # Keep provider content/headers out even if another emitter adds fields later.
        payload = {key: metadata[key] for key in (
            "task_id", "call_id", "phase", "status", "prompt_tokens", "completion_tokens",
            "elapsed_ms",
        ) if key in metadata}
        self._bus.post_bounded(BusMessage("task_model_call", "TaskRuntime", payload))
        if payload.get("phase") != "finished":
            return
        logger.info(
            "Task model call task=%s call=%s status=%s elapsed_ms=%s input=%s output=%s",
            payload.get("task_id"), payload.get("call_id"), payload.get("status"),
            payload.get("elapsed_ms"), payload.get("prompt_tokens"),
            payload.get("completion_tokens"),
        )
        if payload.get("status") == "not_sent":
            return
        usage = {"task_id": payload["task_id"], "call_id": payload["call_id"]}
        if payload.get("status") == "returned":
            usage.update(
                prompt_tokens=payload["prompt_tokens"],
                completion_tokens=payload["completion_tokens"],
                total_tokens=payload["prompt_tokens"] + payload["completion_tokens"],
            )
        self._bus.post_bounded(BusMessage("llm_usage", "TaskRuntime", usage))
