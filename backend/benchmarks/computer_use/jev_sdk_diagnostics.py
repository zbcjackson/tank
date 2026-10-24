"""Process-scoped benchmark diagnostics; no production source or model payload changes."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar
from unittest.mock import patch

from tank_backend.benchmarks.model_policy import BenchmarkModelPolicy
from tank_backend.llm.decision_model import DecisionModelError
from tank_backend.llm.model_call import (
    ModelCaptureError,
    TaskModelCallRunner,
    get_model_call,
)
from tank_backend.llm.model_data import ModelRequest
from tank_backend.observability.model_observation import call_metadata

T = TypeVar("T")


def error_fields(error: BaseException) -> dict[str, object]:
    """Whitelisted types/status only: never stringify SDK exceptions or bodies."""
    status = getattr(error, "status_code", getattr(error, "status", None))
    if type(status) is not int:
        status = getattr(getattr(error, "response", None), "status_code", None)
    fields: dict[str, object] = {
        "error_type": type(error).__name__,
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
        "cause_type": type(error.__cause__).__name__ if error.__cause__ else None,
        "context_type": type(error.__context__).__name__ if error.__context__ else None,
    }
    diagnostics = getattr(error, "diagnostics", None)
    if isinstance(error, DecisionModelError) and isinstance(diagnostics, dict):
        for key in ("error_type", "http_status", "cause_type"):
            value = diagnostics.get(key)
            if value is None or type(value) in (str, int):
                fields["sdk_" + key] = value
    return fields


@contextmanager
def sdk_diagnostics(path: Path) -> Iterator[None]:
    """Instrument one serial standalone study, restoring the original runner on exit."""
    original = TaskModelCallRunner.run
    with path.open("x", encoding="utf-8") as stream:

        def emit(runner: TaskModelCallRunner, phase: str, **fields: object) -> None:
            try:
                stream.write(
                    json.dumps(
                        {"phase": phase, "task_id": runner.task_id, **fields},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                stream.flush()
            except (OSError, ValueError):
                policy = runner.context.model_policy
                if isinstance(policy, BenchmarkModelPolicy):
                    policy.ledger.stop("diagnostic_failed")
                runner.context.runtime.stop("capture_failed")
                raise ModelCaptureError(
                    "required benchmark diagnostics failed"
                ) from None

        def completion(runner: TaskModelCallRunner) -> dict[str, object]:
            record = get_model_call(runner.task_id)
            policy = runner.context.model_policy
            snapshot = (
                policy.ledger.snapshot()
                if isinstance(policy, BenchmarkModelPolicy)
                else None
            )
            reservation = (
                snapshot["requests"].get(record.call_id)
                if snapshot is not None and record is not None
                else None
            )
            return {
                "call_id": record.call_id if record else None,
                "completion_status": record.status if record else None,
                "usage_status": (
                    "known"
                    if record and record.status == "returned"
                    else record.status
                    if record
                    else None
                ),
                "input_tokens": record.prompt_tokens if record else None,
                "output_tokens": record.completion_tokens if record else None,
                "reservation_status": reservation.get("status")
                if reservation
                else None,
                "stop_reason": snapshot["stop_reason"] if snapshot else None,
                "task_deadline_elapsed": (
                    runner.context.deadline is not None
                    and time.monotonic() >= runner.context.deadline
                ),
            }

        async def observed(
            runner: TaskModelCallRunner,
            request: ModelRequest,
            invoke: Callable[[], Awaitable[T]],
        ) -> T:
            async def audited_invoke() -> T:
                metadata = call_metadata.get() or {}
                emit(runner, "invoke_started", call_id=metadata.get("call_id"))
                try:
                    value = await invoke()
                except BaseException as error:
                    emit(
                        runner,
                        "invoke_error",
                        call_id=metadata.get("call_id"),
                        **error_fields(error),
                    )
                    raise
                emit(
                    runner,
                    "invoke_returned",
                    call_id=metadata.get("call_id"),
                    value_type=type(value).__name__,
                )
                return value

            try:
                value = await original(runner, request, audited_invoke)
            except BaseException as error:
                emit(runner, "call_error", **completion(runner), **error_fields(error))
                raise
            emit(runner, "call_returned", **completion(runner))
            return value

        with patch.object(TaskModelCallRunner, "run", observed):
            yield
